"""니즈 갭 — 사람들이 물었는데 우리 글이 답하지 않은 것.

AlsoAsked·AnswerThePublic 같은 도구는 "사람들이 물을 법한 질문" 을 **추정**한다.
우리에게는 실측이 있다. 서치콘솔은 이 URL 이 **실제로 어떤 검색어에 노출됐는지**
그대로 준다. 그 질문을 갖고 우리 글에 왔다는 증거다.

    노출된 쿼리  −  본문이 답한 것  =  채울 자리

`intent.py`(의도 분류)와 `angles.py`(경쟁 각도)가 이미 같은 자리에서 돈다.
여기에 실측 쿼리를 하나 더 꽂는 것이지 새 파이프라인이 아니다.

PAA 를 직접 긁지 않는다 — 구글 약관 위반이고 셀렉터가 자주 바뀐다.

계획서: docs/plans/analytics_integration_plan.md §7
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("intent_gap", "app.log")

# 노출이 이보다 적은 쿼리는 잡음이다. 한두 번 스친 검색어까지 채우려 들면
# 글이 잡동사니가 된다.
MIN_IMPRESSIONS = 5

# 한 번에 주입할 질문 수. 많이 넣으면 AI 가 목록만 나열한다.
MAX_GAPS = 6

# 조사·접미 — 붙어 있으면 같은 말인데 다른 토큰이 된다
_TAIL = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만)$")


def _tokens(text: str) -> set:
    """비교용 토큰. 조사를 떼어 '충전요금은' 과 '충전요금' 을 같게 본다."""
    words = re.findall(r"[가-힣A-Za-z0-9]+", (text or "").lower())
    out = set()
    for word in words:
        out.add(word)
        stripped = _TAIL.sub("", word)
        if len(stripped) >= 2:
            out.add(stripped)
    return out


def find_gaps(queries: List[Dict[str, Any]], content: str,
              min_impressions: int = MIN_IMPRESSIONS,
              limit: int = MAX_GAPS) -> List[Dict[str, Any]]:
    """본문이 답하지 않은 쿼리.

    쿼리의 낱말이 **전부** 본문에 있으면 답했다고 본다. 하나라도 없으면
    그 각도는 다루지 않은 것이다. 느슨하게 잡으면(하나라도 겹치면 통과)
    제목만 스쳐도 답한 것이 되어 갭이 사라진다.

    Args:
        queries: gsc_pages.fetch_queries_for_page 결과
        content: 글 본문(HTML 또는 평문)
        min_impressions: 이보다 적게 노출된 쿼리는 무시
        limit: 최대 개수

    Returns:
        노출 많은 순으로 [{"query", "impressions", "position", "intent"}]
    """
    from ..keyword_lab.intent import classify

    body = _tokens(_strip_html(content))
    if not body:
        return []

    gaps: List[Dict[str, Any]] = []
    for row in queries or []:
        query = (row.get("query") or "").strip()
        if not query or (row.get("impressions") or 0) < min_impressions:
            continue
        words = _tokens(query)
        if not words or words <= body:
            continue          # 본문이 이미 다룬다
        gaps.append({
            "query": query,
            "impressions": row.get("impressions") or 0,
            "clicks": row.get("clicks") or 0,
            "position": row.get("position") or 0.0,
            "intent": _intent_of(classify, query),
        })

    gaps.sort(key=lambda g: g["impressions"], reverse=True)
    return _spread(gaps, limit)


def _intent_of(classify, query: str) -> str:
    """의도 분류. 분류기 반환형이 바뀌어도 여기서 흡수한다."""
    try:
        found = classify(query)
    except Exception:  # noqa: BLE001 — 분류 실패로 갭을 버리지 않는다
        return ""
    if isinstance(found, (tuple, list)):
        return str(found[0]) if found else ""
    return str(found or "")


def _spread(gaps: List[dict], limit: int) -> List[dict]:
    """의도가 겹치지 않게 고른다.

    노출 순으로만 자르면 같은 의도('방법' 계열)만 6개가 남는다. 그러면
    보강해도 한 방향으로만 길어진다.
    """
    picked: List[dict] = []
    seen: set = set()
    for gap in gaps:
        key = gap.get("intent") or gap["query"]
        if key in seen:
            continue
        seen.add(key)
        picked.append(gap)
        if len(picked) >= limit:
            return picked
    # 의도가 부족하면 남은 것으로 채운다
    for gap in gaps:
        if gap not in picked:
            picked.append(gap)
            if len(picked) >= limit:
                break
    return picked


def to_prompt(gaps: List[Dict[str, Any]]) -> str:
    """생성 프롬프트에 붙일 지시문.

    "검색어" 라고 말하지 않는다. 그렇게 쓰면 AI 가 키워드를 그대로 박아 넣어
    부자연스러운 문장이 된다. **질문**으로 제시해 답을 쓰게 한다.
    """
    if not gaps:
        return ""
    lines = [
        "[독자가 이 글에서 답을 찾지 못한 것들]",
        "아래는 이 글을 검색으로 만난 사람들이 실제로 궁금해한 내용입니다.",
        "각각에 대해 본문 안에서 자연스럽게 답을 쓰세요. "
        "목록으로 나열하지 말고 흐름에 녹이세요.",
        "",
    ]
    for gap in gaps:
        lines.append(f"- {gap['query']}")
    return "\n".join(lines)


def _strip_html(text: str) -> str:
    """태그를 걷어낸다. 속성값(class 이름 등)이 본문으로 새면 안 된다."""
    if not text:
        return ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text,
                  flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body).strip()


async def gaps_for_url(db, blog, url: str, content: str,
                       token: Optional[str] = None,
                       site: Optional[str] = None) -> List[Dict[str, Any]]:
    """이 URL 의 니즈 갭. 서치콘솔이 안 붙어 있으면 빈 목록이다."""
    from ..search_visibility import index_check_service as ics
    from ..search_visibility.runner import resolve_gsc_token
    from .gsc_pages import fetch_queries_for_page

    access = token or await resolve_gsc_token(db)
    if not access:
        return []
    if not site:
        try:
            site = ics.resolve_property(await ics.list_sites(access), blog)
        except ics.IndexCheckError:
            return []
    if not site:
        return []

    queries = await fetch_queries_for_page(access, site, url)
    return find_gaps(queries, content)
