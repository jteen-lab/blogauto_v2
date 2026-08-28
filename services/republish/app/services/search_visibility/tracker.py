"""발행된 URL을 검색 노출 원장에 등록하고 IndexNow 제출까지 처리한다.

발행 파이프라인에서 호출되며, **여기서 무슨 일이 나도 발행 결과를 바꾸지 않는다**.
모든 예외를 삼키고 로그만 남긴다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.search_visibility import (
    IN_FAILED, IN_OK, IN_SKIPPED, SearchVisibilityUrl, utcnow,
)
from . import indexnow_service
from .config import load_config

logger = get_logger("search_visibility", "app.log")


async def get_or_create_row(
    db: AsyncSession,
    blog_id: int,
    url: str,
    *,
    crawled_post_id: Optional[int] = None,
    title: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> SearchVisibilityUrl:
    """(blog_id, url) 원장 행을 가져오거나 만든다(멱등)."""
    stmt = select(SearchVisibilityUrl).where(
        SearchVisibilityUrl.blog_id == blog_id,
        SearchVisibilityUrl.url == url,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        if crawled_post_id and not row.crawled_post_id:
            row.crawled_post_id = crawled_post_id
        if title and not row.title:
            row.title = title[:500]
        return row

    row = SearchVisibilityUrl(
        blog_id=blog_id,
        crawled_post_id=crawled_post_id,
        url=url[:1000],
        title=(title or "")[:500] or None,
        published_at=published_at or utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


def _apply_outcome(
    row: SearchVisibilityUrl, outcome: indexnow_service.SubmitOutcome,
) -> None:
    """IndexNow 결과를 원장 행에 반영한다."""
    row.indexnow_submitted_at = utcnow()
    row.indexnow_status_code = outcome.status_code
    row.indexnow_error = outcome.error

    if outcome.submitted:
        row.indexnow_status = IN_OK
    elif outcome.status_code is None and not outcome.retryable:
        # 제출을 아예 시도하지 않은 경우(비활성·키 미검증 등)
        row.indexnow_status = IN_SKIPPED
        row.indexnow_submitted_at = None
    else:
        row.indexnow_status = IN_FAILED
        row.indexnow_attempts = (row.indexnow_attempts or 0) + 1


async def track_published_url(
    db: AsyncSession,
    blog: Any,
    url: str,
    *,
    crawled_post_id: Optional[int] = None,
    title: Optional[str] = None,
) -> Optional[SearchVisibilityUrl]:
    """발행 성공 URL을 원장에 넣고, 설정이 켜져 있으면 IndexNow에 제출한다.

    Returns:
        생성/갱신된 원장 행. 실패하면 None(발행에는 영향 없음).
    """
    if not url:
        return None

    try:
        row = await get_or_create_row(
            db, blog.id, url, crawled_post_id=crawled_post_id, title=title,
        )
        config = load_config(blog)
        outcome = await indexnow_service.submit_url(blog, url, config)
        _apply_outcome(row, outcome)

        # 403 은 키 파일이 사라졌거나 바뀐 것이므로 검증 상태를 되돌린다.
        if outcome.invalidate_key:
            invalidate_key_verification(blog, outcome.error)

        await db.flush()
        return row
    except Exception as exc:  # noqa: BLE001 — 발행을 막지 않는다
        logger.warning(
            "[SEARCH_VIS] 원장 기록 실패(무시) | blog=%s | url=%s | %s",
            getattr(blog, "name", "?"), url, exc,
        )
        return None


def invalidate_key_verification(blog: Any, reason: Optional[str]) -> None:
    """IndexNow 키 검증 상태를 해제한다(설정 JSON 갱신)."""
    config = load_config(blog)
    config["indexnow_key_verified"] = False
    config["indexnow_key_error"] = reason or "키 파일 검증이 해제되었습니다"
    config["indexnow_key_checked_at"] = utcnow().isoformat()
    blog.search_index_config = config
