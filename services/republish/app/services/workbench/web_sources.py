"""키워드·제목으로 글감 찾기 — 블로그·웹문서에서.

지식iN·카페는 질문이 있는 주제에만 쓸 수 있다. 이미 정해 둔 제목으로
쓰고 싶을 때, 또는 질문이 잘 안 잡히는 주제일 때 여기를 쓴다.

**돌려주는 모양을 질문 검색과 맞춘다.** 그래야 고르기·본문 가져오기·
글 만들기로 이어지는 길을 새로 만들지 않는다.

순서도: docs/flowcharts/workbench_web_sources.md
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

import httpx

from ...core.logger import get_logger

logger = get_logger("workbench_web_sources", "app.log")

BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
WEBKR_URL = "https://openapi.naver.com/v1/search/webkr.json"

SRC_BLOG = "naver_blog"
SRC_WEBKR = "naver_webkr"

ENDPOINT = {SRC_BLOG: BLOG_URL, SRC_WEBKR: WEBKR_URL}
SOURCE_LABEL = {SRC_BLOG: "블로그", SRC_WEBKR: "웹문서"}

#: 글감이 될 수 없는 곳. 웹문서(webkr)는 웹사이트 색인이라 한 단어
#: 키워드에서 서점·오픈마켓·가격비교가 위를 차지한다("다이어트" →
#: 알라딘·G마켓). 열어 봐야 상품 목록이라 참고 글로 못 쓴다.
#: 순서를 흔들지 않기 위해 **여기 말고는 아무것도 버리지 않는다.**
JUNK_HOSTS = (
    # 서점
    "aladin.co.kr", "kyobobook.co.kr", "yes24.com", "ridibooks.com",
    "millie.co.kr", "bookk.co.kr", "booksamo.com",
    # 오픈마켓·쇼핑
    "gmarket.co.kr", "coupang.com", "11st.co.kr", "auction.co.kr",
    "ssg.com", "lotteon.com", "wemakeprice.com", "tmon.co.kr",
    "smartstore.naver.com", "shopping.naver.com", "brand.naver.com",
    "interpark.com", "himart.co.kr", "aliexpress.com", "amazon.com",
    # 가격비교·쿠폰
    "danawa.com", "enuri.com", "ppomppu.co.kr",
)

TIMEOUT = 10.0
CALL_DELAY = 0.25
PER_SOURCE = 15
#: 네이버가 받는 시작 위치 상한. 넘기면 400 이 온다.
MAX_START = 1000

_TAG = re.compile(r"<[^>]+>")
_HOST = re.compile(r"^https?://(?:www\.)?([^/?#]+)", re.I)


def host_of(link: str) -> str:
    """주소에서 도메인만. 판정과 화면 표시에 같이 쓴다."""
    m = _HOST.match((link or "").strip())
    return (m.group(1) if m else "").lower()


def is_junk(link: str) -> bool:
    """글감이 될 수 없는 곳인가 — 서점·오픈마켓·가격비교."""
    host = host_of(link)
    return any(host == j or host.endswith("." + j) for j in JUNK_HOSTS)


def _headers(user_settings: Any) -> Dict[str, str]:
    """참조 검색·질문 검색과 같은 키를 쓴다."""
    return {
        "X-Naver-Client-Id":
            getattr(user_settings, "naver_search_client_id", "") or "",
        "X-Naver-Client-Secret":
            getattr(user_settings, "naver_search_client_secret", "") or "",
    }


def is_configured(user_settings: Any) -> bool:
    head = _headers(user_settings)
    return bool(head["X-Naver-Client-Id"] and head["X-Naver-Client-Secret"])


def _clean(text: str) -> str:
    """검색 결과의 <b> 강조와 실체 참조를 벗긴다."""
    out = _TAG.sub("", text or "")
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", out).strip()


async def _fetch(user_settings: Any, query: str, source: str,
                 limit: int, client: httpx.AsyncClient,
                 start: int, sort: str = "sim") -> List[dict]:
    """한 곳에서 긁는다. 실패는 빈 목록 — 회차를 죽이지 않는다."""
    url = ENDPOINT.get(source)
    if not url:
        return []
    try:
        resp = await client.get(
            url, headers=_headers(user_settings),
            params={"query": query, "display": limit,
                    "start": min(int(start), MAX_START),
                    "sort": sort if sort in ("sim", "date") else "sim"})
        if resp.status_code != 200:
            logger.warning("[WEB_SOURCE] %s 응답 %s | %s",
                           source, resp.status_code, resp.text[:120])
            return []
        rows = (resp.json() or {}).get("items") or []
    except Exception as e:                            # noqa: BLE001
        logger.warning("[WEB_SOURCE] %s 실패 | %s", source, e)
        return []

    out = []
    dropped = 0
    for rank, row in enumerate(rows, start=int(start)):
        title = _clean(row.get("title", ""))
        link = (row.get("link") or "").strip()
        if not title or not link:
            continue
        if is_junk(link):
            dropped += 1
            continue
        out.append({
            "title": title,
            "description": _clean(row.get("description", "")),
            "link": link,
            "source": source,
            "source_label": SOURCE_LABEL.get(source, source),
            "has_situation": False,
            # 네이버 검색에서 몇 번째였나 — 순서를 눈으로 대조할 수 있다
            "rank": rank,
            "signals": [s for s in (row.get("bloggername"),
                                    row.get("postdate"),
                                    host_of(link)) if s],
        })
    if dropped:
        logger.info("[WEB_SOURCE] %s | 서점·쇼핑 %d건 제외", source, dropped)
    return out


def _weave(groups: List[List[dict]]) -> List[dict]:
    """두 곳의 결과를 번갈아 섞는다.

    한쪽을 앞에 몰면 화면 위쪽이 같은 성격으로만 찬다.
    """
    out: List[dict] = []
    seen = set()
    for i in range(max((len(g) for g in groups), default=0)):
        for g in groups:
            if i >= len(g):
                continue
            link = g[i]["link"]
            if link in seen:
                continue
            seen.add(link)
            out.append(g[i])
    return out


async def search_pages(user_settings: Any, query: str,
                       sources: Optional[List[str]] = None,
                       limit: int = PER_SOURCE,
                       start: int = 1,
                       sort: str = "sim") -> Dict[str, Any]:
    """키워드·제목으로 글감을 찾는다.

    Args:
        user_settings: 네이버 검색 자격증명 보유 객체
        query: 키워드 또는 제목
        sources: 찾을 곳. 비우면 블로그·웹문서 둘 다
        limit: 한 곳당 최대 건수
        start: 몇 번째 결과부터. 더 보려면 올린다
        sort: 'sim'(정확도순, 네이버 화면 기본) 또는 'date'(최신순)

    Returns:
        {"items": [...], "by_source": {...}, "next_start": int|None,
         "error": str|None}
    """
    if not is_configured(user_settings):
        return {"items": [], "by_source": {},
                "error": "네이버 검색 API 키가 없습니다 — 설정에서 등록하세요"}
    text = (query or "").strip()
    if len(text) < 2:
        return {"items": [], "by_source": {}, "error": "검색어가 너무 짧습니다"}

    picked = [s for s in (sources or [SRC_BLOG, SRC_WEBKR])
              if s in ENDPOINT]
    groups: List[List[dict]] = []
    by_source: Dict[str, int] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for code in picked:
            rows = await _fetch(user_settings, text, code, limit, client,
                                start, sort=sort)
            by_source[code] = len(rows)
            groups.append(rows)
            await asyncio.sleep(CALL_DELAY)

    items = _weave(groups)
    got = max((len(g) for g in groups), default=0)
    nxt = start + limit if got >= limit and start + limit <= MAX_START else None
    logger.info("[WEB_SOURCE] '%s' start=%s → %d건 %s",
                text, start, len(items), by_source)
    return {"items": items, "by_source": by_source, "next_start": nxt,
            "error": None if items else "검색 결과가 없습니다"}
