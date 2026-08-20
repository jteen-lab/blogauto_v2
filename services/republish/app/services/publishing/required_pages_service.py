"""애드센스 필수 페이지 4종 생성/갱신/삭제 오케스트레이션 (F1).

블로그의 플랫폼에 맞는 퍼블리셔로 4종 필수 페이지(개인정보처리방침/
이용약관/소개/문의)를 생성하고, Blog.required_page_ids /
required_pages_status를 갱신한다. 이미 생성된 페이지는 재실행 시
최신 저자 프로필/연락처를 반영해 원격 콘텐츠를 덮어쓴다(재실행 안전).

설계 문서: docs/flowcharts/adsense_sprint1_p1.md - F1
"""
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ...models.blog import Blog, BlogPlatform
from ...core.logger import get_logger
from .blogger_page_publisher import BloggerPagePublisher
from .contact_form_provisioner import ensure_contact_form
from .publish_result import PublishResult
from .required_pages_templates import REQUIRED_PAGE_TYPES, build_required_pages

logger = get_logger("required_pages_service", "app.log")


class RequiredPagesService:
    """필수 페이지 4종 생성 서비스."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_all(
        self,
        blog: Blog,
        owner_email: str,
        *,
        preset_code: Optional[str] = None,
        overrides: Optional[Dict[str, str]] = None,
        contact_template: Optional[Dict[str, Any]] = None,
        contact_design: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """4종 필수 페이지를 생성하거나(신규) 최신 내용으로 갱신(기존)하고
        blog 상태를 갱신한다.

        Args:
            preset_code: 필수페이지 문체 프리셋(없으면 표준)
            overrides: {page_type: 편집된 body} — 있으면 프리셋 본문 대신 사용
            contact_template: 문의폼 필드 템플릿(모듈 설정 연동)
            contact_design: 문의폼 디자인 프리셋(모듈 설정 연동)
        """
        if blog.platform not in (BlogPlatform.BLOGGER, BlogPlatform.WORDPRESS):
            return {
                "success": False,
                "error": f"지원하지 않는 플랫폼: {blog.platform.value}",
                "results": {},
            }

        # F10: 문의 폼 자동 생성(폼 계정 설정 시). 실패/미설정이면 mailto 폴백.
        # 이 서비스가 문의폼 생성을 소유(모듈 디스패치는 generate_all만 호출) → 중복 방지.
        await ensure_contact_form(
            blog, self.db, template=contact_template, design=contact_design
        )

        pages = build_required_pages(blog, owner_email, preset_code, overrides)
        existing_ids = dict(blog.required_page_ids or {})
        results: Dict[str, dict] = {}

        for page_type in REQUIRED_PAGE_TYPES:
            title, html = pages[page_type]
            page_id = existing_ids.get(page_type)
            if page_id:
                outcome = await self._update_one(blog, page_id, title, html)
            else:
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
            "[REQUIRED_PAGES] 생성/갱신 완료 | blog=%s | status=%s | 결과=%s",
            blog.name, blog.required_pages_status, results,
        )
        return {
            "success": True,
            "status": blog.required_pages_status,
            "page_ids": existing_ids,
            "results": results,
        }

    async def delete_all(self, blog: Blog) -> Dict[str, Any]:
        """생성된 필수 페이지 4종을 원격 플랫폼에서 삭제하고 상태를 초기화한다."""
        existing_ids = dict(blog.required_page_ids or {})
        results: Dict[str, dict] = {}

        for page_type, page_id in list(existing_ids.items()):
            if not page_id:
                continue
            outcome = await self._delete_one(blog, page_id)
            results[page_type] = {"success": outcome.success, "error": outcome.error}
            if outcome.success:
                existing_ids.pop(page_type, None)

        blog.required_page_ids = existing_ids
        flag_modified(blog, "required_page_ids")
        blog.required_pages_status = self._compute_status(existing_ids)
        await self.db.commit()

        logger.info(
            "[REQUIRED_PAGES] 삭제 완료 | blog=%s | status=%s | 결과=%s",
            blog.name, blog.required_pages_status, results,
        )
        return {
            "success": True,
            "status": blog.required_pages_status,
            "page_ids": existing_ids,
            "results": results,
        }

    async def _publish_one(
        self, blog: Blog, title: str, html: str,
    ) -> PublishResult:
        """플랫폼별 페이지 신규 발행 위임."""
        if blog.platform == BlogPlatform.BLOGGER:
            return await BloggerPagePublisher().publish_page(blog, title, html)
        return await self._publish_wordpress_page(blog, title, html)

    async def _update_one(
        self, blog: Blog, page_id: str, title: str, html: str,
    ) -> PublishResult:
        """플랫폼별 기존 페이지 갱신 위임."""
        if blog.platform == BlogPlatform.BLOGGER:
            return await BloggerPagePublisher().update_page(blog, page_id, title, html)
        return await self._update_wordpress_page(blog, page_id, title, html)

    async def _delete_one(self, blog: Blog, page_id: str) -> PublishResult:
        """플랫폼별 페이지 삭제 위임."""
        if blog.platform == BlogPlatform.BLOGGER:
            return await BloggerPagePublisher().delete_page(blog, page_id)
        return await self._delete_wordpress_page(blog, page_id)

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

    async def _update_wordpress_page(
        self, blog: Blog, page_id: str, title: str, html: str,
    ) -> PublishResult:
        """WordPress REST wp/v2/pages/{id} 갱신."""
        from ..wordpress_api import WordPressAPI, WordPressAPIError

        result = PublishResult(success=False, platform="wordpress")
        try:
            async with WordPressAPI() as api:
                res = await api.update_page(blog, page_id, title, html)
            result.success = True
            result.published_url = res.get("remote_url", "")
            result.platform_post_id = res.get("remote_id")
        except WordPressAPIError as e:
            result.error = str(e.message)
            result.retryable = e.status_code is None or e.status_code >= 500
        except Exception as e:
            result.error = f"WordPress 페이지 갱신 오류: {e}"
        return result

    async def _delete_wordpress_page(
        self, blog: Blog, page_id: str,
    ) -> PublishResult:
        """WordPress REST wp/v2/pages/{id} 삭제."""
        from ..wordpress_api import WordPressAPI, WordPressAPIError

        result = PublishResult(success=False, platform="wordpress")
        try:
            async with WordPressAPI() as api:
                await api.delete_page(blog, page_id)
            result.success = True
        except WordPressAPIError as e:
            result.error = str(e.message)
            result.retryable = e.status_code is None or e.status_code >= 500
        except Exception as e:
            result.error = f"WordPress 페이지 삭제 오류: {e}"
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
