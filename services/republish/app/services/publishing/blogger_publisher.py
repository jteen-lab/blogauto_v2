"""
Blogger 발행 서비스

Google Blogger API v3를 통해 생성된 글을 발행합니다.
OAuth 2.0 (GoogleCredential) 인증을 사용합니다.

설계 문서: publish_module_implementation_plan.md - Phase 3.3.2
"""
import asyncio
import os
from pathlib import Path
from typing import Optional

import httpx

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...models.google_credential import GoogleCredential
from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from .publish_result import PublishResult

logger = get_logger("blogger_publisher", "app.log")

_CID_KEYS = ("GOOGLE_CLIENT_ID", "BLOGGER_CLIENT_ID")
_CSE_KEYS = ("GOOGLE_CLIENT_SECRET", "BLOGGER_CLIENT_SECRET")


def _read_env_file(cid: str, cse: str) -> tuple:
    """프로젝트 .env 파일에서 OAuth 설정 읽기"""
    for p in (Path(__file__).parents[3] / ".env",):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if not cid and k in _CID_KEYS:
                cid = v
            if not cse and k in _CSE_KEYS:
                cse = v
    return cid, cse

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

        # access_token 획득
        access_token = await self._get_access_token(
            blog, credential,
        )
        if not access_token:
            result.error = (
                "OAuth 인증 실패. 블로그 설정에서 "
                "Refresh Token을 입력하세요."
            )
            logger.error(
                "[BLOGGER_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        # Blog ID 추출
        blog_id = await self._extract_blog_id(
            blog, access_token,
        )
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

                # 401: 토큰 만료 → refresh_token으로 재발급
                if resp.status_code == 401 and not token_refreshed:
                    raw = None
                    if blog.oauth_token_encrypted:
                        try:
                            raw = decrypt_api_key(
                                blog.oauth_token_encrypted
                            )
                        except Exception:
                            pass
                    if raw and raw.startswith("1//"):
                        new_token = await self._exchange_refresh_token(raw)
                        if new_token:
                            token_refreshed = True
                            access_token = new_token
                            continue
                    result.error = "OAuth 토큰 갱신 실패"
                    return result

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

    async def _extract_blog_id(
        self, blog: Blog, access_token: str,
    ) -> Optional[str]:
        """블로그 ID 추출 (캐시 → API 조회)"""
        placeholders = blog.placeholders or {}
        cached_id = placeholders.get("blogger_id")
        if cached_id:
            return str(cached_id)

        if blog.api_key_encrypted:
            try:
                decrypted = decrypt_api_key(
                    blog.api_key_encrypted
                )
                if decrypted and decrypted.isdigit():
                    return decrypted
            except Exception:
                pass

        return await self._fetch_blog_id_by_url(
            blog, access_token,
        )

    async def _fetch_blog_id_by_url(
        self, blog: Blog, access_token: str,
    ) -> Optional[str]:
        """Blogger API blogs/byurl (Bearer Token)"""
        if not blog.url:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=PUBLISH_TIMEOUT,
            ) as client:
                resp = await client.get(
                    f"{BLOGGER_API_BASE}/blogs/byurl",
                    params={"url": blog.url.rstrip("/")},
                    headers={
                        "Authorization":
                            f"Bearer {access_token}",
                    },
                )
            if resp.status_code == 200:
                bid = resp.json().get("id")
                if bid:
                    logger.info(
                        "[BLOGGER_PUBLISH] Blog ID: "
                        "%s → %s", blog.name, bid,
                    )
                    return str(bid)
            logger.warning(
                "[BLOGGER_PUBLISH] Blog ID 실패 | "
                "%d | %s",
                resp.status_code, resp.text[:100],
            )
        except Exception as e:
            logger.warning(
                "[BLOGGER_PUBLISH] Blog ID 오류: "
                "%s", e,
            )
        return None

    def _get_labels(self, blog: Blog) -> list:
        """Blog.placeholders에서 Blogger 라벨 조회"""
        placeholders = blog.placeholders or {}
        labels = placeholders.get("blogger_labels", [])
        if isinstance(labels, list):
            return labels
        return []

    async def _get_access_token(
        self, blog: Blog,
        credential: Optional[GoogleCredential],
    ) -> Optional[str]:
        """OAuth access_token 획득 (refresh_token 자동 갱신)

        Blog.oauth_token_encrypted에 저장된 값이:
        - refresh_token (1//...)이면 → access_token 발급
        - access_token (ya29....)이면 → 그대로 사용
        """
        raw_token = None
        if blog.oauth_token_encrypted:
            try:
                raw_token = decrypt_api_key(
                    blog.oauth_token_encrypted
                )
            except Exception as e:
                logger.warning(
                    "[BLOGGER_PUBLISH] OAuth 토큰 "
                    "복호화 실패: %s", e,
                )

        if not raw_token and credential:
            try:
                raw_token = credential.get_access_token()
            except Exception:
                pass

        if not raw_token:
            return None

        # refresh_token이면 access_token 발급
        if raw_token.startswith("1//"):
            return await self._exchange_refresh_token(
                raw_token,
            )
        # 이미 access_token이면 그대로 반환
        return raw_token

    async def _exchange_refresh_token(
        self, refresh_token: str,
    ) -> Optional[str]:
        """Refresh Token → Access Token 교환"""
        cid, cse = self._get_google_oauth_credentials()
        if not cid or not cse:
            logger.error(
                "[BLOGGER_PUBLISH] CLIENT_ID/SECRET "
                "미설정 → 토큰 갱신 불가"
            )
            return None
        try:
            async with httpx.AsyncClient(
                timeout=PUBLISH_TIMEOUT,
            ) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": cid,
                        "client_secret": cse,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                logger.info(
                    "[BLOGGER_PUBLISH] Access Token "
                    "발급 성공 (refresh_token 사용)"
                )
                return token
            logger.error(
                "[BLOGGER_PUBLISH] 토큰 교환 실패 | "
                "status=%d | %s",
                resp.status_code, resp.text[:200],
            )
        except Exception as e:
            logger.error(
                "[BLOGGER_PUBLISH] 토큰 교환 오류: %s",
                e,
            )
        return None

    @staticmethod
    def _get_google_oauth_credentials() -> tuple:
        """Google OAuth Client ID/Secret 조회"""
        import os
        from ...core.config import settings
        cid = (
            getattr(settings, "google_client_id", "")
            or os.environ.get("GOOGLE_CLIENT_ID", "")
            or os.environ.get("BLOGGER_CLIENT_ID", "")
        )
        cse = (
            getattr(settings, "google_client_secret", "")
            or os.environ.get("GOOGLE_CLIENT_SECRET", "")
            or os.environ.get("BLOGGER_CLIENT_SECRET", "")
        )
        if not cid or not cse:
            cid, cse = _read_env_file(cid, cse)
        return cid, cse

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
