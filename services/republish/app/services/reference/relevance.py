"""관련성 관문 — 이 자료가 정말 그 제목에 대한 것인가.

기존 파이프라인은 관련성을 **한 번도** 보지 않았다. 검색 결과를 위에서부터
크롤링하고, 그중 무작위로 골라 요약했다. 그래서 "우리아파트론" 글에
"우리은행 대표전화 안내" 가 자료로 들어갔다(2026-09-06 실측).

세 관문을 둔다. 앞의 둘은 비용이 0 이라 먼저 건다.

    관문 1  검색 결과 제목·설명에 개체가 있나        (크롤링 전)
    관문 2  크롤링한 본문에 개체가 있나              (요약 전)
    관문 3  요약이 "관련 없음" 이라 답했나           (요약 후)

**무관한 자료를 넣는 것은 자료가 없는 것보다 나쁘다.** 없으면 AI 가 일반
지식으로 쓰지만, 무관한 자료가 있으면 그것을 이 주제의 사실로 쓴다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger
from .query_builder import strip_particle

logger = get_logger("reference_relevance", "app.log")

# 요약 AI 가 "이 문서엔 관련 내용이 없다" 고 답할 때 쓰는 말.
NO_MATCH = "관련 없음"

# 본문에서 개체를 찾을 때 앞부분만 본다. 긴 문서의 꼬리에 한 번 스친 것을
# 관련 있다고 보면 관문이 무의미해진다.
BODY_SCAN_CHARS = 4000

_WORD = re.compile(r"[가-힣A-Za-z0-9]+")


def _norm(text: str) -> str:
    """비교용 정규화. 띄어쓰기·조사 차이를 없앤다.

    "우리 아파트론" 과 "우리아파트론" 은 같은 말이다. 붙여서 비교한다.
    """
    words = [strip_particle(w) for w in _WORD.findall((text or "").lower())]
    return "".join(words)


def matches(text: str, entities: Sequence[str]) -> bool:
    """개체 중 **하나라도** 들어 있나.

    전부 요구하면(AND) 통과가 거의 없다 — 문서가 상품명만 쓰고 은행명을
    생략하는 일이 흔하다. 하나면 충분하되, 개체는 이미 고유한 말로
    골라져 있다(query_builder.extract_entities).
    """
    if not entities:
        return True          # 판단 근거가 없으면 막지 않는다
    haystack = _norm(text)
    if not haystack:
        return False
    return any(_norm(e) and _norm(e) in haystack for e in entities)


def _cascade(items: Sequence[Any], entities: Sequence[str], text_of,
             keep_min: int, stage: str) -> List[Any]:
    """개체를 좁은 것부터 넓은 것 순으로 적용한다.

    개체를 OR 로 한꺼번에 쓰면 "대출" 같은 일반어가 섞여 아무것도 안
    걸러진다. 실제로 "우리아파트론" 글에서 "우리은행 대표전화 안내" 가
    통과했다. 그래서 **가장 고유한 개체 하나**로 먼저 좁히고, 너무 적게
    남을 때만 넓힌다.

        1) entities[0] 만으로            — 가장 좁다
        2) 아무 개체나 하나라도          — 넓힌다
        3) 그래도 부족하면 원본 그대로   — 0건이 되는 것보다 낫다
    """
    if not entities:
        return list(items)

    narrow = [i for i in items if matches(text_of(i), entities[:1])]
    if len(narrow) >= keep_min:
        if len(narrow) < len(items):
            logger.info("[REF_GATE] %s %d→%d건 | 개체='%s'",
                        stage, len(items), len(narrow), entities[0])
        return narrow

    wide = [i for i in items if matches(text_of(i), entities)]
    if len(wide) >= keep_min:
        logger.info("[REF_GATE] %s 좁힘 %d건뿐 — 개체 전체로 %d건 | %s",
                    stage, len(narrow), len(wide), list(entities))
        return wide

    logger.info("[REF_GATE] %s 통과 %d건뿐 — 원본 %d건 유지 | 개체=%s",
                stage, len(wide), len(items), list(entities))
    return list(items)


def filter_search_results(results: Sequence[Any], entities: Sequence[str],
                          keep_min: int = 3) -> List[Any]:
    """관문 1 — 검색 결과에서 개체가 없는 것을 뺀다.

    남는 게 너무 적으면 거르지 않는다. 개체 추출이 빗나간 제목에서
    전부 걸러 버리면 자료가 0 건이 된다.

    Args:
        results: SearchResult 목록(title·description·link)
        entities: 제목에서 뽑은 개체(앞쪽일수록 고유하다)
        keep_min: 이보다 적게 남으면 다음 단계로 넓힌다

    Returns:
        걸러진 목록(원래 순서 유지)
    """
    return _cascade(
        results, entities,
        lambda i: f"{getattr(i, 'title', '')} {getattr(i, 'description', '')}",
        keep_min, "관문1")


def filter_documents(documents: Sequence[Any], entities: Sequence[str],
                     keep_min: int = 1) -> List[Any]:
    """관문 2 — 크롤링한 본문에 개체가 없는 것을 뺀다.

    검색 결과 제목에는 걸렸지만 본문은 다른 얘기인 문서가 있다.
    """
    return _cascade(
        documents, entities,
        lambda d: (f"{getattr(d, 'title', '') or ''} "
                   f"{(getattr(d, 'content', '') or '')[:BODY_SCAN_CHARS]}"),
        keep_min, "관문2")


def is_no_match(summary: str) -> bool:
    """관문 3 — 요약이 "관련 없음" 이라 답했나.

    AI 가 문장 안에 섞어 답할 수 있어(예: "관련 없음 — 이 문서는…")
    앞부분만 본다. 뒤에서 찾으면 "관련 없음은 아니지만" 같은 문장에 걸린다.
    """
    head = (summary or "").strip().lstrip("-—[( ")[:40]
    return head.startswith(NO_MATCH) or head.lower().startswith("no match")


def filter_summaries(summaries: Sequence[Any]) -> List[Any]:
    """관문 3 — "관련 없음" 요약을 뺀다."""
    kept = [s for s in summaries
            if not is_no_match(getattr(s, "summary", "") or "")]
    dropped = len(summaries) - len(kept)
    if dropped:
        logger.info("[REF_GATE] 관문3 무관 %d건 제외", dropped)
    return kept


def report(before: int, after: int, stage: str) -> Dict[str, Any]:
    """관문별 통과 현황. 0 건이 됐을 때 어디서 막혔는지 알아야 한다."""
    return {"stage": stage, "before": before, "after": after,
            "dropped": max(0, before - after)}


def freshness_key(item: Any) -> tuple:
    """⑤ 최신성 — 새 문서를 앞으로.

    금리·제도는 1년 전 정보가 틀린 정보다. 날짜를 못 읽는 문서는 뒤로
    밀지 않는다(날짜가 없다고 오래된 것은 아니다) — 중간에 둔다.

    Returns:
        정렬 키. 내림차순 정렬에 쓴다.
    """
    raw = (getattr(item, "postdate", None) or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return (1, raw)
    return (0, "")


def sort_by_freshness(results: Sequence[Any]) -> List[Any]:
    """날짜가 있는 것을 최신순으로 앞에, 없는 것을 뒤에."""
    dated = [r for r in results if freshness_key(r)[0] == 1]
    undated = [r for r in results if freshness_key(r)[0] == 0]
    dated.sort(key=lambda r: freshness_key(r)[1], reverse=True)
    return dated + undated
