"""
재발행 액션

Features:
- WordPress/Blogger 재발행 실행
- 플랫폼별 서비스 호출
- 결과 반환
- ModuleInterface 상속으로 플로우 연결 지원
"""
from datetime import datetime
from typing import Dict, Any, Optional

from ...models.blog import Blog, BlogPlatform
from ...models.module import Module
from ...models.google_credential import GoogleCredential
from ...services.wordpress_service import WordPressRepublishService
from ...services.blogger_service import BloggerRepublishService
from ...core.logger import get_logger
from ...core.module_interface import ModuleInterface, ModuleType

logger = get_logger("republish_action", "republish.log")


class RepublishAction(ModuleInterface):
    """
    재발행 액션

    ModuleInterface를 상속받아 플로우 내 모듈 연결을 지원합니다.

    하위 호환성:
    - 기존 execute(blog, module, credential) 메서드 그대로 동작
    - 새 execute_flow(inputs) 메서드로 플로우 연결 지원
    """

    # ========== ModuleInterface 메타 정보 ==========
    module_type = ModuleType.PUBLISHING
    module_name = "republish"
    module_description = "블로그 포스트 재발행"

    input_schema = {
        "required": [],  # 기존 방식 호환 - 필수값 없음
        "optional": ["blog_id", "post_id", "category_id"]
    }

    output_schema = {
        "provides": [
            "published_post_id", "published_url", "publish_status",
            "publish_timestamp", "blog_id", "error_message"
        ]
    }

    def __init__(self, config: dict | None = None):
        """
        Args:
            config: 모듈 설정 (플로우 연결 시 사용)
        """
        self.config = config or {}
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

    # ========== ModuleInterface 구현 ==========

    def execute_module(self, inputs: dict | None = None) -> dict:
        """
        ModuleInterface 표준 실행 (플로우 연결용)

        플로우에서 호출될 때 사용됩니다.
        inputs=None이면 config 폴백.

        Args:
            inputs: 이전 모듈에서 전달받은 데이터

        Returns:
            output_schema에 정의된 키 포함
        """
        blog_id = self.get_input_value(inputs, "blog_id", fallback_config=self.config)
        post_id = self.get_input_value(inputs, "post_id", fallback_config=self.config)

        logger.info(f"[REPUBLISH_MODULE] Starting | blog_id={blog_id}, post_id={post_id}")

        # 플로우 연결용 동기 결과 반환 (실제 비동기 실행은 flow_engine에서 처리)
        return self.create_output(
            published_post_id=post_id,
            published_url=None,
            publish_status="pending",
            publish_timestamp=datetime.now().isoformat(),
            blog_id=blog_id,
            error_message=None
        )

    def create_result_output(self, result: dict, blog_id: int | None = None) -> dict:
        """
        기존 execute() 결과를 표준 output 형식으로 변환

        Args:
            result: execute() 반환값
            blog_id: 블로그 ID

        Returns:
            output_schema에 정의된 키 포함
        """
        return self.create_output(
            published_post_id=result.get("post_id"),
            published_url=result.get("url"),
            publish_status="success" if result.get("success") else "failed",
            publish_timestamp=datetime.now().isoformat(),
            blog_id=blog_id or result.get("blog_id"),
            error_message=result.get("message") if not result.get("success") else None
        )
