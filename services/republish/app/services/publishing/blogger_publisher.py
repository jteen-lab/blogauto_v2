"""
Blogger 발행 서비스

Google Blogger API v3를 통해 생성된 글을 발행합니다.
OAuth 2.0 (GoogleCredential) 인증을 사용합니다.

설계 문서: publish_module_implementation_plan.md - Phase 3.3.2
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...models.google_credential import GoogleCredential
from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from .publish_result import PublishResult
from .google_oauth_helper import refresh_access_token

logger = get_logger("blogger_publisher", "app.log")

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
            result.retryable = False
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
            result.retryable = False
            logger.error(
                "[BLOGGER_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        api_url = (
            f"{BLOGGER_API_BASE}/blogs/{blog_id}/posts"
        )

        # 멱등성: 발행 직전 동일 제목 최근 글 조회 → 있으면 신규 생성 생략
        # (직전 시도가 응답 유실로 중단됐어도 재시도 시 중복 생성 방지)
        existing = await self._find_recent_post_by_title(
            blog_id, post.title, access_token,
        )
        if existing:
            result.success = True
            result.published_url = existing.get("url", "")
            result.platform_post_id = str(existing.get("id", ""))
            logger.warning(
                "[BLOGGER_PUBLISH] 중복 방지: 동일 글 이미 존재 → "
                "기존 글 채택 | blog=%s | post_id=%s | url=%s",
                blog.name, result.platform_post_id,
                result.published_url,
            )
            return result

        payload = {
            "kind": "blogger#post",
            "title": post.title,
            "content": final_html,
        }

        # 라벨 설정 (정적 라벨 + 카테고리 동적 라벨)
        labels = self._get_labels(blog, post=post)
        if labels:
            payload["labels"] = labels

        # 재시도 로직
        token_refreshed = False
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    "[BLOGGER_PUBLISH] POST 전송 | blog=%s | "
                    "attempt=%d/%d",
                    blog.name, attempt + 1, MAX_RETRIES,
                )
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
                    result.retryable = False
                    return result

                if resp.status_code == 401:
                    result.error = (
                        "OAuth 토큰 갱신 후에도 인증 실패. "
                        "Google 계정 재인증이 필요합니다."
                    )
                    result.retryable = False
                    logger.error(
                        "[BLOGGER_PUBLISH] 토큰 갱신 후 "
                        "재인증 실패 | blog=%s", blog.name,
                    )
                    return result

                # 그 외 상태 코드는 4xx 클라이언트 오류로 간주 → 영구 실패
                error_msg = self._parse_error(resp)
                result.error = (
                    f"HTTP {resp.status_code}: {error_msg}"
                )
                result.retryable = False
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
            except asyncio.CancelledError:
                # 코루틴 취소는 except Exception으로 잡히지 않는다.
                # POST가 Google에 도달해 글이 생성됐을 수 있으므로 로그 후 재전파.
                logger.error(
                    "[BLOGGER_PUBLISH] 코루틴 중단(취소) | blog=%s | "
                    "post_id=%s | 발행 도중 중단 — Blogger에 글이 "
                    "생성됐을 수 있음(다음 시도 시 중복 조회로 차단)",
                    blog.name, getattr(post, "id", "?"),
                )
                raise
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

    async def _find_recent_post_by_title(
        self,
        blog_id: str,
        title: str,
        access_token: str,
        window_minutes: int = 10,
    ) -> Optional[dict]:
        """동일 제목 + 최근 발행 글 조회 (멱등성/중복 방지).

        직전 발행 시도가 응답 유실/취소로 중단됐어도, 재시도 시 이미
        생성된 글을 찾아 중복 생성을 막는다. 조회 자체가 실패하면
        None을 반환해 정상 발행을 차단하지 않는다.

        Args:
            blog_id: Blogger 블로그 ID
            title: 발행하려는 글 제목
            access_token: OAuth access token
            window_minutes: 최근으로 간주할 시간 윈도우(분)

        Returns:
            매칭된 글 dict(url, id 포함) 또는 None
        """
        target = (title or "").strip()
        if not target:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=PUBLISH_TIMEOUT,
            ) as client:
                resp = await client.get(
                    f"{BLOGGER_API_BASE}/blogs/{blog_id}/posts",
                    params={
                        "fetchBodies": "false",
                        "fetchImages": "false",
                        "maxResults": 10,
                        "orderBy": "published",
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                )
            if resp.status_code != 200:
                logger.warning(
                    "[BLOGGER_PUBLISH] 중복 조회 실패(무시) | "
                    "status=%d", resp.status_code,
                )
                return None
            items = resp.json().get("items", []) or []
            cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=window_minutes,
            )
            for item in items:
                if (item.get("title") or "").strip() != target:
                    continue
                published = self._parse_published(
                    item.get("published"),
                )
                # 시간 파싱 실패 시에도 제목 일치하면 중복으로 간주(보수적)
                if published is None or published >= cutoff:
                    return item
        except Exception as e:
            logger.warning(
                "[BLOGGER_PUBLISH] 중복 조회 오류(무시) | %s", e,
            )
        return None

    @staticmethod
    def _parse_published(
        value: Optional[str],
    ) -> Optional[datetime]:
        """Blogger published(RFC3339)를 aware datetime으로 변환.

        Args:
            value: RFC3339 문자열 (예: 2026-06-13T18:35:00+09:00)

        Returns:
            파싱된 datetime 또는 실패 시 None
        """
        if not value:
            return None
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00"),
            )
        except Exception:
            return None

    def _get_labels(
        self,
        blog: Blog,
        post: Optional[CrawledPost] = None,
    ) -> list:
        """Blog.placeholders 정적 라벨 + 카테고리 기반 동적 라벨 병합

        Args:
            blog: 블로그 객체
            post: CrawledPost (카테고리 라벨 추출용, 선택)

        Returns:
            라벨 문자열 리스트 (중복 제거됨)
        """
        # 1. 정적 라벨 (Blog.placeholders)
        placeholders = blog.placeholders or {}
        static_labels = placeholders.get("blogger_labels", [])
        labels: list = (
            list(static_labels)
            if isinstance(static_labels, list)
            else []
        )

        # 2. 동적 라벨 (CrawledPost 카테고리)
        # lazy loading 에러(greenlet) 방지를 위해 try/except 처리
        if post:
            try:
                category_labels = self._extract_category_labels(
                    post,
                )
                for label in category_labels:
                    if label and label not in labels:
                        labels.append(label)
            except Exception as e:
                logger.debug(
                    "[BLOGGER_LABELS] 카테고리 라벨 추출 스킵 | %s",
                    type(e).__name__,
                )

        if labels:
            logger.debug(
                "[BLOGGER_LABELS] blog=%s | labels=%s",
                blog.name, labels,
            )

        return labels

    @staticmethod
    def _extract_category_labels(
        post: CrawledPost,
    ) -> list:
        """CrawledPost의 매칭된 MainTitle에서 카테고리 라벨 추출

        MainTitle.topic_id / subtopic_id -> Topic.name / SubTopic.name
        이미 로드된 관계 객체에서 안전하게 가져옵니다.
        관계가 로드되지 않은 경우 빈 리스트를 반환합니다.

        Args:
            post: CrawledPost 객체

        Returns:
            카테고리 이름 문자열 리스트
        """
        labels: list = []

        # matched_main_title 관계가 로드되어 있을 때만
        main_title = getattr(post, "matched_main_title", None)
        if not main_title:
            return labels

        # Topic 이름 (이미 로드된 경우)
        topic = getattr(main_title, "topic", None)
        if topic and getattr(topic, "name", None):
            labels.append(topic.name)

        # SubTopic 이름 (이미 로드된 경우)
        subtopic = getattr(main_title, "subtopic", None)
        if subtopic and getattr(subtopic, "name", None):
            labels.append(subtopic.name)

        if labels:
            logger.debug(
                "[BLOGGER_LABELS] 카테고리 라벨 추출 | "
                "main_title_id=%s | labels=%s",
                main_title.id, labels,
            )

        return labels

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
        """Refresh Token → Access Token 교환

        공통 헬퍼(google_oauth_helper)에 위임합니다.

        Args:
            refresh_token: Google refresh_token

        Returns:
            새 access_token 또는 None (실패 시)
        """
        return await refresh_access_token(refresh_token)

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
