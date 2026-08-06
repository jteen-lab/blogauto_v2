"""애드센스 필수 페이지 4종 생성 오케스트레이션 (F1).

블로그의 플랫폼에 맞는 퍼블리셔로 4종 필수 페이지(개인정보처리방침/
이용약관/소개/문의)를 생성하고, Blog.required_page_ids /
required_pages_status를 갱신한다. 이미 생성된 페이지는 재실행 시
건너뛴다(멱등).

설계 문서: docs/flowcharts/adsense_sprint1_p1.md - F1
"""
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ...models.blog import Blog, BlogPlatform
from ...core.logger import get_logger
from .blogger_page_publisher import BloggerPagePublisher
from .publish_result import PublishResult
from .required_pages_templates import REQUIRED_PAGE_TYPES, build_required_pages

logger = get_logger("required_pages_service", "app.log")


class RequiredPagesService:
    """필수 페이지 4종 생성 서비스."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_all(self, blog: Blog, owner_email: str) -> Dict[str, Any]:
        """4종 필수 페이지를 생성하고 blog 상태를 갱신한다."""
        if blog.platform not in (BlogPlatform.BLOGGER, BlogPlatform.WORDPRESS):
            return {
                "success": False,
                "error": f"지원하지 않는 플랫폼: {blog.platform.value}",
                "results": {},
            }

        pages = build_required_pages(blog, owner_email)
        existing_ids = dict(blog.required_page_ids or {})
        results: Dict[str, dict] = {}

        for page_type in REQUIRED_PAGE_TYPES:
            if existing_ids.get(page_type):
                results[page_type] = {"success": True, "skipped": True}
                continue
            title, html = pages[page_type]
            outcome = await self._publish_one(blog, title, html)
            results[page_type] = {
                "success": outcome.success,
                "error": outcome.error,
                "url": outcome.published_url,
            }
            if outcome.success and outcome.platform_post_id:
                existing_ids[page_type] = outcome.platform_post_id

        blog.required_page_ids = existing_ids
        flag_modified(blog, "required_page_ids")
        blog.required_pages_status = self._compute_status(existing_ids)
        await self.db.commit()

        logger.info(
            "[REQUIRED_PAGES] 생성 완료 | blog=%s | status=%s | 결과=%s",
            blog.name, blog.required_pages_status, results,
        )
        return {
            "success": True,
            "status": blog.required_pages_status,
            "results": results,
        }

    async def _publish_one(
        self, blog: Blog, title: str, html: str,
    ) -> PublishResult:
        """플랫폼별 페이지 발행 위임."""
        if blog.platform == BlogPlatform.BLOGGER:
            return await BloggerPagePublisher().publish_page(blog, title, html)
        return await self._publish_wordpress_page(blog, title, html)

    async def _publish_wordpress_page(
        self, blog: Blog, title: str, html: str,
    ) -> PublishResult:
        """WordPress REST wp/v2/pages 발행."""
        from ..wordpress_api import WordPressAPI, WordPressAPIError

        result = PublishResult(success=False, platform="wordpress")
        try:
            async with WordPressAPI() as api:
                res = await api.create_page(blog, title, html)
            result.success = True
            result.published_url = res.get("remote_url", "")
            result.platform_post_id = res.get("remote_id")
        except WordPressAPIError as e:
            result.error = str(e.message)
            result.retryable = e.status_code is None or e.status_code >= 500
        except Exception as e:
            result.error = f"WordPress 페이지 생성 오류: {e}"
        return result

    @staticmethod
    def _compute_status(page_ids: Dict[str, str]) -> str:
        """생성된 페이지 수에 따라 required_pages_status 계산."""
        created = sum(1 for pt in REQUIRED_PAGE_TYPES if page_ids.get(pt))
        if created == 0:
            return "none"
        if created == len(REQUIRED_PAGE_TYPES):
            return "complete"
        return "partial"
