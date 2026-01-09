"""
WordPress 재발행 서비스

Features:
- 오래된 글 조회
- 날짜 업데이트로 재발행
- WordPress REST API v2 활용
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from ..models.blog import Blog
from ..core.logger import get_logger
from .wordpress_api import WordPressAPI, WordPressAPIError

logger = get_logger("wordpress_service", "republish.log")


class WordPressRepublishService:
    """WordPress 재발행 서비스"""

    def __init__(self):
        self.api = WordPressAPI()

    async def get_oldest_post(self, blog: Blog) -> Optional[Dict[str, Any]]:
        """
        가장 오래된 글 조회

        Args:
            blog: 블로그 객체

        Returns:
            포스트 정보 딕셔너리 또는 None
        """
        try:
            logger.info(f"[WP_REPUBLISH] Getting oldest post | BlogID={blog.id}")

            # 오래된 순으로 1개 조회
            url = self.api._get_api_url(blog, "posts?per_page=1&orderby=date&order=asc&status=publish")
            headers = self.api._get_auth_headers(blog)

            result = await self.api._make_request("GET", url, headers)
            posts = result["data"]

            if not posts:
                logger.info(f"[WP_REPUBLISH] No posts found | BlogID={blog.id}")
                return None

            post = posts[0]
            logger.info(
                f"[WP_REPUBLISH] Found oldest post | BlogID={blog.id} | "
                f"PostID={post['id']} | Title={post.get('title', {}).get('rendered', '')[:30]}"
            )

            return {
                "id": str(post["id"]),
                "title": post.get("title", {}).get("rendered", ""),
                "date": post.get("date", ""),
                "link": post.get("link", "")
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_REPUBLISH] Failed to get oldest post | BlogID={blog.id} | Error={e.message}")
            raise
        except Exception as e:
            logger.error(f"[WP_REPUBLISH] Unexpected error | BlogID={blog.id} | Error={e}")
            raise WordPressAPIError(f"예상치 못한 오류: {e}")

    async def update_post_date(
        self,
        blog: Blog,
        post_id: str,
        new_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        포스트 날짜 업데이트 (재발행)

        Args:
            blog: 블로그 객체
            post_id: WordPress 포스트 ID
            new_date: 새 날짜 (기본: 현재 시간)

        Returns:
            업데이트 결과
        """
        try:
            if new_date is None:
                new_date = datetime.now(timezone(timedelta(hours=9)))  # KST (UTC+9)

            # ISO 8601 형식으로 변환
            date_str = new_date.strftime("%Y-%m-%dT%H:%M:%S")
            date_gmt_str = new_date.strftime("%Y-%m-%dT%H:%M:%S")

            logger.info(
                f"[WP_REPUBLISH] Updating post date | BlogID={blog.id} | "
                f"PostID={post_id} | NewDate={date_str}"
            )

            url = self.api._get_api_url(blog, f"posts/{post_id}")
            headers = self.api._get_auth_headers(blog)

            # 날짜만 업데이트
            data = {
                "date": date_str,
                "date_gmt": date_gmt_str
            }

            result = await self.api._make_request("POST", url, headers, data)

            post_data = result["data"]
            logger.info(
                f"[WP_REPUBLISH] Post date updated | BlogID={blog.id} | "
                f"PostID={post_id} | NewDate={post_data.get('date', '')}"
            )

            return {
                "success": True,
                "post_id": post_id,
                "new_date": post_data.get("date", ""),
                "link": post_data.get("link", ""),
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(
                f"[WP_REPUBLISH] Failed to update post date | BlogID={blog.id} | "
                f"PostID={post_id} | Error={e.message}"
            )
            raise
        except Exception as e:
            logger.error(
                f"[WP_REPUBLISH] Unexpected error | BlogID={blog.id} | "
                f"PostID={post_id} | Error={e}"
            )
            raise WordPressAPIError(f"예상치 못한 오류: {e}")

    async def republish(self, blog: Blog) -> Dict[str, Any]:
        """
        재발행 실행 (오래된 글 → 최신화)

        Args:
            blog: 블로그 객체

        Returns:
            재발행 결과
        """
        try:
            logger.info(f"[WP_REPUBLISH] Starting republish | BlogID={blog.id} | BlogName={blog.name}")

            # 1. 가장 오래된 글 조회
            oldest_post = await self.get_oldest_post(blog)

            if not oldest_post:
                logger.warning(f"[WP_REPUBLISH] No posts to republish | BlogID={blog.id}")
                return {
                    "success": False,
                    "message": "재발행할 글이 없습니다",
                    "blog_id": blog.id
                }

            # 2. 날짜 업데이트 (재발행)
            result = await self.update_post_date(blog, oldest_post["id"])

            logger.info(
                f"[WP_REPUBLISH] Republish completed | BlogID={blog.id} | "
                f"PostID={oldest_post['id']} | Title={oldest_post['title'][:30]}"
            )

            return {
                "success": True,
                "message": "재발행 성공",
                "blog_id": blog.id,
                "blog_name": blog.name,
                "post_id": oldest_post["id"],
                "post_title": oldest_post["title"],
                "old_date": oldest_post["date"],
                "new_date": result["new_date"],
                "link": result["link"],
                "response_time_ms": result["response_time_ms"]
            }

        except WordPressAPIError as e:
            logger.error(f"[WP_REPUBLISH] Republish failed | BlogID={blog.id} | Error={e.message}")
            return {
                "success": False,
                "message": f"재발행 실패: {e.message}",
                "blog_id": blog.id,
                "error_code": e.status_code
            }
        except Exception as e:
            logger.error(f"[WP_REPUBLISH] Unexpected error | BlogID={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"예상치 못한 오류: {e}",
                "blog_id": blog.id
            }

    async def test_connection(self, blog: Blog) -> Dict[str, Any]:
        """
        연결 테스트

        Args:
            blog: 블로그 객체

        Returns:
            테스트 결과
        """
        return await self.api.test_connection(blog)

    async def get_post_count(self, blog: Blog) -> int:
        """
        발행된 글 개수 조회

        Args:
            blog: 블로그 객체

        Returns:
            글 개수
        """
        try:
            url = self.api._get_api_url(blog, "posts?per_page=1&status=publish")
            headers = self.api._get_auth_headers(blog)

            async with self.api.client:
                response = await self.api.client.head(url, headers=headers)

                # X-WP-Total 헤더에서 총 개수 추출
                total = response.headers.get("X-WP-Total", "0")
                return int(total)

        except Exception as e:
            logger.error(f"[WP_REPUBLISH] Failed to get post count | BlogID={blog.id} | Error={e}")
            return 0
