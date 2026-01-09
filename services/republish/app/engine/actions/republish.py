"""
재발행 액션

Features:
- WordPress/Blogger 재발행 실행
- 플랫폼별 서비스 호출
- 결과 반환
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog, BlogPlatform
from ...models.module import Module
from ...models.google_credential import GoogleCredential
from ...services.wordpress_service import WordPressRepublishService
from ...services.blogger_service import BloggerRepublishService
from ...core.logger import get_logger

logger = get_logger("republish_action", "republish.log")


class RepublishAction:
    """재발행 액션"""

    def __init__(self):
        self.wordpress_service = WordPressRepublishService()
        self.blogger_service = BloggerRepublishService()

    async def execute(
        self,
        blog: Blog,
        module: Module,
        credential: Optional[GoogleCredential] = None
    ) -> Dict[str, Any]:
        """
        재발행 실행

        Args:
            blog: 대상 블로그
            module: 재발행 모듈
            credential: Google 인증 정보 (Blogger용)

        Returns:
            실행 결과
        """
        try:
            logger.info(
                f"[REPUBLISH_ACTION] Starting | BlogID={blog.id} | "
                f"Platform={blog.platform.value} | ModuleID={module.id}"
            )

            # 플랫폼별 분기
            if blog.platform == BlogPlatform.WORDPRESS:
                result = await self._execute_wordpress(blog, module)

            elif blog.platform == BlogPlatform.BLOGGER:
                if not credential:
                    logger.error(f"[REPUBLISH_ACTION] No credential | BlogID={blog.id}")
                    return {
                        "success": False,
                        "message": "Google 인증 정보가 없습니다",
                        "blog_id": blog.id,
                        "platform": blog.platform.value
                    }
                result = await self._execute_blogger(blog, module, credential)

            else:
                logger.warning(f"[REPUBLISH_ACTION] Unsupported platform | Platform={blog.platform.value}")
                return {
                    "success": False,
                    "message": f"지원하지 않는 플랫폼: {blog.platform.value}",
                    "blog_id": blog.id,
                    "platform": blog.platform.value
                }

            logger.info(
                f"[REPUBLISH_ACTION] Completed | BlogID={blog.id} | "
                f"Success={result.get('success', False)}"
            )

            return result

        except Exception as e:
            logger.error(f"[REPUBLISH_ACTION] Error | BlogID={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"재발행 오류: {e}",
                "blog_id": blog.id,
                "platform": blog.platform.value if blog else "unknown"
            }

    async def _execute_wordpress(self, blog: Blog, module: Module) -> Dict[str, Any]:
        """WordPress 재발행 실행"""
        return await self.wordpress_service.republish(blog)

    async def _execute_blogger(
        self,
        blog: Blog,
        module: Module,
        credential: GoogleCredential
    ) -> Dict[str, Any]:
        """Blogger 재발행 실행"""
        return await self.blogger_service.republish(blog, credential)

    async def test_connection(
        self,
        blog: Blog,
        credential: Optional[GoogleCredential] = None
    ) -> Dict[str, Any]:
        """
        연결 테스트

        Args:
            blog: 대상 블로그
            credential: Google 인증 정보 (Blogger용)

        Returns:
            테스트 결과
        """
        try:
            if blog.platform == BlogPlatform.WORDPRESS:
                return await self.wordpress_service.test_connection(blog)

            elif blog.platform == BlogPlatform.BLOGGER:
                if not credential:
                    return {
                        "success": False,
                        "message": "Google 인증 정보가 없습니다"
                    }
                return await self.blogger_service.test_connection(blog, credential)

            else:
                return {
                    "success": False,
                    "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
                }

        except Exception as e:
            logger.error(f"[REPUBLISH_ACTION] Connection test error | BlogID={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"연결 테스트 오류: {e}"
            }
