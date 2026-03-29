"""
Blogger 발행 서비스

Google Blogger API v3를 통해 생성된 글을 발행합니다.
OAuth 2.0 (GoogleCredential) 인증을 사용합니다.

설계 문서: publish_module_implementation_plan.md - Phase 3.3.2
"""
import asyncio
import logging
from typing import Optional

import httpx

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...models.google_credential import GoogleCredential
from .publish_result import PublishResult

logger = logging.getLogger(__name__)

BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
MAX_RETRIES = 3
BACKOFF_BASE = 2
PUBLISH_TIMEOUT = 30.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class BloggerPublisher:
    """
    Google Blogger API v3를 통한 글 발행

    API: POST /blogger/v3/blogs/{blogId}/posts
    Auth: OAuth 2.0 Bearer Token
    """

    async def publish(
        self,
        blog: Blog,
        post: CrawledPost,
        final_html: str,
        credential: Optional[GoogleCredential] = None,
    ) -> PublishResult:
        """
        Blogger에 글을 발행합니다.

        Args:
            blog: 대상 블로그
            post: 발행할 CrawledPost
            final_html: 이미지가 삽입된 최종 HTML
            credential: Google OAuth 인증 정보

        Returns:
            PublishResult
        """
        result = PublishResult(
            success=False, platform="blogger"
        )

        # 인증 정보 확인
        if not credential:
            result.error = "Google 인증 정보가 없습니다"
            logger.error(
                "[BLOGGER_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        # access_token 획득
        try:
            access_token = credential.get_access_token()
        except Exception as e:
            result.error = f"OAuth 토큰 복호화 실패: {e}"
            logger.error(
                "[BLOGGER_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        # Blog ID 추출 (blog.url에서)
        blog_id = self._extract_blog_id(blog)
        if not blog_id:
            result.error = (
                "Blogger ID를 확인할 수 없습니다. "
                "블로그 URL 또는 설정을 확인하세요."
            )
            logger.error(
                "[BLOGGER_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        api_url = (
            f"{BLOGGER_API_BASE}/blogs/{blog_id}/posts"
        )

        payload = {
            "kind": "blogger#post",
            "title": post.title,
            "content": final_html,
        }

        # 라벨 설정 (Blog.placeholders에서)
        labels = self._get_labels(blog)
        if labels:
            payload["labels"] = labels

        # 재시도 로직
        token_refreshed = False
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._send_request(
                    api_url, access_token, payload
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    result.success = True
                    result.published_url = data.get("url", "")
                    result.platform_post_id = str(
                        data.get("id", "")
                    )

                    logger.info(
                        "[BLOGGER_PUBLISH] 발행 성공 | "
                        "blog=%s | post_id=%s | url=%s",
                        blog.name,
                        result.platform_post_id,
                        result.published_url,
                    )
                    return result

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    wait = BACKOFF_BASE ** attempt
                    result.retry_count = attempt + 1
                    logger.warning(
                        "[BLOGGER_PUBLISH] 재시도 대기 | "
                        "attempt=%d | wait=%ds | status=%d",
                        attempt + 1, wait, resp.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                # 401: 토큰 만료 → 갱신 시도 (1회만)
                if resp.status_code == 401 and not token_refreshed:
                    refreshed = await self._try_refresh_token(
                        credential
                    )
                    if refreshed:
                        token_refreshed = True
                        access_token = credential.get_access_token()
                        logger.info(
                            "[BLOGGER_PUBLISH] 토큰 갱신 성공, "
                            "재시도 | blog=%s", blog.name,
                        )
                        continue
                    result.error = (
                        "OAuth 토큰이 만료되었습니다. "
                        "Google 계정 재인증이 필요합니다."
                    )
                    logger.error(
                        "[BLOGGER_PUBLISH] 토큰 만료 | "
                        "blog=%s", blog.name,
                    )
                    return result

                # 갱신 후에도 401이면 재인증 필요
                if resp.status_code == 401:
                    result.error = (
                        "OAuth 토큰 갱신 후에도 인증 실패. "
                        "Google 계정 재인증이 필요합니다."
                    )
                    logger.error(
                        "[BLOGGER_PUBLISH] 토큰 갱신 후 "
                        "재인증 실패 | blog=%s", blog.name,
                    )
                    return result

                error_msg = self._parse_error(resp)
                result.error = (
                    f"HTTP {resp.status_code}: {error_msg}"
                )
                logger.error(
                    "[BLOGGER_PUBLISH] 발행 실패 | "
                    "blog=%s | %s",
                    blog.name, result.error,
                )
                return result

            except httpx.TimeoutException:
                result.error = "Blogger API 타임아웃"
                result.retry_count = attempt + 1
                logger.warning(
                    "[BLOGGER_PUBLISH] 타임아웃 | blog=%s | "
                    "attempt=%d/%d",
                    blog.name, attempt + 1, MAX_RETRIES,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BACKOFF_BASE ** attempt)
                    continue
            except Exception as e:
                result.error = f"Blogger API 오류: {e}"
                logger.error(
                    "[BLOGGER_PUBLISH] 예외 발생 | "
                    "blog=%s | %s", blog.name, e,
                )
                return result

        logger.error(
            "[BLOGGER_PUBLISH] 최대 재시도 초과 | "
            "blog=%s | retries=%d",
            blog.name, MAX_RETRIES,
        )
        return result

    def _extract_blog_id(self, blog: Blog) -> Optional[str]:
        """
        블로그 ID 추출

        Blog.placeholders.blogger_id 또는
        Blog.url에서 blogspot.com 패턴 파싱
        """
        # 1. placeholders에서 직접 설정된 ID
        placeholders = blog.placeholders or {}
        blogger_id = placeholders.get("blogger_id")
        if blogger_id:
            return str(blogger_id)

        # 2. api_key에 Blogger ID가 저장된 경우
        if blog.api_key_encrypted:
            try:
                from ...core.encryption import decrypt_api_key
                decrypted = decrypt_api_key(
                    blog.api_key_encrypted
                )
                if decrypted and decrypted.isdigit():
                    return decrypted
            except Exception:
                pass

        return None

    def _get_labels(self, blog: Blog) -> list:
        """Blog.placeholders에서 Blogger 라벨 조회"""
        placeholders = blog.placeholders or {}
        labels = placeholders.get("blogger_labels", [])
        if isinstance(labels, list):
            return labels
        return []

    async def _send_request(
        self,
        api_url: str,
        access_token: str,
        payload: dict,
    ) -> httpx.Response:
        """Blogger API 요청 전송"""
        async with httpx.AsyncClient(
            timeout=PUBLISH_TIMEOUT
        ) as client:
            return await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

    async def _try_refresh_token(
        self,
        credential: GoogleCredential,
    ) -> bool:
        """
        Google OAuth 토큰 갱신 시도

        refresh_token으로 새 access_token을 발급받습니다.
        갱신 성공 시 credential 객체를 업데이트합니다.

        Returns:
            갱신 성공 여부
        """
        refresh_token = credential.get_refresh_token()
        if not refresh_token:
            logger.warning(
                "[BLOGGER_PUBLISH] refresh_token 없음, "
                "갱신 불가"
            )
            return False

        try:
            from ...core.config import settings
            client_id = getattr(settings, "google_client_id", None)
            client_secret = getattr(
                settings, "google_client_secret", None
            )
            if not client_id or not client_secret:
                logger.warning(
                    "[BLOGGER_PUBLISH] Google OAuth "
                    "client_id/secret 미설정, 갱신 불가"
                )
                return False

            async with httpx.AsyncClient(
                timeout=10.0
            ) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    credential.set_tokens(
                        access_token=data["access_token"],
                        expires_in_seconds=data.get(
                            "expires_in", 3600
                        ),
                    )
                    logger.info(
                        "[BLOGGER_PUBLISH] 토큰 갱신 완료"
                    )
                    return True

                logger.warning(
                    "[BLOGGER_PUBLISH] 토큰 갱신 실패 | "
                    "status=%d", resp.status_code,
                )
                return False
        except Exception as e:
            logger.error(
                "[BLOGGER_PUBLISH] 토큰 갱신 오류: %s", e,
            )
            return False

    @staticmethod
    def _parse_error(resp: httpx.Response) -> str:
        """Blogger API 에러 메시지 파싱"""
        try:
            data = resp.json()
            error = data.get("error", {})
            if isinstance(error, dict):
                return error.get("message", resp.text[:200])
            return str(error)[:200]
        except Exception:
            return resp.text[:200]
