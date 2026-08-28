"""주기 점검 실행 — S2 사이트맵 신선도, S6 색인 상태.

스케줄러와 수동 실행(라우터) 양쪽에서 같은 함수를 쓴다.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.search_visibility import (
    IX_ERROR, IX_INDEXED, IX_NOT_INDEXED, IX_UNKNOWN,
    SM_MISSING, SM_PRESENT, SM_UNKNOWN, SearchVisibilityUrl, utcnow,
)
from . import index_check_service, sitemap_service
from .config import load_config

logger = get_logger("search_visibility", "app.log")

# 발행 직후에는 사이트맵에 없는 게 정상이므로 이만큼 지난 것만 본다.
SITEMAP_GRACE_MINUTES = 30
# 색인은 더 오래 걸린다.
INDEX_GRACE_DAYS = 3
# 한 번에 처리할 최대 행 수(사이트맵은 1회 fetch로 여러 건을 처리한다)
SITEMAP_BATCH = 200


async def _pending_sitemap_rows(
    db: AsyncSession, blog_id: int, limit: int = SITEMAP_BATCH,
) -> List[SearchVisibilityUrl]:
    """사이트맵 확인이 필요한 행을 고른다."""
    cutoff = utcnow() - timedelta(minutes=SITEMAP_GRACE_MINUTES)
    stmt = (
        select(SearchVisibilityUrl)
        .where(
            SearchVisibilityUrl.blog_id == blog_id,
            SearchVisibilityUrl.sitemap_state.in_([SM_UNKNOWN, SM_MISSING]),
            SearchVisibilityUrl.published_at <= cutoff,
        )
        .order_by(SearchVisibilityUrl.published_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def run_sitemap_check(db: AsyncSession, blog: Any) -> Dict[str, Any]:
    """블로그 사이트맵을 1회 읽어 대기 중인 URL들의 포함 여부를 갱신한다."""
    config = load_config(blog)
    if not config.get("sitemap_check_enabled"):
        return {"skipped": "disabled"}

    rows = await _pending_sitemap_rows(db, blog.id)
    if not rows:
        return {"checked": 0}

    snapshot = await sitemap_service.fetch_sitemap_urls(blog, config)
    if not snapshot.ok:
        logger.warning(
            "[SEARCH_VIS] 사이트맵 조회 실패 | blog=%s | %s", blog.name, snapshot.error,
        )
        return {"error": snapshot.error, "checked": 0}

    now = utcnow()
    present = missing = 0
    for row in rows:
        row.sitemap_checked_at = now
        if sitemap_service.contains(snapshot, row.url):
            row.sitemap_state = SM_PRESENT
            row.sitemap_miss_streak = 0
            present += 1
        else:
            row.sitemap_state = SM_MISSING
            row.sitemap_miss_streak = (row.sitemap_miss_streak or 0) + 1
            missing += 1

    await db.flush()
    return {
        "checked": len(rows),
        "present": present,
        "missing": missing,
        "sitemap_url": snapshot.source_url,
        "latest_lastmod": snapshot.latest_lastmod,
        "stale_days": sitemap_service.stale_days(snapshot),
    }


async def resolve_gsc_token(db: AsyncSession) -> Optional[str]:
    """저장된 refresh token으로 Search Console access token을 얻는다."""
    from ...core.encryption import decrypt_api_key
    from ..publishing.google_oauth_helper import refresh_access_token
    from ..system_settings_service import SystemSettingsService

    encrypted = await SystemSettingsService.get(
        index_check_service.SETTING_GSC_REFRESH_TOKEN, db,
    )
    if not encrypted:
        return None
    try:
        refresh_token = decrypt_api_key(encrypted)
    except Exception:  # noqa: BLE001
        logger.error("[SEARCH_VIS] GSC refresh token 복호화 실패")
        return None
    return await refresh_access_token(refresh_token)


async def _pending_index_rows(
    db: AsyncSession, blog_id: int, limit: int,
) -> List[SearchVisibilityUrl]:
    """색인 점검이 필요한 행을 고른다(미확인 우선, 오래된 확인 순)."""
    cutoff = utcnow() - timedelta(days=INDEX_GRACE_DAYS)
    stmt = (
        select(SearchVisibilityUrl)
        .where(
            SearchVisibilityUrl.blog_id == blog_id,
            SearchVisibilityUrl.index_state.in_(
                [IX_UNKNOWN, IX_NOT_INDEXED, IX_ERROR],
            ),
            SearchVisibilityUrl.published_at <= cutoff,
        )
        .order_by(
            SearchVisibilityUrl.index_checked_at.asc().nullsfirst(),
            SearchVisibilityUrl.published_at.desc(),
        )
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def run_index_check(
    db: AsyncSession,
    blog: Any,
    token: Optional[str] = None,
    sites: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """URL Inspection API로 색인 상태를 갱신한다.

    Args:
        db: 세션
        blog: 대상 블로그
        token: 미리 받아둔 access token(없으면 새로 발급)
        sites: 미리 조회한 Search Console 속성 목록(없으면 여기서 조회)
    """
    config = load_config(blog)
    if not config.get("index_check_enabled"):
        return {"skipped": "disabled"}

    access_token = token or await resolve_gsc_token(db)
    if not access_token:
        return {"skipped": "gsc_not_connected"}

    if sites is None:
        try:
            sites = await index_check_service.list_sites(access_token)
        except index_check_service.IndexCheckError as exc:
            return {"skipped": "sites_list_failed", "error": exc.message}

    site_url = index_check_service.resolve_property(sites, blog)
    if not site_url:
        # 속성이 없으면 URL Inspection 은 403 만 반환한다 — 시도하지 않고 사유를 알린다.
        return {"skipped": "property_not_found", "owned_properties": len(sites)}

    cap = int(config.get("index_check_daily_cap") or 20)
    rows = await _pending_index_rows(db, blog.id, cap)
    if not rows:
        return {"checked": 0}

    now = utcnow()
    indexed = not_indexed = errors = 0
    for row in rows:
        row.index_checked_at = now
        try:
            result = await index_check_service.inspect_url(
                access_token, row.url, site_url,
            )
            is_indexed, detail = index_check_service.interpret(result)
            row.index_detail = detail
            row.index_state = IX_INDEXED if is_indexed else IX_NOT_INDEXED
            indexed += int(is_indexed)
            not_indexed += int(not is_indexed)
        except index_check_service.IndexCheckError as exc:
            row.index_state = IX_ERROR
            row.index_detail = {"error": exc.message, "status": exc.status_code}
            errors += 1
            # 권한·속성 문제면 나머지도 같은 이유로 실패한다.
            if exc.status_code in (401, 403):
                break

    await db.flush()
    return {
        "checked": len(rows), "indexed": indexed,
        "not_indexed": not_indexed, "errors": errors, "property": site_url,
    }


async def blog_summary(db: AsyncSession, blog_id: int) -> Dict[str, Any]:
    """블로그 1개의 노출 현황 집계(화면용)."""
    total = (
        await db.execute(
            select(func.count(SearchVisibilityUrl.id)).where(
                SearchVisibilityUrl.blog_id == blog_id,
            ),
        )
    ).scalar() or 0

    async def _count(column: Any, value: str) -> int:
        stmt = select(func.count(SearchVisibilityUrl.id)).where(
            SearchVisibilityUrl.blog_id == blog_id, column == value,
        )
        return (await db.execute(stmt)).scalar() or 0

    indexed = await _count(SearchVisibilityUrl.index_state, IX_INDEXED)
    checked = total - await _count(SearchVisibilityUrl.index_state, IX_UNKNOWN)
    missing = await _count(SearchVisibilityUrl.sitemap_state, SM_MISSING)

    return {
        "total": total,
        "indexed": indexed,
        "index_checked": checked,
        "index_rate": round(indexed / checked * 100, 1) if checked else None,
        "sitemap_missing": missing,
        "indexnow_ok": await _count(SearchVisibilityUrl.indexnow_status, "ok"),
        "indexnow_failed": await _count(SearchVisibilityUrl.indexnow_status, "failed"),
    }
