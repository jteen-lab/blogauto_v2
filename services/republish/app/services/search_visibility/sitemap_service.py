"""S2 — 사이트맵 신선도 점검.

발행한 URL이 사이트맵에 실제로 들어갔는지 확인한다. 구글은 2023년 sitemap ping을
폐지하고 `lastmod` 를 크롤 스케줄 신호로 쓰기 때문에, 사이트맵이 늦으면 발견도 늦다.

실측 근거: doooit082.com 사이트맵이 2026-08-20에 멈춰 8/22 발행분이 누락돼 있었다.
"""
from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional, Set
from xml.etree import ElementTree

import httpx

from .config import blog_host, load_config, platform_of

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0
# 인덱스 사이트맵에서 따라갈 하위 사이트맵 최대 개수(최신 것 우선)
MAX_CHILD_SITEMAPS = 5
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# 플랫폼별 사이트맵 추정 경로(앞에서부터 시도)
CANDIDATE_PATHS = {
    "wordpress": ["/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"],
    "blogger": ["/sitemap.xml"],
    "other": ["/sitemap.xml", "/sitemap_index.xml"],
}


@dataclass
class SitemapSnapshot:
    """사이트맵 1회 조회 결과."""

    ok: bool
    source_url: Optional[str] = None
    urls: Set[str] = field(default_factory=set)
    latest_lastmod: Optional[str] = None
    error: Optional[str] = None


def candidate_sitemap_urls(blog: Any, config: Optional[dict] = None) -> List[str]:
    """조회할 사이트맵 주소 후보를 순서대로 만든다."""
    cfg = config if config is not None else load_config(blog)
    manual = (cfg.get("sitemap_url") or "").strip()
    if manual:
        return [manual]

    host = blog_host(blog)
    if not host:
        return []
    paths = CANDIDATE_PATHS.get(platform_of(blog), CANDIDATE_PATHS["other"])
    return [f"https://{host}{path}" for path in paths]


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    """사이트맵 본문을 가져온다. 실패하면 None."""
    try:
        response = await client.get(url)
    except Exception as exc:
        logger.debug("[SITEMAP] fetch 실패 | %s | %s", url, exc)
        return None
    if response.status_code != 200:
        return None
    body = response.content
    if url.endswith(".gz"):
        try:
            body = gzip.decompress(body)
        except Exception:
            return None
    return body


def _parse(body: bytes) -> tuple[List[str], List[str], Optional[str]]:
    """사이트맵 XML을 파싱한다.

    Returns:
        (하위 사이트맵 주소, URL 목록, 가장 최근 lastmod)
    """
    try:
        root = ElementTree.fromstring(body)
    except Exception:
        return [], [], None

    lastmods: List[str] = []
    children: List[str] = []
    urls: List[str] = []

    for node in root.findall(f"{SITEMAP_NS}sitemap"):
        loc = node.findtext(f"{SITEMAP_NS}loc")
        if loc:
            children.append(loc.strip())
        mod = node.findtext(f"{SITEMAP_NS}lastmod")
        if mod:
            lastmods.append(mod.strip())

    for node in root.findall(f"{SITEMAP_NS}url"):
        loc = node.findtext(f"{SITEMAP_NS}loc")
        if loc:
            urls.append(loc.strip())
        mod = node.findtext(f"{SITEMAP_NS}lastmod")
        if mod:
            lastmods.append(mod.strip())

    return children, urls, (max(lastmods) if lastmods else None)


async def fetch_sitemap_urls(blog: Any, config: Optional[dict] = None) -> SitemapSnapshot:
    """블로그 사이트맵을 읽어 URL 집합을 만든다.

    인덱스 사이트맵이면 하위 사이트맵을 최대 MAX_CHILD_SITEMAPS 개까지 따라간다.
    """
    candidates = candidate_sitemap_urls(blog, config)
    if not candidates:
        return SitemapSnapshot(ok=False, error="사이트맵 주소를 만들 수 없습니다")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        for candidate in candidates:
            body = await _fetch(client, candidate)
            if body is None:
                continue

            children, urls, lastmod = _parse(body)
            collected: Set[str] = set(urls)

            # 하위 사이트맵은 뒤쪽(최신)부터 본다 — 워드프레스는 오름차순이 흔하다.
            for child in list(reversed(children))[:MAX_CHILD_SITEMAPS]:
                child_body = await _fetch(client, child)
                if child_body is None:
                    continue
                _, child_urls, child_mod = _parse(child_body)
                collected.update(child_urls)
                if child_mod and (not lastmod or child_mod > lastmod):
                    lastmod = child_mod

            return SitemapSnapshot(
                ok=True, source_url=candidate, urls=collected, latest_lastmod=lastmod,
            )

    return SitemapSnapshot(
        ok=False,
        error=f"사이트맵을 찾지 못했습니다 (시도: {', '.join(candidates)})",
    )


def normalize(url: str) -> str:
    """비교용으로 URL 끝 슬래시와 공백을 정리한다."""
    return (url or "").strip().rstrip("/")


def contains(snapshot: SitemapSnapshot, url: str) -> bool:
    """사이트맵에 해당 URL이 들어 있는지 확인한다."""
    target = normalize(url)
    return any(normalize(item) == target for item in snapshot.urls)


def stale_days(snapshot: SitemapSnapshot) -> Optional[int]:
    """사이트맵 lastmod 가 며칠 전인지 계산한다. 알 수 없으면 None."""
    raw = snapshot.latest_lastmod
    if not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - parsed).days)
