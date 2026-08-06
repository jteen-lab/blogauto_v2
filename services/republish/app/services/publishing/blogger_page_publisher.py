"""Blogger 필수 페이지(Page) 발행 (애드센스 F1).

BloggerPublisher의 인증/blog_id 조회 헬퍼를 상속해 정적 페이지를 생성한다.
Blogger API는 posts와 pages를 같은 blog 하위 리소스로 다루며 별도 OAuth
스코프를 요구하지 않으므로, 기존 글 발행에 쓰이던 인증 정보를 그대로
재사용한다(신규 동의 불필요 전제 — 착수 세션 설계 질문 1의 결론).

설계 문서: docs/flowcharts/adsense_sprint1_p1.md - F1
"""
from typing import Optional

from ...models.blog import Blog
from ...models.google_credential import GoogleCredential
from ...core.logger import get_logger
from .blogger_publisher import (
    BLOGGER_API_BASE,
    RETRYABLE_STATUS_CODES,
    BloggerPublisher,
)
from .publish_result import PublishResult

logger = get_logger("blogger_page_publisher", "app.log")


class BloggerPagePublisher(BloggerPublisher):
    """Blogger Pages API(`pages.insert`)를 통한 정적 페이지 생성."""

    async def publish_page(
        self,
        blog: Blog,
        title: str,
        html_content: str,
        credential: Optional[GoogleCredential] = None,
    ) -> PublishResult:
        """Blogger에 정적 페이지(Page)를 생성합니다.

        API: POST /blogger/v3/blogs/{blogId}/pages
        """
        result = PublishResult(success=False, platform="blogger")

        access_token = await self._get_access_token(blog, credential)
        if not access_token:
            result.error = (
                "OAuth 인증 실패. 블로그 설정에서 Refresh Token을 입력하세요."
            )
            result.retryable = False
            return result

        blog_id = await self._extract_blog_id(blog, access_token)
        if not blog_id:
            result.error = "Blogger ID를 확인할 수 없습니다."
            result.retryable = False
            return result

        api_url = f"{BLOGGER_API_BASE}/blogs/{blog_id}/pages"
        payload = {
            "kind": "blogger#page", "title": title, "content": html_content,
        }

        try:
            resp = await self._send_request(api_url, access_token, payload)
        except Exception as e:
            result.error = f"Blogger Pages API 오류: {e}"
            logger.error(
                "[BLOGGER_PAGE] 예외 발생 | blog=%s | %s", blog.name, e,
            )
            return result

        if resp.status_code in (200, 201):
            data = resp.json()
            result.success = True
            result.published_url = data.get("url", "")
            result.platform_post_id = str(data.get("id", ""))
            logger.info(
                "[BLOGGER_PAGE] 페이지 생성 성공 | blog=%s | title=%s | id=%s",
                blog.name, title, result.platform_post_id,
            )
            return result

        if resp.status_code == 403:
            result.error = (
                "Blogger Pages API 권한 없음(403). Google 계정 재인증이 "
                "필요할 수 있습니다."
            )
            result.retryable = False
            logger.error(
                "[BLOGGER_PAGE] 403 권한 오류 | blog=%s | title=%s",
                blog.name, title,
            )
            return result

        result.error = f"HTTP {resp.status_code}: {self._parse_error(resp)}"
        result.retryable = resp.status_code in RETRYABLE_STATUS_CODES
        logger.error(
            "[BLOGGER_PAGE] 페이지 생성 실패 | blog=%s | title=%s | %s",
            blog.name, title, result.error,
        )
        return result
