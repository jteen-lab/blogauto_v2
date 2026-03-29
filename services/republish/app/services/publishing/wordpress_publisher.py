"""
WordPress 발행 서비스

WordPress REST API (wp/v2/posts)를 통해 생성된 글을 발행합니다.
Application Password 기반 Basic Auth 인증을 사용합니다.

설계 문서: publish_module_implementation_plan.md - Phase 3.3.1
"""
import asyncio
import base64
import logging
from typing import Optional

import httpx

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...core.encryption import decrypt_api_key
from .publish_result import PublishResult

logger = logging.getLogger(__name__)

# 재시도 설정
MAX_RETRIES = 3
BACKOFF_BASE = 2
PUBLISH_TIMEOUT = 30.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class WordPressPublisher:
    """
    WordPress REST API를 통한 글 발행

    API: POST {blog_url}/wp-json/wp/v2/posts
    Auth: Basic Auth (Application Password)
    """

    async def publish(
        self,
        blog: Blog,
        post: CrawledPost,
        final_html: str,
    ) -> PublishResult:
        """
        WordPress에 글을 발행합니다.

        대표 이미지는 HTML 본문에 직접 삽입되므로
        featured_media API를 사용하지 않습니다.

        Args:
            blog: 대상 블로그
            post: 발행할 CrawledPost
            final_html: 이미지가 삽입된 최종 HTML

        Returns:
            PublishResult
        """
        result = PublishResult(
            success=False, platform="wordpress"
        )

        # 인증 정보 복호화
        try:
            username = decrypt_api_key(blog.api_key_encrypted)
            app_password = decrypt_api_key(
                blog.api_secret_encrypted
            )
        except Exception as e:
            result.error = f"API 인증 정보 복호화 실패: {e}"
            logger.error(
                "[WP_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        auth_str = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()

        api_url = (
            f"{blog.url.rstrip('/')}/wp-json/wp/v2/posts"
        )

        # 요청 본문 (featured_media 미사용 - HTML 내 이미지 삽입)
        payload = {
            "title": post.title,
            "content": final_html,
            "status": "publish",
            "format": "standard",
        }

        # 카테고리 매핑 (Blog.placeholders에서)
        categories = self._get_categories(blog)
        if categories:
            payload["categories"] = categories

        # 재시도 로직
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._send_request(
                    api_url, auth_str, payload
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    result.success = True
                    result.published_url = data.get("link", "")
                    result.platform_post_id = str(
                        data.get("id", "")
                    )

                    logger.info(
                        "[WP_PUBLISH] 발행 성공 | blog=%s | "
                        "post_id=%s | url=%s",
                        blog.name,
                        result.platform_post_id,
                        result.published_url,
                    )
                    return result

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    wait = BACKOFF_BASE ** attempt
                    result.retry_count = attempt + 1
                    logger.warning(
                        "[WP_PUBLISH] 재시도 대기 | "
                        "attempt=%d | wait=%ds | status=%d",
                        attempt + 1, wait, resp.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                # 재시도 불가능한 오류 (4xx)
                error_msg = self._parse_error(resp)
                result.error = (
                    f"HTTP {resp.status_code}: {error_msg}"
                )
                logger.error(
                    "[WP_PUBLISH] 발행 실패 | blog=%s | %s",
                    blog.name, result.error,
                )
                return result

            except httpx.TimeoutException:
                result.error = "WordPress API 타임아웃"
                result.retry_count = attempt + 1
                logger.warning(
                    "[WP_PUBLISH] 타임아웃 | blog=%s | "
                    "attempt=%d/%d",
                    blog.name, attempt + 1, MAX_RETRIES,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_BASE ** attempt)
                    continue
            except Exception as e:
                result.error = f"WordPress API 오류: {e}"
                logger.error(
                    "[WP_PUBLISH] 예외 발생 | blog=%s | %s",
                    blog.name, e,
                )
                return result

        logger.error(
            "[WP_PUBLISH] 최대 재시도 초과 | blog=%s | "
            "retries=%d",
            blog.name, MAX_RETRIES,
        )
        return result

    async def _send_request(
        self,
        api_url: str,
        auth_str: str,
        payload: dict,
    ) -> httpx.Response:
        """WordPress API 요청 전송"""
        async with httpx.AsyncClient(
            timeout=PUBLISH_TIMEOUT
        ) as client:
            return await client.post(
                api_url,
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

    @staticmethod
    def _get_categories(blog: Blog) -> list:
        """Blog.placeholders에서 WordPress 카테고리 ID 조회"""
        placeholders = blog.placeholders or {}
        categories = placeholders.get("wp_categories", [])
        if isinstance(categories, list):
            return [int(c) for c in categories if str(c).isdigit()]
        return []

    @staticmethod
    def _parse_error(resp: httpx.Response) -> str:
        """WordPress API 에러 메시지 파싱"""
        try:
            data = resp.json()
            return data.get("message", resp.text[:200])
        except Exception:
            return resp.text[:200]
