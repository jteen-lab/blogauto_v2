"""4-2-B 증분 적재 모듈 (lastmod_only_after_first).

`bulk_params.lastmod_only_after_first=True` 이고 첫 사이클이 아닌 경우,
sitemap.xml 의 `<lastmod>` 값을 `BulkCollectProgress.last_seen_lastmod` 와
비교하여 새로 갱신된 URL 만 적재한다.

외부 진입점: ingest_blog_url_incremental(...)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_collect.lastmod_tracker import LastmodTracker
from app.services.bulk_collect.sitemap_parser import SitemapParser
from app.services.bulk_collect.timebox import Timebox

logger = logging.getLogger(__name__)

__all__ = [
    "ingest_blog_url_incremental",
    "parse_lastmod_str",
    "to_aware_utc",
    "filter_new_pairs",
]


def parse_lastmod_str(lastmod_raw: Optional[str]) -> Optional[datetime]:
    """사이트맵 lastmod 문자열을 datetime 으로 안전 파싱.

    Args:
        lastmod_raw: 사이트맵 <lastmod> 원본 문자열.

    Returns:
        파싱 성공 시 timezone-aware datetime, 실패/None 시 None.
    """
    if not lastmod_raw:
        return None
    try:
        # ISO 8601 (예: 2026-05-26T10:00:00+00:00 또는 ...Z)
        cleaned = lastmod_raw.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            # naive → UTC 로 간주
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[BULK_COLLECT:INGEST] lastmod 파싱 실패 raw=%r err=%s",
            lastmod_raw, exc,
        )
        return None


def to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """비교용으로 datetime 을 UTC aware 로 정규화.

    Args:
        dt: 입력 datetime.

    Returns:
        UTC aware datetime 또는 None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def filter_new_pairs(
    pairs: list,
    since_utc: Optional[datetime],
) -> Tuple[list, Optional[datetime]]:
    """lastmod 페어 목록에서 since_utc 이후 항목만 추출.

    Args:
        pairs: [(url, lastmod_str_or_none), ...]
        since_utc: 직전 사이클의 last_seen_lastmod (UTC aware).

    Returns:
        (new_urls, max_lastmod_seen_utc).
        lastmod 가 None 인 항목은 비교 불가 → since_utc 가 None 일 때만 포함.
    """
    new_urls: list = []
    max_lastmod: Optional[datetime] = None
    for url, lastmod_raw in pairs:
        lm = parse_lastmod_str(lastmod_raw)
        lm_utc = to_aware_utc(lm)
        # 최대값 추적
        if lm_utc is not None and (
            max_lastmod is None or lm_utc > max_lastmod
        ):
            max_lastmod = lm_utc
        # 필터: since_utc 가 없으면 전체 포함, 있으면 그 이후 항목만
        if since_utc is None:
            new_urls.append(url)
            continue
        if lm_utc is None:
            # lastmod 불명 → 보수적으로 스킵 (재적재 방지)
            continue
        if lm_utc > since_utc:
            new_urls.append(url)
    return new_urls, max_lastmod


async def _fetch_sitemap_pairs_safe(
    sitemap_parser: SitemapParser,
    domain: str,
    summary: dict,
) -> Optional[list]:
    """사이트맵에서 (url, lastmod) 페어 목록을 안전하게 조회 (실패 시 None)."""
    try:
        return await sitemap_parser.fetch_url_lastmod_pairs(
            domain, max_pairs=None,
        )
    except Exception as exc:  # noqa: BLE001
        summary["failed"] += 1
        logger.warning(
            "[BULK_COLLECT:INGEST] lastmod 페어 조회 실패 "
            "domain=%s err=%s", domain, exc,
        )
        return None


async def _safe_update_last_seen(
    tracker: LastmodTracker,
    module_id: int,
    domain: str,
    max_lastmod: Optional[datetime],
) -> None:
    """LastmodTracker 갱신을 안전하게 수행 (실패 시 로그만)."""
    if max_lastmod is None:
        return
    try:
        await tracker.update_last_seen(
            module_id=module_id,
            blog_domain=domain,
            lastmod=max_lastmod,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[BULK_COLLECT:INGEST] last_seen 갱신 실패 "
            "domain=%s err=%s", domain, exc,
        )


async def ingest_blog_url_incremental(
    db: AsyncSession,
    module_id: int,
    domain: str,
    sitemap_parser: SitemapParser,
    tracker: LastmodTracker,
    summary: dict,
    timebox: Timebox,
    ingest_blog_posts_fn,
) -> None:
    """4-2-B 증분 적재: lastmod > last_seen_lastmod 인 URL 만 적재.

    1) 직전 last_seen_lastmod 조회 2) (url, lastmod) 페어 조회
    3) since 이후 항목 필터링 4) 최대 lastmod 로 tracker 갱신.

    Args:
        ingest_blog_posts_fn: URL 리스트 적재용 콜백 (순환 import 회피).
    """
    last_seen = await tracker.get_last_seen(module_id, domain)
    last_seen_utc = to_aware_utc(last_seen)
    pairs = await _fetch_sitemap_pairs_safe(
        sitemap_parser, domain, summary,
    )
    if pairs is None:
        return
    if not pairs:
        logger.info(
            "[BULK_COLLECT:INGEST] 증분 적재 — 사이트맵 비어있음 domain=%s",
            domain,
        )
        return
    summary["blogs_processed"] += 1
    new_urls, max_lastmod = filter_new_pairs(pairs, last_seen_utc)
    logger.info(
        "[BULK_COLLECT:INGEST] 증분 적재 domain=%s sitemap=%d new=%d "
        "since=%s",
        domain, len(pairs), len(new_urls), last_seen_utc,
    )
    # 변경된 URL 이 없으면 적재 스킵하되 last_seen 은 유지
    if not new_urls:
        summary["skipped_unchanged"] += len(pairs)
        return
    await ingest_blog_posts_fn(
        db=db, module_id=module_id, domain=domain,
        post_urls=new_urls, summary=summary, timebox=timebox,
    )
    await _safe_update_last_seen(tracker, module_id, domain, max_lastmod)
