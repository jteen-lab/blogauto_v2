"""키워드 묶기 — 생산 단위를 키워드에서 클러스터로 올린다.

정석은 **SERP 오버랩**이다(두 키워드의 상위 노출 URL 이 겹치면 같은 글로
커버할 수 있다). 다만 키워드마다 검색 결과를 받아야 해 호출량이 크다.
그래서 1차는 **토큰 겹침**으로 묶고, SERP 오버랩은 유망 후보에만 나중에
적용한다(계획서 §9-4).

한국어 키워드는 띄어쓰기가 들쭉날쭉하다("전기기사 실기" / "전기기사실기").
그래서 공백 토큰과 **문자 2-gram** 을 함께 쓴다.

계획서: docs/plans/keyword_module_redesign_plan.md §3 [4]
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from ...core.logger import get_logger
from . import intent as intent_mod

logger = get_logger("keyword_clustering", "app.log")

# 같은 묶음으로 볼 최소 유사도
DEFAULT_THRESHOLD = 0.34

# 묶음 최소 크기. 이보다 작으면 클러스터로 치지 않는다(단독 키워드로 남는다).
DEFAULT_MIN_SIZE = 3

# 묶음 최대 크기. 너무 크면 한 글로 커버할 수 없는 주제까지 섞인다.
DEFAULT_MAX_SIZE = 12

# 의미 없는 토큰. 이것만 겹치면 같은 주제가 아니다.
STOPWORDS = {"방법", "추천", "후기", "비교", "초보", "정리", "가격", "무료"}

_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")


def tokens(keyword: str) -> Set[str]:
    """비교용 토큰 집합.

    공백으로 자른 낱말과 문자 2-gram 을 함께 쓴다. 한국어 키워드는
    띄어쓰기가 일정하지 않아 낱말만 보면 같은 말을 다른 것으로 센다.
    """
    text = _NON_WORD.sub(" ", (keyword or "").lower()).strip()
    if not text:
        return set()

    words = {w for w in text.split() if len(w) > 1 and w not in STOPWORDS}
    joined = text.replace(" ", "")
    grams = {joined[i:i + 2] for i in range(len(joined) - 1)}
    return words | grams


def similarity(left: str, right: str) -> float:
    """두 키워드의 겹침(자카드). 0~1."""
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def build(items: Sequence[Any], threshold: float = DEFAULT_THRESHOLD,
          min_size: int = DEFAULT_MIN_SIZE,
          max_size: int = DEFAULT_MAX_SIZE) -> List[List[Any]]:
    """키워드들을 묶는다.

    검색량이 큰 것부터 씨앗으로 삼고, 아직 안 묶인 것 중 충분히 비슷한
    것을 붙인다. 큰 것을 축으로 잡아야 대표 키워드가 묶음을 대표한다.

    Args:
        items: `keyword` 와 `search_volume` 속성을 가진 객체들
        threshold: 같은 묶음으로 볼 최소 유사도
        min_size: 이보다 작은 묶음은 버린다
        max_size: 이보다 크게는 안 묶는다

    Returns:
        묶음 목록. 각 묶음의 첫 항목이 대표다.
    """
    pool = sorted(items, key=lambda x: (getattr(x, "search_volume", 0) or 0),
                  reverse=True)
    used: Set[int] = set()
    clusters: List[List[Any]] = []

    for index, seed in enumerate(pool):
        if index in used:
            continue
        group = [seed]
        used.add(index)
        for other_index in range(index + 1, len(pool)):
            if other_index in used or len(group) >= max_size:
                continue
            if similarity(seed.keyword, pool[other_index].keyword) >= threshold:
                group.append(pool[other_index])
                used.add(other_index)
        if len(group) >= min_size:
            clusters.append(group)

    logger.info("[CLUSTERING] 키워드 %d개 → 묶음 %d개 (최소 %d개)",
                len(pool), len(clusters), min_size)
    return clusters


def describe(group: Sequence[Any]) -> Dict[str, Any]:
    """묶음의 요약 — 대표 키워드·의도·검색량 합계·니치."""
    keywords = [g.keyword for g in group]
    lead = group[0]
    volumes = [getattr(g, "search_volume", None) or 0 for g in group]
    return {
        "name": lead.keyword,
        "intent": intent_mod.dominant(keywords),
        "size": len(group),
        "total_volume": sum(volumes) or None,
        "topic_id": _first(group, "topic_id"),
        "subtopic_id": _first(group, "subtopic_id"),
    }


def _first(group: Sequence[Any], field: str) -> Optional[int]:
    """묶음에서 처음 나오는 값. 미분류는 건너뛴다."""
    for item in group:
        value = getattr(item, field, None)
        if value:
            return value
    return None
