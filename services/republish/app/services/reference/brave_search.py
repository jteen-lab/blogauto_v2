"""Brave 검색.

클로드가 자료를 찾을 때 쓰는 검색과 같은 곳이다. 붙이면 손으로 글을
쓸 때 보던 것과 같은 결과가 자료로 들어온다.

순서도: docs/flowcharts/brave_reference.md
"""
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from ...schemas.reference_collection import SearchResult

logger = logging.getLogger(__name__)

API_URL = "https://api.search.brave.com/res/v1/web/search"
TIMEOUT = 10

#: 한 번에 받을 수 있는 최대치
MAX_COUNT = 20

#: 발췌문을 이어 붙였을 때의 상한. 한 결과가 자료를 독차지하면 안 된다.
SNIPPET_MAX_CHARS = 900


def _clean(text: Any) -> str:
    """태그와 겹친 공백을 지운다. 검색 결과에 <strong> 이 섞여 온다."""
    out = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", out).strip()


def _description(row: dict) -> str:
    """본문 대목을 모은다.

    `extra_snippets` 를 켜면 한 결과에서 여러 대목이 온다. 페이지를
    긁지 않고도 쓸 분량이 나온다.
    """
    parts = [_clean(row.get("description"))]
    extra = row.get("extra_snippets")
    if isinstance(extra, list):
        parts.extend(_clean(x) for x in extra)
    joined = " ".join(p for p in parts if p)
    return joined[:SNIPPET_MAX_CHARS]


async def collect(api_key: Optional[str], query: str,
                  count: int = 20) -> List[SearchResult]:
    """검색해서 결과를 돌려준다.

    Args:
        api_key: Brave 구독 토큰. 없으면 빈 목록 — 호출부가 네이버만 쓴다
        query: 검색어
        count: 결과 개수(최대 20)

    Returns:
        SearchResult 목록. 실패해도 예외를 올리지 않는다 — 자료
        한 갈래가 막혔다고 글이 안 나오면 안 된다
    """
    key = (api_key or "").strip()
    text = (query or "").strip()
    if not key or len(text) < 2:
        return []

    params: Dict[str, Any] = {
        "q": text,
        "count": max(1, min(MAX_COUNT, count)),
        "country": "KR",
        "search_lang": "ko",
        "extra_snippets": "true",
        "safesearch": "moderate",
    }
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": key,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(API_URL, params=params, headers=headers)
        if resp.status_code == 429:
            logger.warning("[BRAVE] 호출 한도 초과 | '%s'", text)
            return []
        if resp.status_code != 200:
            logger.warning("[BRAVE] 응답 %s | '%s'", resp.status_code, text)
            return []
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("[BRAVE] 호출 실패 | '%s' | %s", text, e)
        return []

    rows = ((data or {}).get("web") or {}).get("results") or []
    out: List[SearchResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        link = _clean(row.get("url"))
        title = _clean(row.get("title"))
        if not link or not title:
            continue
        out.append(SearchResult(
            title=title, link=link, description=_description(row)))

    logger.info("[BRAVE] '%s' | %d건", text, len(out))
    return out
