"""기존 발행 글을 검색 노출 원장에 채워 넣는다(백필).

원장은 기능 배포 이후 발행분만 쌓이므로, 색인율 기준선을 잡으려면 이미 발행된
글을 불러와야 한다. 최근 발행분부터 넣는다 — 오래된 글은 색인 여부를 지금 확인해도
해석하기 어렵고, GSC 일일 쿼터도 유한하기 때문이다.

백필된 행은 IndexNow 를 **제출하지 않는다**. 이미 발행된 URL 수천 건을 한꺼번에
제출하면 스팸으로 취급될 수 있고, 애초에 IndexNow 는 새 글 알림 수단이다.
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.crawled_post import CrawledPost
from ...models.search_visibility import IN_SKIPPED, SearchVisibilityUrl

logger = get_logger("search_visibility", "app.log")

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
# 백필 행의 indexnow_error 에 남기는 사유 — 실패와 구분된다.
REASON = "backfill(기존 발행분)"


async def backfill_blog(
    db: AsyncSession, blog_id: int, limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """블로그의 최근 발행 글을 원장에 채운다.

    Args:
        db: 세션
        blog_id: 대상 블로그
        limit: 가져올 최대 건수(최근 발행 순)

    Returns:
        {"scanned": 조회 건수, "created": 새로 넣은 건수, "existing": 이미 있던 건수}
    """
    capped = max(1, min(limit, MAX_LIMIT))

    stmt = (
        select(CrawledPost)
        .where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.published_at.isnot(None),
            CrawledPost.url.isnot(None),
        )
        .order_by(CrawledPost.published_at.desc())
        .limit(capped)
    )
    posts = list((await db.execute(stmt)).scalars().all())
    if not posts:
        return {"scanned": 0, "created": 0, "existing": 0}

    urls = [post.url for post in posts if post.url]
    known = set(
        (
            await db.execute(
                select(SearchVisibilityUrl.url).where(
                    SearchVisibilityUrl.blog_id == blog_id,
                    SearchVisibilityUrl.url.in_(urls),
                ),
            )
        ).scalars().all()
    )

    created = 0
    for post in posts:
        if not post.url or post.url in known:
            continue
        db.add(
            SearchVisibilityUrl(
                blog_id=blog_id,
                crawled_post_id=post.id,
                url=post.url[:1000],
                title=(post.title or "")[:500] or None,
                published_at=post.published_at,
                indexnow_status=IN_SKIPPED,
                indexnow_error=REASON,
            ),
        )
        known.add(post.url)
        created += 1

    await db.flush()
    logger.info(
        "[SEARCH_VIS] 백필 | blog_id=%s | 조회 %d | 신규 %d",
        blog_id, len(posts), created,
    )
    return {
        "scanned": len(posts),
        "created": created,
        "existing": len(posts) - created,
    }
