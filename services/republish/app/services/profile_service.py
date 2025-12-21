"""
재발행 프로파일 서비스

Features:
- 프로파일 CRUD 작업
- 블로그-프로파일 연동 관리
- 포스트 범위 중복 검증
- 프로파일 유효성 검증
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.orm import selectinload

from ..models.publish_profile import PublishProfile
from ..models.blog_profile_link import BlogProfileLink
from ..models.user import User
from ..models.blog import Blog
from ..core.logger import get_logger
from .platform_limiter import PlatformLimiter

logger = get_logger("profile_service", "republish.log")


class ProfileService:
    """재발행 프로파일 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.platform_limiter = PlatformLimiter(db)

    # ===========================================
    # 프로파일 CRUD
    # ===========================================

    async def create_profile(
        self,
        user: User,
        profile_data: Dict[str, Any]
    ) -> PublishProfile:
        """프로파일 생성"""
        try:
            # 프로파일 생성
            profile = PublishProfile(
                user_id=user.id,
                **profile_data
            )

            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)

            logger.info(f"프로파일 생성 성공 | 프로파일ID={profile.id} | 사용자={user.id}")
            return profile

        except Exception as e:
            await self.db.rollback()
            logger.error(f"프로파일 생성 실패 | 사용자={user.id} | 오류={e}")
            raise

    async def get_user_profiles(self, user: User) -> List[PublishProfile]:
        """사용자의 프로파일 목록 조회"""
        query = select(PublishProfile).where(
            PublishProfile.user_id == user.id
        ).order_by(PublishProfile.priority, PublishProfile.created_at)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_profile_by_id(self, user: User, profile_id: int) -> PublishProfile:
        """프로파일 상세 조회"""
        query = select(PublishProfile).where(
            and_(
                PublishProfile.id == profile_id,
                PublishProfile.user_id == user.id
            )
        )

        result = await self.db.execute(query)
        profile = result.scalar_one_or_none()

        if not profile:
            raise ValueError(f"프로파일을 찾을 수 없습니다: {profile_id}")

        return profile

    async def update_profile(
        self,
        user: User,
        profile_id: int,
        update_data: Dict[str, Any]
    ) -> PublishProfile:
        """프로파일 수정"""
        try:
            profile = await self.get_profile_by_id(user, profile_id)

            # 업데이트
            for key, value in update_data.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)

            await self.db.commit()
            await self.db.refresh(profile)

            logger.info(f"프로파일 수정 성공 | 프로파일ID={profile_id} | 사용자={user.id}")
            return profile

        except Exception as e:
            await self.db.rollback()
            logger.error(f"프로파일 수정 실패 | 프로파일ID={profile_id} | 사용자={user.id} | 오류={e}")
            raise

    async def delete_profile(self, user: User, profile_id: int) -> Dict[str, Any]:
        """프로파일 삭제"""
        try:
            profile = await self.get_profile_by_id(user, profile_id)

            # 연동된 블로그 링크 먼저 삭제
            await self.db.execute(
                delete(BlogProfileLink).where(BlogProfileLink.profile_id == profile_id)
            )

            # 프로파일 삭제
            await self.db.delete(profile)
            await self.db.commit()

            logger.info(f"프로파일 삭제 성공 | 프로파일ID={profile_id} | 사용자={user.id}")
            return {"message": "프로파일이 삭제되었습니다"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"프로파일 삭제 실패 | 프로파일ID={profile_id} | 사용자={user.id} | 오류={e}")
            raise

    # ===========================================
    # 프로파일 검증
    # ===========================================

    async def validate_profile(
        self,
        profile_data: Dict[str, Any],
        blog_id: Optional[int] = None
    ) -> List[str]:
        """프로파일 검증"""
        warnings = []

        # 간격 설정 검증
        interval_mode = profile_data.get("interval_mode", "manual")
        if interval_mode == "manual":
            interval = profile_data.get("manual_interval_minutes")
            if not interval or interval < 5:
                warnings.append("수동 간격은 최소 5분 이상이어야 합니다")

        elif interval_mode == "auto":
            daily_count = profile_data.get("auto_daily_count")
            if not daily_count or daily_count < 1:
                warnings.append("자동 모드에서 일일 목표 횟수는 최소 1회 이상이어야 합니다")
            elif daily_count > 288:  # 5분마다 = 288회/일
                warnings.append("일일 목표 횟수가 너무 큽니다 (최대 288회)")

        # 포스트 범위 검증
        range_start = profile_data.get("post_range_start", 1)
        range_end = profile_data.get("post_range_end")

        if range_start < 1:
            warnings.append("포스트 범위 시작은 1 이상이어야 합니다")

        if range_end is not None and range_end <= range_start:
            warnings.append("포스트 범위 끝은 시작보다 커야 합니다")

        # Jitter 설정 검증
        jitter_min = profile_data.get("jitter_min_percent", -20)
        jitter_max = profile_data.get("jitter_max_percent", 30)

        if jitter_min > jitter_max:
            warnings.append("Jitter 최소값은 최대값보다 작아야 합니다")

        if jitter_min < -50:
            warnings.append("Jitter 최소 변동률이 너무 작습니다 (-50% 이상 권장)")

        # 플랫폼별 검증 (블로그 정보가 있는 경우)
        if blog_id:
            try:
                blog_query = select(Blog).where(Blog.id == blog_id)
                blog_result = await self.db.execute(blog_query)
                blog = blog_result.scalar_one_or_none()

                if blog:
                    platform_warnings = await self.platform_limiter.validate_profile(
                        profile_data, blog.platform.value
                    )
                    warnings.extend(platform_warnings)

            except Exception as e:
                logger.warning(f"플랫폼 검증 중 오류 | 블로그ID={blog_id} | 오류={e}")

        return warnings

    # ===========================================
    # 블로그-프로파일 연동
    # ===========================================

    async def link_blog_to_profile(
        self,
        user: User,
        blog_id: int,
        profile_id: int
    ) -> BlogProfileLink:
        """블로그-프로파일 연동"""
        try:
            # 권한 확인
            profile = await self.get_profile_by_id(user, profile_id)

            blog_query = select(Blog).where(
                and_(Blog.id == blog_id, Blog.user_id == user.id)
            )
            blog_result = await self.db.execute(blog_query)
            blog = blog_result.scalar_one_or_none()

            if not blog:
                raise ValueError(f"블로그를 찾을 수 없습니다: {blog_id}")

            # 중복 확인
            existing_query = select(BlogProfileLink).where(
                and_(
                    BlogProfileLink.blog_id == blog_id,
                    BlogProfileLink.profile_id == profile_id
                )
            )
            existing_result = await self.db.execute(existing_query)
            existing = existing_result.scalar_one_or_none()

            if existing:
                raise ValueError("이미 연동된 블로그-프로파일 조합입니다")

            # 포스트 범위 중복 검증
            overlap_warnings = await self._check_range_overlap(blog_id, profile)
            if overlap_warnings:
                logger.warning(f"포스트 범위 중복 경고 | 블로그ID={blog_id} | 프로파일ID={profile_id}")

            # 연동 생성
            link = BlogProfileLink(
                blog_id=blog_id,
                profile_id=profile_id
            )

            self.db.add(link)
            await self.db.commit()
            await self.db.refresh(link)

            logger.info(f"블로그-프로파일 연동 성공 | 블로그ID={blog_id} | 프로파일ID={profile_id}")
            return link

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그-프로파일 연동 실패 | 블로그ID={blog_id} | 프로파일ID={profile_id} | 오류={e}")
            raise

    async def unlink_blog_from_profile(
        self,
        user: User,
        blog_id: int,
        profile_id: int
    ) -> Dict[str, Any]:
        """블로그-프로파일 연동 해제"""
        try:
            # 권한 확인
            await self.get_profile_by_id(user, profile_id)

            # 연동 삭제
            delete_query = delete(BlogProfileLink).where(
                and_(
                    BlogProfileLink.blog_id == blog_id,
                    BlogProfileLink.profile_id == profile_id
                )
            )

            result = await self.db.execute(delete_query)
            await self.db.commit()

            if result.rowcount == 0:
                raise ValueError("연동된 블로그-프로파일을 찾을 수 없습니다")

            logger.info(f"블로그-프로파일 연동 해제 성공 | 블로그ID={blog_id} | 프로파일ID={profile_id}")
            return {"message": "연동이 해제되었습니다"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그-프로파일 연동 해제 실패 | 블로그ID={blog_id} | 프로파일ID={profile_id} | 오류={e}")
            raise

    async def get_blog_profiles(self, user: User, blog_id: int) -> List[Dict[str, Any]]:
        """블로그에 연동된 프로파일 목록"""
        query = select(BlogProfileLink).options(
            selectinload(BlogProfileLink.profile)
        ).where(
            BlogProfileLink.blog_id == blog_id
        ).order_by(BlogProfileLink.profile.has(PublishProfile.priority))

        result = await self.db.execute(query)
        links = result.scalars().all()

        profiles = []
        for link in links:
            if link.profile.user_id == user.id:  # 권한 확인
                profiles.append({
                    "link_id": link.id,
                    "profile": link.profile,
                    "is_active": link.is_active,
                    "last_executed_at": link.last_executed_at,
                    "next_scheduled_at": link.next_scheduled_at,
                    "success_rate": link.success_rate
                })

        return profiles

    async def _check_range_overlap(
        self,
        blog_id: int,
        new_profile: PublishProfile
    ) -> List[str]:
        """포스트 범위 중복 검증"""
        warnings = []

        # 해당 블로그의 기존 프로파일들 조회
        query = select(BlogProfileLink).options(
            selectinload(BlogProfileLink.profile)
        ).where(
            and_(
                BlogProfileLink.blog_id == blog_id,
                BlogProfileLink.is_active == True
            )
        )

        result = await self.db.execute(query)
        existing_links = result.scalars().all()

        new_start = new_profile.post_range_start
        new_end = new_profile.post_range_end

        for link in existing_links:
            existing = link.profile
            existing_start = existing.post_range_start
            existing_end = existing.post_range_end

            # 범위 중복 검사
            if self._ranges_overlap(new_start, new_end, existing_start, existing_end):
                warnings.append(
                    f"프로파일 '{existing.name}' ({existing_start}-{existing_end or '무제한'})와 "
                    f"포스트 범위가 중복됩니다"
                )

        return warnings

    def _ranges_overlap(
        self,
        start1: int, end1: Optional[int],
        start2: int, end2: Optional[int]
    ) -> bool:
        """두 범위의 중복 여부 확인"""
        # 무제한 범위 처리
        if end1 is None:
            end1 = float('inf')
        if end2 is None:
            end2 = float('inf')

        # 범위 중복 확인
        return not (end1 < start2 or end2 < start1)