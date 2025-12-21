"""
블로그 비즈니스 로직

Features:
- 블로그 CRUD 작업
- API 키 암호화/복호화
- 플랫폼별 연결 테스트
- 보안 이벤트 로깅
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..models.blog import Blog, BlogPlatform
from ..models.user import User
from ..schemas.blog import (
    BlogCreateRequest,
    BlogUpdateRequest,
    BlogResponse,
    BlogListResponse,
    BlogConnectionTestResponse,
    BlogStatsResponse
)
from ..core.security import encrypt_data, decrypt_data
from ..core.logger import get_logger, log_security_event

logger = get_logger("blog_service", "blog.log")


class BlogService:
    """블로그 서비스 클래스"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_blog(self, user: User, request: BlogCreateRequest) -> BlogResponse:
        """
        블로그 등록

        Args:
            user: 사용자 객체
            request: 블로그 등록 요청

        Returns:
            생성된 블로그 정보

        Raises:
            HTTPException: 등록 실패시
        """
        logger.info(f"블로그 등록 시도 | 사용자={user.id} | 이름={request.name} | 플랫폼={request.platform}")

        # 중복 URL 확인
        await self._check_duplicate_url(user.id, str(request.url))

        try:
            # 자동화 지원 여부 결정
            is_auto_supported = request.platform != BlogPlatform.OTHER

            # API 키 암호화
            api_key_encrypted = await self._encrypt_api_credential(
                request.api_key, "api_key"
            ) if request.api_key else None

            api_secret_encrypted = await self._encrypt_api_credential(
                request.api_secret, "api_secret"
            ) if request.api_secret else None

            oauth_token_encrypted = await self._encrypt_api_credential(
                request.oauth_token, "oauth_token"
            ) if request.oauth_token else None

            # 블로그 객체 생성
            blog = Blog(
                user_id=user.id,
                name=request.name,
                url=str(request.url),
                platform=request.platform,
                is_auto_supported=is_auto_supported,
                api_key_encrypted=api_key_encrypted,
                api_secret_encrypted=api_secret_encrypted,
                oauth_token_encrypted=oauth_token_encrypted,
                auto_publish=request.auto_publish and is_auto_supported,
                republish_interval_hours=request.republish_interval_hours,
                daily_limit=request.daily_limit,
                editor_type=request.editor_type,
                css_classes=request.css_classes
            )

            self.db.add(blog)
            await self.db.commit()
            await self.db.refresh(blog)

            logger.info(f"블로그 등록 완료 | 블로그ID={blog.id} | 사용자={user.id}")

            return BlogResponse(**blog.to_dict())

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 등록 실패 | 사용자={user.id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 등록 중 오류가 발생했습니다"
            )

    async def get_user_blogs(self, user: User, include_deleted: bool = False) -> List[BlogListResponse]:
        """
        사용자 블로그 목록 조회

        Args:
            user: 사용자 객체
            include_deleted: 삭제된 블로그 포함 여부

        Returns:
            블로그 목록
        """
        query = select(Blog).where(Blog.user_id == user.id)

        if not include_deleted:
            query = query.where(Blog.is_deleted == False)

        query = query.order_by(Blog.created_at.desc())

        result = await self.db.execute(query)
        blogs = result.scalars().all()

        logger.info(f"블로그 목록 조회 | 사용자={user.id} | 개수={len(blogs)}")

        return [BlogListResponse(**blog.to_dict()) for blog in blogs]

    async def get_blog_by_id(self, user: User, blog_id: int) -> BlogResponse:
        """
        블로그 상세 조회

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            블로그 상세 정보

        Raises:
            HTTPException: 블로그를 찾을 수 없는 경우
        """
        blog = await self._get_user_blog(user, blog_id)
        return BlogResponse(**blog.to_dict())

    async def update_blog(self, user: User, blog_id: int, request: BlogUpdateRequest) -> BlogResponse:
        """
        블로그 정보 수정

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID
            request: 수정 요청

        Returns:
            수정된 블로그 정보
        """
        blog = await self._get_user_blog(user, blog_id)

        logger.info(f"블로그 수정 시도 | 블로그ID={blog_id} | 사용자={user.id}")

        try:
            # 변경된 필드 추적
            changed_fields = []

            # 기본 정보 업데이트
            if request.name is not None:
                blog.name = request.name
                changed_fields.append("name")

            if request.url is not None:
                blog.url = str(request.url)
                changed_fields.append("url")

            # API 키 업데이트 (값이 제공된 경우만)
            if request.api_key is not None:
                blog.api_key_encrypted = await self._encrypt_api_credential(
                    request.api_key, "api_key"
                )
                changed_fields.append("api_key")

            if request.api_secret is not None:
                blog.api_secret_encrypted = await self._encrypt_api_credential(
                    request.api_secret, "api_secret"
                )
                changed_fields.append("api_secret")

            if request.oauth_token is not None:
                blog.oauth_token_encrypted = await self._encrypt_api_credential(
                    request.oauth_token, "oauth_token"
                )
                changed_fields.append("oauth_token")

            # 발행 설정 업데이트
            if request.auto_publish is not None:
                blog.auto_publish = request.auto_publish and blog.is_auto_supported
                changed_fields.append("auto_publish")

            if request.republish_interval_hours is not None:
                blog.republish_interval_hours = request.republish_interval_hours
                changed_fields.append("republish_interval_hours")

            if request.daily_limit is not None:
                blog.daily_limit = request.daily_limit
                changed_fields.append("daily_limit")

            if request.editor_type is not None:
                blog.editor_type = request.editor_type
                changed_fields.append("editor_type")

            if request.css_classes is not None:
                blog.css_classes = request.css_classes
                changed_fields.append("css_classes")

            await self.db.commit()
            await self.db.refresh(blog)

            logger.info(f"블로그 수정 완료 | 블로그ID={blog_id} | 변경필드={changed_fields}")

            return BlogResponse(**blog.to_dict())

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 수정 실패 | 블로그ID={blog_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 수정 중 오류가 발생했습니다"
            )

    async def delete_blog(self, user: User, blog_id: int) -> dict:
        """
        블로그 삭제 (소프트 삭제)

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            삭제 결과
        """
        blog = await self._get_user_blog(user, blog_id)

        logger.info(f"블로그 삭제 시도 | 블로그ID={blog_id} | 사용자={user.id}")

        try:
            blog.soft_delete()
            await self.db.commit()

            logger.info(f"블로그 삭제 완료 | 블로그ID={blog_id}")

            return {"message": f"블로그 '{blog.name}'이 삭제되었습니다"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 삭제 실패 | 블로그ID={blog_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 삭제 중 오류가 발생했습니다"
            )

    async def test_blog_connection(self, user: User, blog_id: int) -> BlogConnectionTestResponse:
        """
        블로그 API 연결 테스트

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            연결 테스트 결과
        """
        blog = await self._get_user_blog(user, blog_id)

        logger.info(f"블로그 연결 테스트 시도 | 블로그ID={blog_id}")

        if not blog.is_auto_supported:
            return BlogConnectionTestResponse(
                success=False,
                message="자동화를 지원하지 않는 플랫폼입니다",
                details={"platform": blog.platform.value}
            )

        if not blog.has_api_credentials:
            return BlogConnectionTestResponse(
                success=False,
                message="API 인증 정보가 설정되지 않았습니다",
                details={"missing_credentials": True}
            )

        # 실제 API 연결 테스트는 Phase 4에서 구현 예정
        # 현재는 기본적인 검증만 수행
        test_result = await self._perform_connection_test(blog)

        logger.info(f"블로그 연결 테스트 완료 | 블로그ID={blog_id} | 결과={test_result['success']}")

        return BlogConnectionTestResponse(**test_result)

    async def get_user_blog_stats(self, user: User) -> BlogStatsResponse:
        """
        사용자 블로그 통계 조회

        Args:
            user: 사용자 객체

        Returns:
            블로그 통계
        """
        query = select(Blog).where(
            and_(Blog.user_id == user.id, Blog.is_deleted == False)
        )

        result = await self.db.execute(query)
        blogs = result.scalars().all()

        total_blogs = len(blogs)
        active_blogs = sum(1 for blog in blogs if blog.is_active)
        auto_publish_enabled = sum(1 for blog in blogs if blog.auto_publish)

        # 플랫폼별 통계
        by_platform = {}
        for blog in blogs:
            platform = blog.platform.value
            by_platform[platform] = by_platform.get(platform, 0) + 1

        return BlogStatsResponse(
            total_blogs=total_blogs,
            active_blogs=active_blogs,
            auto_publish_enabled=auto_publish_enabled,
            by_platform=by_platform
        )

    async def _check_duplicate_url(self, user_id: int, url: str) -> None:
        """URL 중복 확인"""
        query = select(Blog).where(
            and_(
                Blog.user_id == user_id,
                Blog.url == url,
                Blog.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        existing_blog = result.scalar_one_or_none()

        if existing_blog:
            logger.warning(f"URL 중복 | 사용자={user_id} | URL={url}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 등록된 블로그 URL입니다"
            )

    async def _get_user_blog(self, user: User, blog_id: int) -> Blog:
        """사용자 블로그 조회"""
        query = select(Blog).where(
            and_(
                Blog.id == blog_id,
                Blog.user_id == user.id,
                Blog.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        blog = result.scalar_one_or_none()

        if not blog:
            logger.warning(f"블로그 없음 | 블로그ID={blog_id} | 사용자={user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="블로그를 찾을 수 없습니다"
            )

        return blog

    async def _encrypt_api_credential(self, value: str, field_name: str) -> str:
        """API 인증 정보 암호화"""
        try:
            encrypted_value = encrypt_data(value)

            # 보안 로그 (값은 마스킹)
            masked_value = "****" + value[-4:] if len(value) > 4 else "****"
            log_security_event(logger, "API_KEY_ENCRYPTED", {
                "field": field_name,
                "masked_value": masked_value
            })

            return encrypted_value

        except Exception as e:
            logger.error(f"암호화 실패 | 필드={field_name} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="암호화 처리 중 오류가 발생했습니다"
            )

    async def _perform_connection_test(self, blog: Blog) -> Dict[str, Any]:
        """
        실제 연결 테스트 수행

        Note: Phase 4에서 WordPress/Blogger API 연동 시 구현 예정
        현재는 기본 검증만 수행
        """
        # 기본적인 설정 확인
        if blog.platform == BlogPlatform.WORDPRESS:
            if not blog.api_key_encrypted or not blog.api_secret_encrypted:
                return {
                    "success": False,
                    "message": "WordPress API 키와 시크릿이 모두 필요합니다",
                    "details": {"platform": "wordpress", "missing_auth": True}
                }

        elif blog.platform == BlogPlatform.BLOGGER:
            if not blog.oauth_token_encrypted:
                return {
                    "success": False,
                    "message": "Blogger OAuth 토큰이 필요합니다",
                    "details": {"platform": "blogger", "missing_oauth": True}
                }

        # Phase 4에서 실제 API 호출 로직 구현 예정
        return {
            "success": True,
            "message": "연결 설정이 올바르게 구성되었습니다 (실제 API 테스트는 Phase 4에서 구현 예정)",
            "details": {
                "platform": blog.platform.value,
                "url": blog.url,
                "has_credentials": blog.has_api_credentials
            }
        }