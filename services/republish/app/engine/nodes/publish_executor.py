"""
노드 4: 발행 집행 모듈 (재발행 특화)

Features:
- 플랫폼별 API 호출 (WordPress/Blogger)
- 재발행 실행 및 결과 반환
- 기존 서비스 클래스 활용
"""
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("publish_executor")


class PublishExecutor:
    """
    발행 집행 노드

    실제 WordPress/Blogger API를 호출하여 재발행을 수행합니다.
    기존 WordPressRepublishService, BloggerRepublishService를 활용합니다.
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션 (인증 정보 조회용)
        """
        self.db = db
        self._wordpress_service = None
        self._blogger_service = None

    @property
    def wordpress_service(self):
        """WordPress 서비스 지연 로딩"""
        if self._wordpress_service is None:
            from ...services.wordpress_service import WordPressRepublishService
            self._wordpress_service = WordPressRepublishService()
        return self._wordpress_service

    @property
    def blogger_service(self):
        """Blogger 서비스 지연 로딩"""
        if self._blogger_service is None:
            from ...services.blogger_service import BloggerRepublishService
            self._blogger_service = BloggerRepublishService()
        return self._blogger_service

    async def execute(
        self,
        selected_post: dict[str, Any],
        profile: Optional[str] = None
    ) -> dict[str, Any]:
        """
        재발행 실행

        Args:
            selected_post: 선택된 포스트 정보 (PostSelector 출력)
                - blog_id, blog_name, platform
                - post_id, post_title, post_date
                - credential_id (Blogger용)
            profile: 재발행 프로파일 (선택)

        Returns:
            PublishResult 형식의 딕셔너리
        """
        blog_id = selected_post.get("blog_id") or selected_post.get("id")
        blog_name = selected_post.get("blog_name") or selected_post.get("name", "Unknown")
        platform = selected_post.get("platform", "").lower()
        post_id = selected_post.get("post_id")
        post_title = selected_post.get("post_title")
        post_date = selected_post.get("post_date")

        logger.info(
            f"[PUBLISH_EXECUTOR] 시작 | BlogID={blog_id}, "
            f"BlogName={blog_name}, Platform={platform}, PostID={post_id}"
        )

        try:
            # 플랫폼별 분기
            if platform == "wordpress":
                result = await self._execute_wordpress(
                    blog_id, post_id, post_title, post_date
                )
            elif platform == "blogger":
                credential_id = selected_post.get("credential_id")
                result = await self._execute_blogger(
                    blog_id, post_id, post_title, post_date, credential_id
                )
            else:
                result = self._create_error_result(
                    selected_post, f"지원하지 않는 플랫폼: {platform}"
                )

            logger.info(
                f"[PUBLISH_EXECUTOR] 완료 | BlogID={blog_id}, "
                f"PostID={post_id}, Status={result['status']}"
            )

            return result

        except Exception as e:
            logger.error(f"[PUBLISH_EXECUTOR] 오류 | BlogID={blog_id} | Error={e}")
            return self._create_error_result(selected_post, str(e))

    async def _execute_wordpress(
        self,
        blog_id: int,
        post_id: str,
        post_title: Optional[str],
        post_date: Optional[str]
    ) -> dict[str, Any]:
        """WordPress 재발행 실행"""
        blog_obj = await self._get_blog_model(blog_id)

        if not blog_obj:
            return self._create_error_result(
                {"blog_id": blog_id}, "블로그를 찾을 수 없습니다"
            )

        # WordPress 서비스 호출 (PostSelector에서 선택된 포스트 전달)
        result = await self.wordpress_service.republish(
            blog_obj,
            post_id=post_id,
            post_title=post_title,
            post_date=post_date
        )

        return self._convert_service_result(
            {"id": blog_id, "name": blog_obj.name}, result
        )

    async def _execute_blogger(
        self,
        blog_id: int,
        post_id: str,
        post_title: Optional[str],
        post_date: Optional[str],
        credential_id: Optional[int]
    ) -> dict[str, Any]:
        """Blogger 재발행 실행"""
        blog_obj = await self._get_blog_model(blog_id)

        if not blog_obj:
            return self._create_error_result(
                {"blog_id": blog_id}, "블로그를 찾을 수 없습니다"
            )

        # 인증 정보 조회
        credential = await self._get_credential(credential_id)

        if not credential:
            return self._create_error_result(
                {"blog_id": blog_id}, "Google 인증 정보가 없습니다"
            )

        # Blogger 서비스 호출 (PostSelector에서 선택된 포스트 전달)
        result = await self.blogger_service.republish(
            blog_obj,
            credential,
            post_id=post_id,
            post_title=post_title,
            post_date=post_date
        )

        return self._convert_service_result(
            {"id": blog_id, "name": blog_obj.name}, result
        )

    async def _get_blog_model(self, blog_id: int):
        """블로그 모델 조회"""
        from ...models.blog import Blog

        query = select(Blog).where(Blog.id == blog_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_credential(self, credential_id: Optional[int]):
        """Google 인증 정보 조회"""
        if not credential_id:
            return None

        from ...models.google_credential import GoogleCredential

        query = select(GoogleCredential).where(GoogleCredential.id == credential_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _convert_service_result(
        self,
        blog: dict[str, Any],
        service_result: dict[str, Any]
    ) -> dict[str, Any]:
        """서비스 결과를 PublishResult 형식으로 변환"""
        success = service_result.get("success", False)

        return {
            "blog_id": blog["id"],
            "blog_name": blog.get("name", "Unknown"),
            "status": "success" if success else "failed",
            "post_id": service_result.get("post_id"),
            "post_title": service_result.get("post_title"),
            "post_url": service_result.get("link") or service_result.get("url"),
            "old_date": service_result.get("old_date") or service_result.get("old_published"),
            "new_date": service_result.get("new_date") or service_result.get("new_published"),
            "error_message": service_result.get("message") if not success else None,
            "response_time_ms": service_result.get("response_time_ms"),
            "executed_at": datetime.now().isoformat()
        }

    def _create_error_result(
        self,
        blog: dict[str, Any],
        error_message: str
    ) -> dict[str, Any]:
        """오류 결과 생성"""
        return {
            "blog_id": blog.get("id"),
            "blog_name": blog.get("name", "Unknown"),
            "status": "failed",
            "post_id": None,
            "post_title": None,
            "post_url": None,
            "old_date": None,
            "new_date": None,
            "error_message": error_message,
            "response_time_ms": None,
            "executed_at": datetime.now().isoformat()
        }


async def create_publish_executor(db: AsyncSession) -> PublishExecutor:
    """
    PublishExecutor 인스턴스 생성 팩토리 함수

    Args:
        db: 데이터베이스 세션

    Returns:
        PublishExecutor 인스턴스
    """
    return PublishExecutor(db)
