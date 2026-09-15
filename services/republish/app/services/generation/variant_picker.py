"""변형 선택 — 같은 블로그·같은 니치라도 글마다 다르게.

**왜 필요한가**: 한 블로그에서 같은 구조로 글이 계속 나가면 검색 쪽에서
패턴이 보인다. 니치를 나누는 것만으로는 부족하다. 같은 니치 안에서도
글마다 구조가 달라야 한다.

프롬프트와 대표 이미지가 **같은 규칙**을 쓴다. 그래서 선택 로직을 한 곳에
둔다. 모드는 넷이다.

    random      매번 무작위
    sequential  순번대로 (커서는 호출부가 보관한다 — 동시 실행 경합을
                피하려면 모듈 설정이 아니라 실행 상태에 둬야 한다)
    by_niche    하위 주제별로 고정
    by_keyword  키워드 패턴별로 고정

**후보가 없으면 None 을 돌려준다.** 호출부는 기존 단수 설정으로 폴백한다.
이게 하위 호환의 전부다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §3-2
순서도: docs/flowcharts/topic_discovery.md §4
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger

logger = get_logger("variant_picker", "app.log")

MODE_RANDOM = "random"
MODE_SEQUENTIAL = "sequential"
MODE_BY_NICHE = "by_niche"
MODE_BY_KEYWORD = "by_keyword"

ALL_MODES = (MODE_RANDOM, MODE_SEQUENTIAL, MODE_BY_NICHE, MODE_BY_KEYWORD)
DEFAULT_MODE = MODE_RANDOM

MODE_LABEL = {
    MODE_RANDOM: "무작위",
    MODE_SEQUENTIAL: "순번",
    MODE_BY_NICHE: "하위 주제별",
    MODE_BY_KEYWORD: "키워드별",
}


@dataclass
class Picked:
    """고른 변형 하나."""

    item: Dict[str, Any]
    index: int
    mode: str
    next_cursor: int
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "mode": self.mode,
                "next_cursor": self.next_cursor, "reason": self.reason}


def normalize_mode(value: Any) -> str:
    """모르는 모드는 무작위로. 설정 오타로 생성이 멈추면 안 된다."""
    text = str(value or "").strip().lower()
    return text if text in ALL_MODES else DEFAULT_MODE


def _matches_topic(item: Dict[str, Any], topic_id: Optional[int]) -> bool:
    """topic_ids 가 비어 있으면 모든 주제에 쓴다(공용 변형)."""
    ids = item.get("topic_ids") or []
    if not ids:
        return True
    if topic_id is None:
        return False
    return int(topic_id) in [int(x) for x in ids if x is not None]


def _matches_purpose(item: Dict[str, Any], purpose: Optional[str]) -> bool:
    """purpose 가 비어 있으면 목적을 가리지 않는다."""
    want = (item.get("purpose") or "").strip().lower()
    if not want:
        return True
    return want == (purpose or "").strip().lower()


def keyword_score(item: Dict[str, Any], keyword: str) -> int:
    """이 변형이 제목과 얼마나 맞는가. 0 이면 안 맞는다.

    **한 규칙 안의 `+` 는 모두 들어 있어야 한다(조합).** 단어 하나로
    가르면 겹친다 — 템플릿1 이 `이사`, 템플릿2 가 `청소` 면 「이사 청소」
    에 둘 다 걸리고, 「방청소」 처럼 엉뚱한 말에도 걸린다.
    `이사+견적` 과 `이사+청소` 로 적으면 그 겹침이 사라진다.

    쉼표로 나눈 규칙끼리는 **둘 중 하나만** 맞으면 된다.
        "이사+견적, 이사+비용"  →  (이사 그리고 견적) 또는 (이사 그리고 비용)

    Returns:
        맞은 규칙 중 가장 구체적인 것의 낱말 수. 조건이 없으면 0
    """
    marks = [str(m).strip() for m in (item.get("keywords") or []) if str(m).strip()]
    if not marks:
        return 0
    text = keyword or ""
    best = 0
    for rule in marks:
        parts = [p.strip() for p in rule.split("+") if p.strip()]
        if parts and all(p in text for p in parts):
            best = max(best, len(parts))
    return best


def _matches_keyword(item: Dict[str, Any], keyword: str) -> bool:
    """keywords 가 비어 있으면 항상 통과."""
    if not (item.get("keywords") or []):
        return True
    return keyword_score(item, keyword) > 0


def candidates(items: Sequence[Dict[str, Any]], *,
               topic_id: Optional[int] = None,
               purpose: Optional[str] = None,
               keyword: str = "") -> List[Dict[str, Any]]:
    """조건에 맞는 변형만 남긴다.

    조건이 너무 좁아 하나도 안 남으면 **조건 없는 변형들**로 물러선다.
    글이 안 나가는 것보다 낫다.
    """
    rows = [i for i in (items or []) if isinstance(i, dict)]
    picked = [i for i in rows
              if _matches_purpose(i, purpose)
              and _matches_topic(i, topic_id)
              and _matches_keyword(i, keyword)]
    if picked:
        return picked

    loose = [i for i in rows
             if not (i.get("topic_ids") or i.get("keywords"))
             and _matches_purpose(i, purpose)]
    if loose:
        logger.info("[VARIANT] 조건 일치 없음 — 공용 변형 %d개로 물러섬",
                    len(loose))
    return loose


def pick(items: Sequence[Dict[str, Any]], mode: Any = DEFAULT_MODE, *,
         topic_id: Optional[int] = None, purpose: Optional[str] = None,
         keyword: str = "", cursor: int = 0) -> Optional[Picked]:
    """변형 하나를 고른다. 후보가 없으면 None.

    Args:
        items: 변형 목록
        mode: random | sequential | by_niche | by_keyword
        topic_id: 하위 주제. by_niche 와 조건 필터에 쓴다
        purpose: adsense | cpa | info
        keyword: by_keyword 와 조건 필터에 쓴다
        cursor: sequential 의 현재 순번

    Returns:
        Picked 또는 None
    """
    pool = candidates(items, topic_id=topic_id, purpose=purpose,
                      keyword=keyword)
    if not pool:
        return None

    picked_mode = normalize_mode(mode)

    # 키워드별에서 여럿이 맞으면 **더 구체적인 것**이 이긴다.
    # 「이사 청소」에 `이사` 와 `이사+청소` 가 다 맞으면 뒤쪽을 쓴다 —
    # 그러라고 조합으로 적은 것이다.
    if picked_mode == MODE_BY_KEYWORD and len(pool) > 1:
        scores = [keyword_score(i, keyword) for i in pool]
        top = max(scores)
        if top > 0:
            pool = [i for i, sc in zip(pool, scores) if sc == top]

    size = len(pool)

    if picked_mode == MODE_SEQUENTIAL:
        index = int(cursor or 0) % size
        reason = f"순번 {index + 1}/{size}"
    elif picked_mode == MODE_BY_NICHE:
        index = _stable_index(str(topic_id or ""), size)
        reason = f"주제 {topic_id} 고정"
    elif picked_mode == MODE_BY_KEYWORD:
        index = _stable_index(keyword or "", size)
        reason = "키워드 고정"
    else:
        index = random.randrange(size)
        reason = f"무작위 {index + 1}/{size}"

    return Picked(item=pool[index], index=index, mode=picked_mode,
                  next_cursor=int(cursor or 0) + 1, reason=reason)


def _stable_index(key: str, size: int) -> int:
    """같은 키면 항상 같은 자리. 주제·키워드별 고정에 쓴다."""
    if not key:
        return 0
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size
