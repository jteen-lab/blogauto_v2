"""
WordPress REST API 클라이언트

Features:
- WordPress REST API v2 연동
- Application Password 인증
- 재시도 로직 (지수 백오프)
- API 키 로그 마스킹
- 응답 시간 측정
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
import httpx
from urllib.parse import urljoin, urlparse

from ..models.blog import Blog
from ..models.post import Post
from ..core.logger import get_logger
from ..core.encryption import decrypt_api_key  # 암호화 유틸리티

logger = get_logger("wordpress_api", "republish.log")


class WordPressAPIError(Exception):
    """WordPress API 오류"""
    def __init__(self, message: str, status_code: int = None, response_data: Dict = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)


class WordPressAPI:
    """WordPress REST API 클라이언트"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3
        self.base_backoff = 2  # 초

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_api_url(self, blog: Blog, endpoint: str) -> str:
        """API URL 생성"""
        base_url = blog.url.rstrip('/')
        return urljoin(base_url, f"/wp-json/wp/v2/{endpoint}")

    def _get_auth_headers(self, blog: Blog) -> Dict[str, str]:
        """인증 헤더 생성"""
        try:
            # API 키 복호화 (username:password 형태)
            username = decrypt_api_key(blog.api_key_encrypted)
            password = decrypt_api_key(blog.api_secret_encrypted)

            # Basic Auth 헤더
            import base64
            credentials = f"{username}:{password}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            return {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json",
                "User-Agent": "BlogAuto-v2/1.0"
            }

        except Exception as e:
            logger.error(f"WP 인증 헤더 생성 실패 | 블로그ID={blog.id} | 오류={e}")
            raise WordPressAPIError("인증 정보가 올바르지 않습니다")

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
                start_time = time.time()

                # HTTP 요청
                response = await self.client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data
                )

                response_time_ms = int((time.time() - start_time) * 1000)

                # 성공 응답
                if response.status_code in [200, 201]:
                    logger.info(f"[WP_API] Success - {method} {url} - {response.status_code} - {response_time_ms}ms")
                    return {
                        "data": response.json(),
                        "response_time_ms": response_time_ms,
                        "status_code": response.status_code
                    }

                # 클라이언트 오류 (재시도 불가)
                elif 400 <= response.status_code < 500:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("message", f"HTTP {response.status_code}")

                    logger.error(f"[WP_API] Client Error - {method} {url} - {response.status_code} - {error_msg}")

                    raise WordPressAPIError(
                        message=f"클라이언트 오류: {error_msg}",
                        status_code=response.status_code,
                        response_data=error_data
                    )

                # 서버 오류 (재시도 가능)
                else:
                    last_error = WordPressAPIError(
                        message=f"서버 오류: HTTP {response.status_code}",
                        status_code=response.status_code
                    )

            except httpx.TimeoutException:
                last_error = WordPressAPIError("요청 시간 초과")
                logger.warning(f"[WP_API] Timeout - {method} {url} (attempt {attempt + 1})")

            except httpx.RequestError as e:
                last_error = WordPressAPIError(f"네트워크 오류: {e}")
                logger.warning(f"[WP_API] Network Error - {method} {url} (attempt {attempt + 1}) - {e}")

            except Exception as e:
                last_error = WordPressAPIError(f"예상치 못한 오류: {e}")
                logger.error(f"[WP_API] Unexpected Error - {method} {url} (attempt {attempt + 1}) - {e}")

            # 재시도 대기 (지수 백오프)
            if attempt < self.max_retries:
                wait_time = self.base_backoff ** attempt
                logger.info(f"[WP_API] Retrying in {wait_time}s (attempt {attempt + 2})")
                await asyncio.sleep(wait_time)

        # 최대 재시도 초과
        logger.error(f"[WP_API] Max retries exceeded - {method} {url}")
        raise last_error

    # ===========================================
    # 포스트 API
    # ===========================================

    async def create_post(self, blog: Blog, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 포스트 발행"""
        try:
            logger.info(f"[WP_API] Creating post | Blog={blog.id} | Title={post_data.get('title', '')[:50]}")

            url = self._get_api_url(blog, "posts")
            headers = self._get_auth_headers(blog)

            # 포스트 데이터 변환
            wp_data = self._convert_post_data_for_create(post_data)

            result = await self._make_request("POST", url, headers, wp_data)

            remote_id = str(result["data"]["id"])
            remote_url = result["data"].get("link", "")

            logger.info(f"[WP_API] Post created successfully | Blog={blog.id} | RemoteID={remote_id}")

            return {
                "success": True,
                "remote_id": remote_id,
                "remote_url": remote_url,
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_API] Failed to create post | Blog={blog.id} | Error={e.message}")
            raise

        except Exception as e:
            logger.error(f"[WP_API] Unexpected error creating post | Blog={blog.id} | Error={e}")
            raise WordPressAPIError(f"예상치 못한 오류: {e}")

    async def update_post(
        self,
        blog: Blog,
        remote_id: str,
        post_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """포스트 수정 (재발행)"""
        try:
            logger.info(f"[WP_API] Updating post | Blog={blog.id} | RemoteID={remote_id}")

            url = self._get_api_url(blog, f"posts/{remote_id}")
            headers = self._get_auth_headers(blog)

            # 포스트 데이터 변환
            wp_data = self._convert_post_data_for_update(post_data)

            result = await self._make_request("POST", url, headers, wp_data)

            remote_url = result["data"].get("link", "")

            logger.info(f"[WP_API] Post updated successfully | Blog={blog.id} | RemoteID={remote_id}")

            return {
                "success": True,
                "remote_id": remote_id,
                "remote_url": remote_url,
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_API] Failed to update post | Blog={blog.id} | RemoteID={remote_id} | Error={e.message}")
            raise

        except Exception as e:
            logger.error(f"[WP_API] Unexpected error updating post | Blog={blog.id} | RemoteID={remote_id} | Error={e}")
            raise WordPressAPIError(f"예상치 못한 오류: {e}")

    async def get_post(self, blog: Blog, remote_id: str) -> Dict[str, Any]:
        """포스트 조회"""
        try:
            url = self._get_api_url(blog, f"posts/{remote_id}")
            headers = self._get_auth_headers(blog)

            result = await self._make_request("GET", url, headers)

            return {
                "success": True,
                "data": result["data"],
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_API] Failed to get post | Blog={blog.id} | RemoteID={remote_id} | Error={e.message}")
            raise

    async def get_posts(
        self,
        blog: Blog,
        page: int = 1,
        per_page: int = 100
    ) -> List[Dict[str, Any]]:
        """포스트 목록 조회"""
        try:
            url = self._get_api_url(blog, f"posts?page={page}&per_page={per_page}")
            headers = self._get_auth_headers(blog)

            result = await self._make_request("GET", url, headers)

            return result["data"]

        except WordPressAPIError as e:
            logger.error(f"[WP_API] Failed to get posts | Blog={blog.id} | Error={e.message}")
            raise

    # ===========================================
    # 데이터 변환
    # ===========================================

    def _convert_post_data_for_create(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """포스트 생성용 데이터 변환"""
        return {
            "title": post_data.get("title", ""),
            "content": post_data.get("content", ""),
            "excerpt": post_data.get("excerpt", ""),
            "status": "publish",
            "comment_status": "closed",
            "ping_status": "closed"
        }

    def _convert_post_data_for_update(self, post_data: Dict[str, Any]) -> Dict[str, Any]:
        """포스트 수정용 데이터 변환"""
        data = {
            "title": post_data.get("title", ""),
            "content": post_data.get("content", ""),
            "excerpt": post_data.get("excerpt", ""),
            "status": "publish"
        }

        # 수정일시 업데이트로 재발행 표시
        from datetime import datetime
        data["date"] = datetime.now().isoformat()

        return data

    # ===========================================
    # 연결 테스트
    # ===========================================

    async def test_connection(self, blog: Blog) -> Dict[str, Any]:
        """연결 테스트"""
        try:
            logger.info(f"[WP_API] Testing connection | Blog={blog.id}")

            url = self._get_api_url(blog, "posts?per_page=1")
            headers = self._get_auth_headers(blog)

            result = await self._make_request("GET", url, headers)

            logger.info(f"[WP_API] Connection test successful | Blog={blog.id}")
            return {
                "success": True,
                "message": "연결 성공",
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_API] Connection test failed | Blog={blog.id} | Error={e.message}")
            return {
                "success": False,
                "message": f"연결 실패: {e.message}"
            }

        except Exception as e:
            logger.error(f"[WP_API] Connection test error | Blog={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"예상치 못한 오류: {e}"
            }