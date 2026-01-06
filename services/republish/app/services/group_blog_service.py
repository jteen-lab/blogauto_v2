"""
그룹 블로그 관리 서비스 - 블로그 추가/제거/검증
"""

from typing import List, Dict, Any, TYPE_CHECKING
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
import json

from ..models import User, ProfileGroup, BlogGroupLink, PublishProfile, Blog
from ..models.blog import BlogPlatform
from ..schemas.blogger_slot import (
    AddBlogResult,
    SlotInfo,
    ScheduleInfo,
    SlotReservation,
)
from ..core.logger import get_logger
from .blogger_slot_service import BloggerGlobalSlotManager

from .group_slot_service import GroupSlotService

logger = get_logger("group_blog_service", "app.log")


class GroupBlogService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.slot_service = GroupSlotService(db)

    async def add_blog_with_slot_validation(
        self, user: User, group: ProfileGroup, blog_id: int
    ) -> AddBlogResult:
        """블로그 추가 시 슬롯 검증 포함"""
        logger.info(f"[ADD_BLOG_WITH_SLOT] group_id={group.id}, blog_id={blog_id}")

        blog_query = select(Blog).where(
            and_(Blog.id == blog_id, Blog.user_id == user.id)
        )
        blog_result = await self.db.execute(blog_query)
        blog = blog_result.scalar_one_or_none()

        if not blog:
            return AddBlogResult(
                success=False, message=f"블로그를 찾을 수 없습니다: {blog_id}"
            )

        if blog.platform.value != "blogger":
            await self._add_blog_direct(group.id, blog_id)
            return AddBlogResult(
                success=True,
                message=f"{blog.platform.value} 블로그가 성공적으로 추가되었습니다",
            )

        if not blog.google_credential_id:
            return AddBlogResult(
                success=False,
                message="Blogger 블로그에 Google 계정이 연결되지 않았습니다",
            )

        return await self._add_blogger_blog_with_slot_check(group, blog)

    async def remove_blog_with_slot_release(
        self, user: User, group_id: int, blog_id: int
    ) -> bool:
        """블로그 제거 시 슬롯 해제 포함"""
        logger.info(f"[REMOVE_BLOG_WITH_SLOT] group_id={group_id}, blog_id={blog_id}")

        blog_query = select(Blog).where(Blog.id == blog_id)
        blog_result = await self.db.execute(blog_query)
        blog = blog_result.scalar_one_or_none()

        await self.db.execute(
            delete(BlogGroupLink).where(
                and_(
                    BlogGroupLink.group_id == group_id, BlogGroupLink.blog_id == blog_id
                )
            )
        )

        if blog and blog.platform.value == "blogger" and blog.google_credential_id:
            slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)
            await slot_manager.release_slots_by_blog(blog_id, group_id)

        await self.db.commit()
        logger.info(
            f"[REMOVE_BLOG_WITH_SLOT] 완료: group_id={group_id}, blog_id={blog_id}"
        )
        return True

    async def _add_blog_direct(self, group_id: int, blog_id: int) -> None:
        """블로그 직접 추가 (WordPress 등)"""
        existing_query = select(BlogGroupLink).where(
            and_(BlogGroupLink.group_id == group_id, BlogGroupLink.blog_id == blog_id)
        )
        result = await self.db.execute(existing_query)
        if result.scalar_one_or_none():
            logger.info(
                f"[ADD_BLOG_DIRECT] 이미 연결됨: group_id={group_id}, blog_id={blog_id}"
            )
            return

        link = BlogGroupLink(group_id=group_id, blog_id=blog_id)
        self.db.add(link)
        await self.db.commit()

    async def _add_blogger_blog_with_slot_check(
        self, group: ProfileGroup, blog: Blog
    ) -> AddBlogResult:
        """Blogger 블로그 슬롯 검증 후 추가"""
        slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)

        try:
            schedules = await self._extract_group_schedules(group)

            if not schedules:
                await self._add_blog_direct(group.id, blog.id)
                return AddBlogResult(
                    success=True, message="스케줄이 없는 그룹에 블로그가 추가되었습니다"
                )

            from ..models.google_account_policy import GoogleAccountPolicy

            policy_query = select(GoogleAccountPolicy).where(
                GoogleAccountPolicy.google_credential_id == blog.google_credential_id
            )
            policy_result = await self.db.execute(policy_query)
            policy = policy_result.scalar_one_or_none()

            if not policy:
                return AddBlogResult(
                    success=False, message="Google 계정 정책을 찾을 수 없습니다"
                )

            adjusted_schedules = []
            conflicts = []

            for schedule in schedules:
                available_minute = await self.slot_service.find_available_minute(
                    blog.google_credential_id,
                    schedule.day_of_week,
                    schedule.hour,
                    policy.min_interval_minutes,
                )

                if available_minute is None:
                    conflicts.append(
                        f"[{schedule.day_of_week}일 {schedule.hour:02d}시] 모든 슬롯 점유됨"
                    )
                else:
                    adjusted_schedule = ScheduleInfo(
                        profile_id=schedule.profile_id,
                        profile_name=schedule.profile_name,
                        day_of_week=schedule.day_of_week,
                        hour=schedule.hour,
                        minute=available_minute,
                    )
                    adjusted_schedules.append(adjusted_schedule)
                    logger.info(
                        f"[AUTO_SLOT_ALLOCATION] 블로그 {blog.id}: {schedule.day_of_week}일 {schedule.hour:02d}:{available_minute:02d} 할당"
                    )

            if conflicts:
                return AddBlogResult(
                    success=False,
                    message=f"시간 슬롯 충돌 ({len(conflicts)}개): "
                    + ", ".join(conflicts),
                    conflicts=conflicts,
                )

            reservations = [
                SlotReservation(
                    profile_id=schedule.profile_id,
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=schedule.minute,
                )
                for schedule in adjusted_schedules
            ]

            reserved_slots = await slot_manager.reserve_multiple_slots(
                blog_id=blog.id, group_id=group.id, reservations=reservations
            )

            await self._add_blog_direct(group.id, blog.id)

            return AddBlogResult(
                success=True,
                message=f"블로그가 성공적으로 추가되었습니다 ({len(reserved_slots)}개 슬롯 자동 할당)",
                reserved_slots=[
                    SlotInfo(
                        day_of_week=slot.day_of_week,
                        hour=slot.hour,
                        minute=slot.minute,
                        blog_id=blog.id,
                        blog_name=blog.name,
                        group_id=group.id,
                    )
                    for slot in reserved_slots
                ],
            )

        except Exception as e:
            logger.error(f"[ADD_BLOGGER_BLOG] 오류: {e}")
            return AddBlogResult(
                success=False, message=f"블로그 추가 중 오류 발생: {str(e)}"
            )

    async def _extract_group_schedules(self, group: ProfileGroup) -> List[ScheduleInfo]:
        """그룹의 프로파일 스케줄 추출"""
        schedules = []

        for profile_link in group.profile_links:
            profile_query = select(PublishProfile).where(
                PublishProfile.id == profile_link.profile_id
            )
            profile_result = await self.db.execute(profile_query)
            profile = profile_result.scalar_one_or_none()

            if not profile or not profile.schedule_matrix:
                continue

            try:
                matrix_data = (
                    json.loads(profile.schedule_matrix)
                    if isinstance(profile.schedule_matrix, str)
                    else profile.schedule_matrix
                )
                profile_interval = profile.calculated_interval_minutes

                if isinstance(matrix_data, list):
                    schedules.extend(
                        await self._parse_list_matrix(
                            profile, matrix_data, profile_interval
                        )
                    )
                elif isinstance(matrix_data, dict):
                    schedules.extend(
                        await self._parse_dict_matrix(
                            profile, matrix_data, profile_interval
                        )
                    )
                else:
                    logger.warning(
                        f"[EXTRACT_SCHEDULES] 지원하지 않는 schedule_matrix 형식: profile_id={profile.id}"
                    )

            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                logger.warning(
                    f"[EXTRACT_SCHEDULES] 프로파일 스케줄 파싱 오류: profile_id={profile.id}, error={e}"
                )
                continue

        logger.debug(
            f"[EXTRACT_SCHEDULES] group_id={group.id}, schedule_count={len(schedules)}"
        )
        return schedules

    async def _parse_list_matrix(
        self, profile: PublishProfile, matrix_data: List, profile_interval: int
    ) -> List[ScheduleInfo]:
        """2D 배열 형식 스케줄 파싱"""
        schedules = []
        for day in range(min(7, len(matrix_data))):
            day_schedule = matrix_data[day]
            if isinstance(day_schedule, list):
                for hour in range(min(24, len(day_schedule))):
                    if day_schedule[hour]:
                        minute = await self.slot_service.calculate_optimal_minute(
                            profile.id, day, hour, profile_interval
                        )
                        schedules.append(
                            ScheduleInfo(
                                profile_id=profile.id,
                                profile_name=profile.name,
                                day_of_week=day,
                                hour=hour,
                                minute=minute,
                            )
                        )
        return schedules

    async def _parse_dict_matrix(
        self, profile: PublishProfile, matrix_data: Dict, profile_interval: int
    ) -> List[ScheduleInfo]:
        """딕셔너리 형식 스케줄 파싱"""
        schedules = []
        for day in range(7):
            day_str = str(day)
            if day_str in matrix_data:
                for hour_str, is_active in matrix_data[day_str].items():
                    if is_active:
                        hour = int(hour_str)
                        minute = await self.slot_service.calculate_optimal_minute(
                            profile.id, day, hour, profile_interval
                        )
                        schedules.append(
                            ScheduleInfo(
                                profile_id=profile.id,
                                profile_name=profile.name,
                                day_of_week=day,
                                hour=hour,
                                minute=minute,
                            )
                        )
        return schedules

    async def add_blogs_with_validation(
        self, user: User, group: ProfileGroup, blog_ids: List[int]
    ) -> Dict[str, Any]:
        """블로그 목록을 플랫폼별로 검증하여 추가"""
        results = {"success_count": 0, "failed_blogs": [], "warnings": []}

        for blog_id in blog_ids:
            try:
                blog_query = select(Blog).where(
                    and_(Blog.id == blog_id, Blog.user_id == user.id)
                )
                blog_result = await self.db.execute(blog_query)
                blog = blog_result.scalar_one_or_none()

                if not blog:
                    results["failed_blogs"].append(
                        {"blog_id": blog_id, "reason": "블로그를 찾을 수 없습니다"}
                    )
                    continue

                if blog.is_blogger:
                    add_result = await self._add_blogger_blog_with_slot_check(
                        group, blog
                    )
                    if not add_result.success:
                        results["failed_blogs"].append(
                            {
                                "blog_id": blog_id,
                                "blog_name": blog.name,
                                "reason": add_result.message,
                                "conflicts": add_result.conflicts,
                            }
                        )
                        logger.warning(
                            f"[ADD_BLOGS] Blogger 블로그 추가 실패: {blog.name} - {add_result.message}"
                        )
                        continue

                    if add_result.reserved_slots:
                        results["warnings"].append(
                            f"블로그 '{blog.name}': {len(add_result.reserved_slots)}개 슬롯 예약"
                        )
                else:
                    await self._add_blog_direct(group.id, blog_id)

                results["success_count"] += 1

            except Exception as e:
                logger.error(
                    f"[ADD_BLOGS] 블로그 추가 오류: blog_id={blog_id}, error={e}"
                )
                results["failed_blogs"].append(
                    {"blog_id": blog_id, "reason": f"처리 중 오류: {str(e)}"}
                )

        return results

    async def release_existing_blogger_slots(self, group_id: int) -> None:
        """그룹의 기존 Blogger 블로그 슬롯 해제"""
        query = (
            select(Blog)
            .join(BlogGroupLink)
            .where(
                and_(
                    BlogGroupLink.group_id == group_id,
                    Blog.platform == BlogPlatform.BLOGGER,
                    Blog.google_credential_id.isnot(None),
                )
            )
        )
        result = await self.db.execute(query)
        blogger_blogs = result.scalars().all()

        for blog in blogger_blogs:
            try:
                slot_manager = BloggerGlobalSlotManager(
                    self.db, blog.google_credential_id
                )
                await slot_manager.release_slots_by_blog(blog.id, group_id)
                logger.debug(
                    f"[RELEASE_SLOTS] 해제 완료: blog_id={blog.id}, group_id={group_id}"
                )
            except Exception as e:
                logger.error(f"[RELEASE_SLOTS] 해제 실패: blog_id={blog.id}, error={e}")

        if blogger_blogs:
            logger.info(
                f"[RELEASE_SLOTS] 그룹 {group_id}: {len(blogger_blogs)}개 Blogger 블로그 슬롯 해제"
            )
