"""고른 글의 본문을 가져온다 — 아무 사이트나 올 수 있다.

질문 본문(`question_body`)은 지식iN·카페 두 곳만 상대하면 됐다. 여기는
검색으로 나온 어떤 블로그·문서든 올 수 있어 더 넓게 뒤진다.

**고른 것만 가져온다.** 목록을 통째로 긁으면 느리고 차단 위험도 생긴다.

순서도: docs/flowcharts/workbench_web_sources.md
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from ...core.logger import get_logger

logger = get_logger("workbench_page_body", "app.log")

TIMEOUT = 12
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

#: 한 번에 받을 수 있는 최대 개수
MAX_LINKS = 5
#: 프롬프트를 잡아먹지 않게 자른다
BODY_MAX = 2000
#: 이보다 짧으면 못 가져온 것으로 친다. 차림표·꼬리말만 남은 경우다
MIN_CHARS = 200

#: 본문 자리를 아는 곳. 먼저 본다
KNOWN_SELECTORS = (
    ".se-main-container",          # 네이버 블로그 스마트에디터
    "#postViewArea",               # 네이버 옛 에디터
    ".tt_article_useless_p_margin",  # 티스토리
    ".article_view", ".entry-content", ".post-content", ".article-body",
    "#content .wrap_body",         # 브런치
    "article",
)

#: 걷어낼 것. 본문이 아니다
DROP_TAGS = ("script", "style", "nav", "header", "footer", "aside",
             "form", "noscript", "iframe")


def _text(node: Any) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def _strip_noise(soup: Any) -> None:
    for tag in soup(list(DROP_TAGS)):
        tag.decompose()


#: 이 비율보다 링크 글자가 많으면 차림표로 본다
LINK_RATIO = 0.35

#: 차림표에서만 나오는 말. 여러 번 나오면 본문이 아니다
NAV_WORDS = ("바로가기", "펼치기", "하위메뉴", "하위 메뉴", "메인메뉴",
             "전체메뉴", "보기/숨기기", "회원가입", "로그인", "이전글",
             "다음글", "목차 펼치기", "확장/축소")
#: 이만큼 나오면 차림표로 본다
NAV_HITS = 4


#: 이보다 문장이 드물면 글이 아니라 차림표로 본다(글자 수 기준)
CHARS_PER_SENTENCE = 260


def _nav_heavy(text: str) -> bool:
    """차림표인가.

    낱말 목록만으로는 끝이 없다. 사이트마다 메뉴 말이 다르기 때문이다.
    그래서 **문장다운지**를 함께 본다 — 글에는 맺는 문장이 줄줄이
    있지만 차림표는 짧은 말이 늘어설 뿐이다.
    """
    if sum(text.count(w) for w in NAV_WORDS) >= NAV_HITS:
        return True
    stops = sum(text.count(mark) for mark in ("다.", "요.", ". ", "?", "!"))
    return stops < (len(text) / CHARS_PER_SENTENCE)


def _link_heavy(node: Any, whole: str) -> bool:
    """링크 글자가 빽빽하면 본문이 아니라 차림표다.

    `바로가기 메인메뉴 바로가기 서브메뉴…` 같은 것이 본문으로 잡히면
    글감이 아니라 쓰레기가 프롬프트에 실린다.
    """
    if not whole:
        return True
    if _nav_heavy(whole):
        return True
    linked = sum(len(_text(a)) for a in node.find_all("a"))
    return (linked / len(whole)) > LINK_RATIO


def _longest_block(soup: Any) -> str:
    """본문 자리를 모를 때. 글이 가장 많이 몰린 덩어리를 고른다.

    링크가 빽빽한 덩어리는 건너뛴다.
    """
    best = ""
    for node in soup.find_all(["div", "section", "article", "main"]):
        got = _text(node)
        if len(got) <= len(best) or _link_heavy(node, got):
            continue
        best = got
    return best


def _extract(html: str) -> str:
    """페이지에서 본문만 뽑는다."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    for sel in KNOWN_SELECTORS:
        found = [n for n in soup.select(sel) if _text(n)]
        if not found:
            continue
        # 아는 자리라도 링크가 빽빽하면 차림표다. `article` 을 뼈대로
        # 쓰면서 안에 메뉴를 담는 곳이 있다.
        keep = [n for n in found if not _link_heavy(n, _text(n))]
        joined = " ".join(_text(n) for n in keep)
        if len(joined) >= MIN_CHARS:
            return joined[:BODY_MAX]
    return _longest_block(soup)[:BODY_MAX]


def _naver_blog_view(link: str, html: str) -> str:
    """네이버 블로그는 본문이 iframe 안에 있다. 그 주소를 만들어 준다.

    없으면 빈 문자열 — 그러면 받아 둔 페이지를 그대로 쓴다.
    """
    host = (urlparse(link).netloc or "").lower()
    if "blog.naver.com" not in host:
        return ""
    hit = re.search(r'id="mainFrame"[^>]*src="([^"]+)"', html)
    if hit:
        src = hit.group(1)
        return src if src.startswith("http") else "https://blog.naver.com" + src
    parts = [p for p in urlparse(link).path.split("/") if p]
    if len(parts) >= 2 and parts[1].isdigit():
        return ("https://blog.naver.com/PostView.naver?blogId="
                f"{parts[0]}&logNo={parts[1]}")
    return ""


async def _fetch_one(client: httpx.AsyncClient, link: str) -> Dict[str, Any]:
    """한 건. 실패해도 예외를 올리지 않는다 — 제목만으로도 글은 쓴다."""
    out = {"link": link, "question": "", "answer": "", "error": ""}
    try:
        resp = await client.get(link, headers={"User-Agent": UA})
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}"
            return out

        html = resp.text
        inner = _naver_blog_view(link, html)
        if inner:
            try:
                got = await client.get(inner, headers={"User-Agent": UA})
                if got.status_code == 200:
                    html = got.text
            except Exception:                          # noqa: BLE001
                pass                                   # 받아 둔 것으로 간다

        body = _extract(html)
        if len(body) < MIN_CHARS:
            out["error"] = "본문이 너무 짧습니다"
            return out
        if _nav_heavy(body):
            # 쓰레기를 프롬프트에 싣느니 못 가져온 것으로 둔다
            out["error"] = "본문 대신 차림표만 있는 쪽입니다"
            return out
        # 질문 검색과 같은 칸에 담는다 — 뒤쪽 길을 그대로 쓰기 위해서다
        out["question"] = body
    except Exception as e:                             # noqa: BLE001
        out["error"] = str(e)[:80]
        logger.warning("[PAGE_BODY] 실패 | %s | %s", link[:60], e)
    return out


async def fetch_bodies(links: List[str]) -> List[Dict[str, Any]]:
    """고른 글들의 본문. 순서는 준 것과 같다.

    Args:
        links: 글 주소 목록

    Returns:
        [{"link", "question", "answer", "error"}, ...]
    """
    picked = [l.strip() for l in (links or []) if (l or "").strip()][:MAX_LINKS]
    if not picked:
        return []
    async with httpx.AsyncClient(timeout=TIMEOUT,
                                 follow_redirects=True) as client:
        got = await asyncio.gather(
            *[_fetch_one(client, l) for l in picked],
            return_exceptions=True)
    out: List[Dict[str, Any]] = []
    for link, item in zip(picked, got):
        if isinstance(item, dict):
            out.append(item)
        else:
            out.append({"link": link, "question": "", "answer": "",
                        "error": "조회 실패"})
    ok = len([o for o in out if o.get("question")])
    logger.info("[PAGE_BODY] %d건 요청 · %d건 성공", len(picked), ok)
    return out
