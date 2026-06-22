"""재발행 리뉴얼 P4 — 저장 정리 (데이터 변경).

유예기간(delete_grace_days)이 지난 발행/리뉴얼 글의 본문(content_html)+이미지
파일을 삭제하고 경량 메타(제목/url/platform_post_id/날짜)는 보존한다. 리뉴얼은
라이브 글에서 fetch하므로 서버 저장본이 없어도 동작한다.

안전 규칙:
    - 나이기준 = COALESCE(last_renewed_at, published_at) 가 now - grace_days 이전.
    - platform_post_id 필수(라이브 글 존재 → 리뉴얼 재fetch 가능).
    - content_html 이 남아있는 글만(이미 정리된 글 재처리 방지: purged_at IS NULL).
    - 메타는 삭제하지 않음.
    - grace_days <= 0 이면 정리 비활성(no-op).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from dateutil.relativedelta import relativedelta  # noqa: F401  (주기 계산 일관성)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ..post_image_cleanup import delete_post_images

logger = get_logger("renewal_cleanup", "app.log")


async def cleanup_purged_posts(
    db: AsyncSession,
    blog: Blog,
    cfg: Dict[str, Any],
    limit: int = 50,
) -> Dict[str, int]:
    """유예 경과 글의 본문/이미지 정리. {posts, images} 정리 수 반환.

    Args:
        db: 비동기 DB 세션.
        blog: 대상 블로그.
        cfg: blog.renewal_config (delete_grace_days 사용).
        limit: 1회 처리 상한(과도한 부하 방지).

    Returns:
        {"posts": 정리한 글 수, "images": 삭제한 이미지 수}.
    """
    grace_days = int(cfg.get("delete_grace_days", 7) or 0)
    if grace_days <= 0:
        return {"posts": 0, "images": 0}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=grace_days)
    age_key = func.coalesce(
        CrawledPost.last_renewed_at, CrawledPost.published_at,
    )

    rows = (await db.execute(
        select(CrawledPost)
        .where(
            CrawledPost.blog_id == blog.id,
            CrawledPost.source == "generated",
            CrawledPost.published_at.isnot(None),
            CrawledPost.platform_post_id.isnot(None),
            CrawledPost.content_html.isnot(None),
            CrawledPost.purged_at.is_(None),
            age_key <= cutoff,
        )
        .order_by(age_key.asc())
        .limit(limit)
    )).scalars().all()

    if not rows:
        return {"posts": 0, "images": 0}

    posts = 0
    images = 0
    for post in rows:
        try:
            images += await delete_post_images(post, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RENEWAL_CLEANUP] 이미지 삭제 오류(계속) | post=%s | %s",
                post.id, exc,
            )
        post.content_html = None
        post.purged_at = now
        posts += 1

    await db.commit()
    logger.info(
        "[RENEWAL_CLEANUP] 정리 완료 | blog=%s | posts=%d | images=%d | grace=%dd",
        blog.name, posts, images, grace_days,
    )
    return {"posts": posts, "images": images}
