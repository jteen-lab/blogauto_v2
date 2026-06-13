"""
블로그 유효 발행 카운트 헬퍼 (GP 성장단계 판정용)

스케줄러가 GP 단계를 판정할 때 사용하는 카운트를, UI 표시(blog_service)와
동일하게 `max(blogs.total_post_count, 실제 DB 발행수)`로 통일한다.

배경: blogs.total_post_count가 발행 시 갱신되지 않아 NULL/구값인 블로그가 있어,
스케줄러가 실제보다 낮은 단계로 잘못 판정(예: 성장기 블로그를 급성장기로)했다.
실제 발행된 CrawledPost 수를 함께 고려해 표시 단계와 실행 단계를 일치시킨다.
"""
import logging
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost

logger = logging.getLogger(__name__)


async def build_effective_post_counts(
    db: AsyncSession, blogs: List[Blog]
) -> Dict[int, int]:
    """블로그별 유효 발행 카운트 = max(total_post_count, 실제 DB 발행수).

    Args:
        db: DB 세션
        blogs: 대상 블로그 목록

    Returns:
        {blog_id: effective_post_count}
    """
    if not blogs:
        return {}

    blog_ids = [b.id for b in blogs]
    rows = await db.execute(
        select(CrawledPost.blog_id, func.count(CrawledPost.id))
        .where(
            CrawledPost.blog_id.in_(blog_ids),
            CrawledPost.published_at.isnot(None),
        )
        .group_by(CrawledPost.blog_id)
    )
    published: Dict[int, int] = {bid: cnt for bid, cnt in rows.all()}

    result: Dict[int, int] = {}
    for b in blogs:
        stored = b.total_post_count or 0
        db_published = published.get(b.id, 0)
        result[b.id] = max(stored, db_published)
    return result
