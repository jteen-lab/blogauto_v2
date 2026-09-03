"""대량 수집 Phase 1 — URL탭(수집 모듈 DB)에서 블로그를 골라 사이트맵 적재.

`url_source_mode == "from_collect_module"` 의 신규 Phase 1 구현.

동작:
    1. `collected_urls` 의 블로그 URL(소스: source_module_id IS NULL, 활성)을
       BulkCollectProgress 기준(미크롤/오래된 순)으로 blogs_per_cycle 개 선택.
    2. 각 블로그의 sitemap.xml 을 크롤해 포스트 URL 목록을 얻는다.
    3. 이미 이 모듈이 적재한 URL(dedup)을 제외한 **신규 글만** blog 당
       posts_per_blog 개까지 `collected_urls(source_module_id=모듈ID, pending)` 로 적재.
       → dedup 기반이라 재크롤 시 신규 글만 추가된다(D-2).
    4. BulkCollectProgress 의 last_cycle_at 을 갱신(다음 블로그 선택 우선순위용).

외부 진입점: ingest_from_url_tab(db, module_id, blogs_per_cycle, posts_per_blog, timebox)
"""
from __future__ import annotations

import logging
from typing import List, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bulk_collect_progress import BulkCollectProgress
from app.models.collected_url import CollectedUrl
from app.services.bulk_collect.lastmod_tracker import LastmodTracker
from app.services.title_collect.sitemap import SitemapParser
from app.services.bulk_collect.timebox import Timebox
from app.services.bulk_collect.url_utils import (
    extract_domain_safe,
    guess_platform,
)

logger = logging.getLogger(__name__)

__all__ = ["ingest_from_url_tab"]


async def ingest_from_url_tab(
    db: AsyncSession,
    module_id: int,
    blogs_per_cycle: int,
    posts_per_blog: int,
    timebox: Timebox,
) -> dict:
    """URL탭 블로그를 골라 사이트맵에서 신규 포스트 URL을 적재한다.

    Args:
        db: AsyncSession.
        module_id: 대량 수집 모듈 ID.
        blogs_per_cycle: 한 사이클에 크롤할 블로그 수.
        posts_per_blog: 블로그당 적재할 신규 포스트 상한.
        timebox: 사이클 타임박스.

    Returns:
        {"blogs_processed", "posts_ingested", "skipped_duplicate", "failed"}.
    """
    summary = {
        "blogs_processed": 0,
        "posts_ingested": 0,
        "skipped_duplicate": 0,
        "failed": 0,
    }
    blogs = await _select_blogs(db, module_id, blogs_per_cycle)
    if not blogs:
        logger.info(
            "[BULK_COLLECT:P1] URL탭에 크롤할 블로그 없음 module=%s", module_id,
        )
        return summary

    parser = SitemapParser()
    tracker = LastmodTracker(db)
    for blog in blogs:
        if timebox.expired:
            logger.warning("[BULK_COLLECT:P1] 타임박스 만료 → Phase1 중단")
            break
        await _crawl_one_blog(
            db, module_id, blog, posts_per_blog,
            parser, tracker, summary, timebox,
        )
    return summary


async def _select_blogs(
    db: AsyncSession, module_id: int, limit: int,
) -> List[CollectedUrl]:
    """URL탭(NULL 풀, 활성) 블로그를 미크롤/오래된 순으로 선택."""
    if limit <= 0:
        return []
    progress = BulkCollectProgress
    stmt = (
        select(CollectedUrl)
        .outerjoin(
            progress,
            (progress.module_id == module_id)
            & (progress.blog_domain == CollectedUrl.domain),
        )
        .where(CollectedUrl.source_module_id.is_(None))
        .where(CollectedUrl.is_active.is_(True))
        .order_by(
            progress.last_cycle_at.asc().nulls_first(),
            CollectedUrl.id.asc(),
        )
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def _existing_post_urls(
    db: AsyncSession, module_id: int, domain: str,
) -> Set[str]:
    """이 모듈이 해당 도메인에 이미 적재한 포스트 URL 집합(dedup용)."""
    rows = (
        await db.execute(
            select(CollectedUrl.url).where(
                CollectedUrl.source_module_id == module_id,
                CollectedUrl.domain == domain,
            )
        )
    ).scalars().all()
    return set(rows)


async def _crawl_one_blog(
    db: AsyncSession,
    module_id: int,
    blog: CollectedUrl,
    posts_per_blog: int,
    parser: SitemapParser,
    tracker: LastmodTracker,
    summary: dict,
    timebox: Timebox,
) -> None:
    """블로그 1개의 사이트맵을 크롤해 신규 포스트 URL을 적재(+진행 기록)."""
    domain = (blog.domain or extract_domain_safe(blog.url)).strip().lower()
    if not domain:
        summary["failed"] += 1
        return
    # 메모리 보호: 필요 수의 배수까지만 사이트맵에서 가져옴(신규 우선 상위)
    max_fetch = max(posts_per_blog * 10, 200)
    try:
        post_urls = await parser.fetch_urls(domain, max_urls=max_fetch)
        summary["blogs_processed"] += 1
        ingested = _stage_new_posts(
            db, module_id, domain, post_urls,
            await _existing_post_urls(db, module_id, domain),
            posts_per_blog, summary, timebox,
        )
        # 적재분 + 진행상태(last_cycle_at)를 함께 커밋
        await tracker.record_cycle_stats(
            module_id=module_id, blog_domain=domain,
            duration_sec=0, processed=ingested, failed=0,
        )
        logger.info(
            "[BULK_COLLECT:P1] domain=%s sitemap=%d 신규적재=%d",
            domain, len(post_urls), ingested,
        )
    except Exception as exc:  # noqa: BLE001
        summary["failed"] += 1
        logger.warning(
            "[BULK_COLLECT:P1] 블로그 크롤 실패 domain=%s err=%s", domain, exc,
        )
        await db.rollback()


def _stage_new_posts(
    db: AsyncSession,
    module_id: int,
    domain: str,
    post_urls: List[str],
    existing: Set[str],
    posts_per_blog: int,
    summary: dict,
    timebox: Timebox,
) -> int:
    """신규 포스트 URL을 세션에 추가(중복/캡/타임박스 적용). 적재 수 반환."""
    ingested = 0
    platform = guess_platform(domain)
    for purl in post_urls:
        if timebox.expired or ingested >= posts_per_blog:
            break
        url = (purl or "").strip()[:500]
        if not url:
            continue
        if url in existing:
            summary["skipped_duplicate"] += 1
            continue
        db.add(
            CollectedUrl(
                url=url,
                domain=domain,
                platform=platform,
                source_module_id=module_id,
                title_fetch_status="pending",
                is_active=True,
            )
        )
        existing.add(url)
        ingested += 1
        summary["posts_ingested"] += 1
    return ingested
