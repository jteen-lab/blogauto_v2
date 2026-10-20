"""O2. 주제별 공식 시작 주소 — 참고 자료 수집 때 먼저 읽는다.

슈마즈 시험(2026-10-20)에서 제목 6개 중 4개가 "공식 기관 주소 0건" 으로
보류됐다. 금감원·국세청 자료가 많은 주제인데 공식 쪽을 찾지 못한 것이다.
원인 두 가지:
  - 네이버 웹문서 검색은 블로그·언론 글을 먼저 준다.
  - 공식 누리집(www.nts.go.kr·www.fss.or.kr·hometax.go.kr 등)이 크롤 실패로
    도메인 차단 목록(domain_blacklist)에 올라 있다. 메뉴 글자가 앞쪽 5,000자를
    채워 본문이 잘리거나, 기관 첫 화면이라 내용이 없어서다.

그래서 모듈 설정 표(fact_gate.official_seeds)에 제목 낱말 → 공식 안내 페이지
주소를 적고, 검색과 별도로 **차단 목록을 거치지 않고** 직접 읽는다. 본문은
메뉴를 빼고 글자가 가장 빽빽한 덩어리를 쓴다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (O2)
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Sequence
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ...core.logger import get_logger
from ...schemas.reference_collection import CrawledDocument

logger = get_logger("official_seeds", "app.log")

MAX_SEEDS = 3
MIN_CHARS = 200
MAX_CHARS = 5000
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_DROP = ["script", "style", "nav", "header", "footer", "aside", "form",
         "iframe", "noscript"]


def urls_for(settings: Optional[dict], title: str) -> List[str]:
    """제목 낱말에 맞는 시작 주소(표 순서, 중복 없이 최대 MAX_SEEDS)."""
    cfg = (settings or {}).get("fact_gate") or {}
    rows = cfg.get("official_seeds") if isinstance(cfg, dict) else None
    out: List[str] = []
    text = (title or "").replace(" ", "")
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        words = [str(w).replace(" ", "") for w in row.get("keywords") or []]
        if any(w and w in text for w in words):
            out += [u for u in row.get("urls") or [] if u and u not in out]
    return out[:int(cfg.get("max_seeds", MAX_SEEDS) or MAX_SEEDS)]


def dense_text(html: str) -> str:
    """메뉴를 빼고 글자가 가장 빽빽한 덩어리의 글.

    링크 글자는 세 배로 깎는다 — 메뉴·바로가기 묶음이 뽑히지 않게.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(_DROP):
        tag.decompose()
    best, text = 0, ""
    for el in soup.find_all(["div", "section", "article", "main", "td"]):
        t = el.get_text(" ", strip=True)
        links = sum(len(a.get_text(strip=True)) for a in el.find_all("a"))
        score = len(t) - 3 * links
        if score > best:
            best, text = score, t
    return " ".join(text.split())


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[CrawledDocument]:
    """한 주소를 읽어 문서로. 실패하면 None(차단 목록에 올리지 않는다)."""
    try:
        r = await client.get(url)
    except Exception as e:  # noqa: BLE001
        logger.warning("[OFFICIAL_SEED] 읽기 실패 | %s | %s", url, e)
        return None
    text = dense_text(r.text) if r.status_code == 200 else ""
    if len(text) < MIN_CHARS:
        logger.warning("[OFFICIAL_SEED] 본문 부족 | %s | HTTP %s | %d자",
                       url, r.status_code, len(text))
        return None
    title = ""
    try:
        t = BeautifulSoup(r.text, "html.parser").find("title")
        title = (t.get_text(strip=True) if t else "")[:200]
    except Exception:  # noqa: BLE001
        pass
    return CrawledDocument(url=url, domain=urlparse(url).hostname or "",
                           title=title or None, content=text[:MAX_CHARS],
                           content_length=len(text))


async def fetch(urls: Sequence[str]) -> List[CrawledDocument]:
    """시작 주소들을 동시에 읽는다(실패한 주소는 빠진다)."""
    if not urls:
        return []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as client:
        docs = await asyncio.gather(*(_fetch(client, u) for u in urls))
    found = [d for d in docs if d]
    logger.info("[OFFICIAL_SEED] %d/%d건 읽음 | %s", len(found), len(urls),
                [d.url for d in found])
    return found


def merge(seed_docs: List[Any], documents: List[Any]) -> List[Any]:
    """시작 주소 문서를 앞에, 같은 주소의 검색 문서는 뺀다."""
    have = {getattr(d, "url", "") for d in seed_docs}
    return list(seed_docs) + [d for d in documents
                              if getattr(d, "url", "") not in have]


def pick(seed_docs: List[Any], documents: List[Any], count: int) -> List[Any]:
    """요약에 넣을 문서: 시작 주소 전부 + 나머지에서 count 개."""
    have = {getattr(d, "url", "") for d in seed_docs}
    rest = [d for d in documents if getattr(d, "url", "") not in have]
    return list(seed_docs) + rest[:max(1, count)]
