"""디스패치 시점에 처리 대상 제목/포스트를 미리 결정하는 헬퍼.

큐 등록 → 워커 → 작업 완료까지 동일한 제목/포스트가 사용되도록
peek 시점에 ID를 결정한 뒤 dispatcher에 명시 전달하고, 워커가 그 ID를
강제 사용하도록 한다. 결정성을 보장하기 위한 단일 진실 공급원.

각 함수는 (title, id) 튜플을 반환한다. 사용 가능 대상이 없으면
("", 0)을 반환하여 호출자가 큐 등록을 skip하도록 신호한다.
"""
import logging
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def peek_next_generate_title(
    db: AsyncSession,
    blog_id: int,
    module_settings: Optional[dict] = None,
) -> Tuple[str, int]:
    """다음 생성 대상 MainTitle을 결정하고 (title, id)를 반환한다.

    Returns:
        (title, title_id). 사용 가능 제목이 없으면 ("", 0).
    """
    try:
        from .inventory_trigger import InventoryTrigger
        trigger = InventoryTrigger(db)
        title = await trigger._find_available_title(blog_id, module_settings)
        if title:
            return (title.title, title.id)
        return ("", 0)
    except Exception as exc:
        logger.debug(f"[PEEK_TITLE] generate peek 실패 | blog={blog_id} | {exc}")
        return ("", 0)


async def peek_next_publish_post(
    db: AsyncSession, blog_id: int,
) -> Tuple[str, int]:
    """다음 발행 대상 CrawledPost를 결정하고 (title, id)를 반환한다.

    Returns:
        (post_title, post_id). 발행 대상이 없으면 ("", 0).
    """
    try:
        from .inventory_manager import InventoryManager
        mgr = InventoryManager(db)
        post = await mgr.get_post_for_publish(blog_id)
        if post:
            return (getattr(post, "title", "") or "", post.id)
        return ("", 0)
    except Exception as exc:
        logger.debug(f"[PEEK_TITLE] publish peek 실패 | blog={blog_id} | {exc}")
        return ("", 0)


# 하위 호환: 기존 호출자가 title 문자열만 기대할 수 있으므로 wrapper 제공.
# 신규 코드는 위 두 함수(튜플 반환)를 직접 사용한다.
async def peek_next_publish_title(db: AsyncSession, blog_id: int) -> str:
    """하위 호환 wrapper. 신규 코드는 peek_next_publish_post 사용 권장."""
    title, _ = await peek_next_publish_post(db, blog_id)
    return title


async def peek_next_republish_title(
    db: AsyncSession, blog_id: int,
) -> str:
    """다음 재발행 대상 글의 제목을 결정한다 (큐 등록 로그용).

    WordPress/Blogger 플랫폼의 가장 오래된 글 제목을 가져온다.
    실패 시 빈 문자열을 반환해 호출자가 정상적으로 dispatch를 진행하도록 한다.
    Celery 워커는 자체적으로 재조회하므로 결정성 보장용이 아닌 표시용이다.

    Returns:
        post_title 문자열. 조회 실패/대상 없음 시 "".
    """
    try:
        from app.models.blog import Blog, BlogPlatform
        blog = await db.get(Blog, blog_id)
        if not blog:
            return ""
        if blog.platform == BlogPlatform.WORDPRESS:
            from app.services.wordpress_service import (
                WordPressRepublishService,
            )
            service = WordPressRepublishService()
            post = await service.get_oldest_post(blog)
            return (post or {}).get("title", "") or ""
        if blog.platform == BlogPlatform.BLOGGER:
            if not blog.google_credential_id:
                return ""
            from app.models.google_credential import GoogleCredential
            cred = await db.get(GoogleCredential, blog.google_credential_id)
            if not cred:
                return ""
            from app.services.blogger_service import (
                BloggerRepublishService,
            )
            service = BloggerRepublishService()
            blogger_id = await service.get_blog_id(blog, cred)
            if not blogger_id:
                return ""
            post = await service.get_oldest_post(blog, cred, blogger_id)
            return (post or {}).get("title", "") or ""
        return ""
    except Exception as exc:
        logger.debug(
            f"[PEEK_TITLE] republish peek 실패 | blog={blog_id} | {exc}"
        )
        return ""
