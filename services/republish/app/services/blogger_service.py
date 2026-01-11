"""
Blogger 재발행 서비스

Features:
- 오래된 글 조회
- 임시저장(revert) → 재발행(publish) 패턴
- Google Blogger API v3 사용
- OAuth2 인증 (GoogleCredential 모델)
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import httpx

from ..models.blog import Blog
from ..models.google_credential import GoogleCredential
from ..core.logger import get_logger

logger = get_logger("blogger_service", "republish.log")

# Blogger API 기본 URL
BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"


class BloggerAPIError(Exception):
    """Blogger API 오류"""
    def __init__(self, message: str, status_code: int = None, error_data: Dict = None):
        self.message = message
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(self.message)


class BloggerRepublishService:
    """Blogger 재발행 서비스"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3
        self.base_backoff = 2

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_auth_headers(self, credential: GoogleCredential) -> Dict[str, str]:
        """인증 헤더 생성"""
        access_token = credential.get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    def _extract_blog_id_from_url(self, url: str) -> Optional[str]:
        """URL에서 블로그 ID 추출 시도 (Blogger URL 패턴)"""
        # blogspot.com URL에서는 직접 ID 추출 불가
        # API를 통해 조회해야 함
        return None

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Dict = None
    ) -> Dict[str, Any]:
        """API 요청 실행 (재시도 포함)"""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data
                )

                if response.status_code in [200, 201]:
                    return response.json()

                elif 400 <= response.status_code < 500:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")

                    logger.error(f"[BLOGGER_API] Client Error - {method} {url} - {response.status_code} - {error_msg}")

                    raise BloggerAPIError(
                        message=f"클라이언트 오류: {error_msg}",
                        status_code=response.status_code,
                        error_data=error_data
                    )

                else:
                    last_error = BloggerAPIError(
                        message=f"서버 오류: HTTP {response.status_code}",
                        status_code=response.status_code
                    )

            except httpx.TimeoutException:
                last_error = BloggerAPIError("요청 시간 초과")
                logger.warning(f"[BLOGGER_API] Timeout - {method} {url} (attempt {attempt + 1})")

            except httpx.RequestError as e:
                last_error = BloggerAPIError(f"네트워크 오류: {e}")
                logger.warning(f"[BLOGGER_API] Network Error - {method} {url} (attempt {attempt + 1})")

            except BloggerAPIError:
                raise

            except Exception as e:
                last_error = BloggerAPIError(f"예상치 못한 오류: {e}")
                logger.error(f"[BLOGGER_API] Unexpected Error - {method} {url} - {e}")

            if attempt < self.max_retries:
                wait_time = self.base_backoff ** attempt
                await asyncio.sleep(wait_time)

        raise last_error

    async def get_blog_id(self, blog: Blog, credential: GoogleCredential) -> str:
        """
        블로그 URL로 블로그 ID 조회

        Args:
            blog: 블로그 객체
            credential: Google 인증 정보

        Returns:
            Blogger 블로그 ID
        """
        try:
            headers = self._get_auth_headers(credential)
            url = f"{BLOGGER_API_BASE}/blogs/byurl?url={blog.url}"

            result = await self._make_request("GET", url, headers)
            blog_id = result.get("id")

            logger.info(f"[BLOGGER] Got blog ID | BlogID={blog.id} | BloggerID={blog_id}")
            return blog_id

        except BloggerAPIError as e:
            logger.error(f"[BLOGGER] Failed to get blog ID | BlogID={blog.id} | Error={e.message}")
            raise

    async def get_oldest_post(
        self,
        blog: Blog,
        credential: GoogleCredential,
        blogger_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        가장 오래된 글 조회

        Args:
            blog: 블로그 객체
            credential: Google 인증 정보
            blogger_id: Blogger 블로그 ID

        Returns:
            포스트 정보 딕셔너리 또는 None
        """
        try:
            headers = self._get_auth_headers(credential)
            # 발행일 기준 오래된 순 정렬
            url = f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts?maxResults=1&orderBy=published"

            result = await self._make_request("GET", url, headers)
            posts = result.get("items", [])

            if not posts:
                logger.info(f"[BLOGGER] No posts found | BlogID={blog.id}")
                return None

            post = posts[0]
            logger.info(
                f"[BLOGGER] Found oldest post | BlogID={blog.id} | "
                f"PostID={post['id']} | Title={post.get('title', '')[:30]}"
            )

            return {
                "id": post["id"],
                "title": post.get("title", ""),
                "published": post.get("published", ""),
                "url": post.get("url", "")
            }

        except BloggerAPIError as e:
            logger.error(f"[BLOGGER] Failed to get posts | BlogID={blog.id} | Error={e.message}")
            raise

    async def revert_to_draft(
        self,
        credential: GoogleCredential,
        blogger_id: str,
        post_id: str
    ) -> Dict[str, Any]:
        """
        글을 임시저장 상태로 변경

        Args:
            credential: Google 인증 정보
            blogger_id: Blogger 블로그 ID
            post_id: 포스트 ID

        Returns:
            API 응답
        """
        headers = self._get_auth_headers(credential)
        url = f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts/{post_id}/revert"

        logger.info(f"[BLOGGER] Reverting to draft | BloggerID={blogger_id} | PostID={post_id}")
        return await self._make_request("POST", url, headers)

    async def publish_post(
        self,
        credential: GoogleCredential,
        blogger_id: str,
        post_id: str
    ) -> Dict[str, Any]:
        """
        글을 다시 발행

        Args:
            credential: Google 인증 정보
            blogger_id: Blogger 블로그 ID
            post_id: 포스트 ID

        Returns:
            API 응답
        """
        headers = self._get_auth_headers(credential)
        url = f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts/{post_id}/publish"

        logger.info(f"[BLOGGER] Publishing post | BloggerID={blogger_id} | PostID={post_id}")
        return await self._make_request("POST", url, headers)

    async def republish(self, blog: Blog, credential: GoogleCredential) -> Dict[str, Any]:
        """
        재발행 실행 (임시저장 → 재발행)

        Args:
            blog: 블로그 객체
            credential: Google 인증 정보

        Returns:
            재발행 결과
        """
        try:
            logger.info(f"[BLOGGER] Starting republish | BlogID={blog.id} | BlogName={blog.name}")

            # 1. 블로그 ID 조회
            blogger_id = await self.get_blog_id(blog, credential)

            # 2. 가장 오래된 글 조회
            oldest_post = await self.get_oldest_post(blog, credential, blogger_id)

            if not oldest_post:
                logger.warning(f"[BLOGGER] No posts to republish | BlogID={blog.id}")
                return {
                    "success": False,
                    "message": "재발행할 글이 없습니다",
                    "blog_id": blog.id
                }

            post_id = oldest_post["id"]
            old_published = oldest_post["published"]

            # 3. 임시저장으로 변경
            await self.revert_to_draft(credential, blogger_id, post_id)

            # 잠시 대기 (API 안정성)
            await asyncio.sleep(0.5)

            # 4. 다시 발행
            result = await self.publish_post(credential, blogger_id, post_id)

            new_published = result.get("published", "")

            logger.info(
                f"[BLOGGER] Republish completed | BlogID={blog.id} | "
                f"PostID={post_id} | Title={oldest_post['title'][:30]}"
            )

            return {
                "success": True,
                "message": "재발행 성공",
                "blog_id": blog.id,
                "blog_name": blog.name,
                "blogger_id": blogger_id,
                "post_id": post_id,
                "post_title": oldest_post["title"],
                "old_published": old_published,
                "new_published": new_published,
                "url": result.get("url", oldest_post["url"])
            }

        except BloggerAPIError as e:
            logger.error(f"[BLOGGER] Republish failed | BlogID={blog.id} | Error={e.message}")
            return {
                "success": False,
                "message": f"재발행 실패: {e.message}",
                "blog_id": blog.id,
                "error_code": e.status_code
            }
        except Exception as e:
            logger.error(f"[BLOGGER] Unexpected error | BlogID={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"예상치 못한 오류: {e}",
                "blog_id": blog.id
            }

    async def test_connection(self, blog: Blog, credential: GoogleCredential) -> Dict[str, Any]:
        """
        연결 테스트

        Args:
            blog: 블로그 객체
            credential: Google 인증 정보

        Returns:
            테스트 결과
        """
        try:
            blogger_id = await self.get_blog_id(blog, credential)

            return {
                "success": True,
                "message": "연결 성공",
                "blogger_id": blogger_id
            }

        except BloggerAPIError as e:
            return {
                "success": False,
                "message": f"연결 실패: {e.message}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"예상치 못한 오류: {e}"
            }

    async def get_post_count(
        self,
        blog: Blog,
        credential: GoogleCredential
    ) -> int:
        """
        발행된 글 개수 조회

        Args:
            blog: 블로그 객체
            credential: Google 인증 정보

        Returns:
            글 개수
        """
        try:
            blogger_id = await self.get_blog_id(blog, credential)
            headers = self._get_auth_headers(credential)

            # 블로그 정보 조회 (totalPosts 포함)
            url = f"{BLOGGER_API_BASE}/blogs/{blogger_id}"
            result = await self._make_request("GET", url, headers)

            total_posts = result.get("posts", {}).get("totalItems", 0)
            logger.info(f"[BLOGGER] Post count | BlogID={blog.id} | Count={total_posts}")
            return total_posts

        except Exception as e:
            logger.error(f"[BLOGGER] Failed to get post count | BlogID={blog.id} | Error={e}")
            return 0
