"""
그룹 서비스
"""
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import json

from ..models import User, ProfileGroup, GroupProfileLink, BlogGroupLink, PublishProfile, Blog
from ..models.blog import BlogPlatform
from ..models.blogger_global_slot import BloggerGlobalSlot
from ..schemas.blogger_slot import AddBlogResult, SlotInfo, SlotConflict, ScheduleInfo, SlotReservation
from ..core.logger import get_logger
from .blogger_slot_service import BloggerGlobalSlotManager

logger = get_logger("group_service", "app.log")


class GroupService:
    """그룹 관리 서비스"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_groups(self, user: User) -> List[ProfileGroup]:
        """사용자의 그룹 목록 조회"""
        query = select(ProfileGroup).where(
            ProfileGroup.user_id == user.id
        ).options(
            selectinload(ProfileGroup.profile_links),
            selectinload(ProfileGroup.blog_links)
        ).order_by(ProfileGroup.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_group_by_id(self, user: User, group_id: int) -> Optional[ProfileGroup]:
        """그룹 상세 조회"""
        query = select(ProfileGroup).where(
            and_(
                ProfileGroup.id == group_id,
                ProfileGroup.user_id == user.id
            )
        ).options(
            selectinload(ProfileGroup.profile_links).selectinload(GroupProfileLink.profile),
            selectinload(ProfileGroup.blog_links).selectinload(BlogGroupLink.blog)
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def create_group(self, user: User, data: Dict[str, Any]) -> ProfileGroup:
        """그룹 생성"""
        profile_ids = data.pop("profile_ids", [])
        blog_ids = data.pop("blog_ids", [])

        group = ProfileGroup(user_id=user.id, **data)
        self.db.add(group)
        await self.db.flush()

        # 프로파일 연결
        for pid in profile_ids:
            link = GroupProfileLink(group_id=group.id, profile_id=pid)
            self.db.add(link)

        await self.db.commit()  # 프로파일 연결 먼저 커밋

        # 블로그 연결 (슬롯 검증 포함)
        blog_results = {"success_count": 0, "failed_blogs": [], "warnings": []}
        if blog_ids:
            # 관계 데이터 로딩 (스케줄 추출을 위해)
            await self.db.refresh(group, ['profile_links'])
            blog_results = await self._add_blogs_with_validation(user, group, blog_ids)

        await self.db.commit()
        await self.db.refresh(group)

        # 관계 데이터 로딩
        await self.db.refresh(group, ['profile_links', 'blog_links'])

        # 로그 기록
        total_requested = len(blog_ids)
        success_count = blog_results["success_count"]
        failed_count = len(blog_results["failed_blogs"])

        log_message = f"[GROUP] 생성 완료 | user={user.id} | group={group.id} | profiles={len(profile_ids)} | blogs={success_count}/{total_requested} 성공"
        if blog_results["warnings"]:
            log_message += f" | 경고: {'; '.join(blog_results['warnings'])}"
        if blog_results["failed_blogs"]:
            log_message += f" | 실패: {failed_count}개"

        logger.info(log_message)

        # 실패한 블로그가 있으면 경고 로그
        for failed in blog_results["failed_blogs"]:
            logger.warning(f"[GROUP] 블로그 추가 실패: {failed}")

        return group
    
    async def update_group(self, user: User, group_id: int, data: Dict[str, Any]) -> ProfileGroup:
        """그룹 수정"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")

        profile_ids = data.pop("profile_ids", None)
        blog_ids = data.pop("blog_ids", None)

        # 기본 정보 업데이트
        for key, value in data.items():
            if value is not None and hasattr(group, key):
                setattr(group, key, value)

        # 프로파일 연결 업데이트
        if profile_ids is not None:
            await self.db.execute(
                delete(GroupProfileLink).where(GroupProfileLink.group_id == group_id)
            )
            for pid in profile_ids:
                link = GroupProfileLink(group_id=group_id, profile_id=pid)
                self.db.add(link)

        # 블로그 연결 업데이트 (슬롯 검증 포함)
        blog_results = {"success_count": 0, "failed_blogs": [], "warnings": []}
        if blog_ids is not None:
            # 기존 Blogger 블로그들의 슬롯 해제
            await self._release_existing_blogger_slots(group_id)

            # 기존 연결 삭제
            await self.db.execute(
                delete(BlogGroupLink).where(BlogGroupLink.group_id == group_id)
            )
            await self.db.commit()  # 프로파일 변경사항 먼저 적용

            if blog_ids:  # 새 블로그들 추가
                # 관계 데이터 새로고침
                await self.db.refresh(group, ['profile_links'])
                blog_results = await self._add_blogs_with_validation(user, group, blog_ids)

        await self.db.commit()
        await self.db.refresh(group)

        # 로그 기록
        blog_log = "변경없음"
        if blog_ids is not None:
            total_requested = len(blog_ids)
            success_count = blog_results["success_count"]
            failed_count = len(blog_results["failed_blogs"])
            blog_log = f"{success_count}/{total_requested} 성공"

            if blog_results["warnings"]:
                blog_log += f" (경고: {len(blog_results['warnings'])}개)"
            if failed_count > 0:
                blog_log += f" (실패: {failed_count}개)"

        logger.info(f"[GROUP] 수정 완료 | group={group_id} | profiles={len(profile_ids) if profile_ids else '변경없음'} | blogs={blog_log}")

        # 실패한 블로그가 있으면 경고 로그
        for failed in blog_results["failed_blogs"]:
            logger.warning(f"[GROUP] 블로그 수정 실패: {failed}")

        return group
    
    async def delete_group(self, user: User, group_id: int) -> bool:
        """그룹 삭제"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        await self.db.delete(group)
        await self.db.commit()
        
        logger.info(f"[GROUP] 삭제 완료 | group={group_id}")
        return True
    
    async def assign_blogs(self, user: User, group_id: int, blog_ids: List[int]) -> ProfileGroup:
        """그룹에 블로그 할당"""
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        # 기존 연결 삭제
        await self.db.execute(
            delete(BlogGroupLink).where(BlogGroupLink.group_id == group_id)
        )
        
        # 새 연결 생성
        for bid in blog_ids:
            link = BlogGroupLink(group_id=group_id, blog_id=bid)
            self.db.add(link)
        
        await self.db.commit()
        await self.db.refresh(group)
        
        logger.info(f"[GROUP] 블로그 할당 | group={group_id} | blogs={blog_ids}")
        return group
    
    async def copy_group(self, user: User, group_id: int, new_name: str) -> ProfileGroup:
        """그룹 복사"""
        original = await self.get_group_by_id(user, group_id)
        if not original:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")
        
        # 새 그룹 생성
        new_group = ProfileGroup(
            user_id=user.id,
            name=new_name,
            description=original.description,
            is_active=original.is_active
        )
        self.db.add(new_group)
        await self.db.flush()
        
        # 프로파일 연결 복사
        for link in original.profile_links:
            new_link = GroupProfileLink(group_id=new_group.id, profile_id=link.profile_id)
            self.db.add(new_link)
        
        await self.db.commit()
        await self.db.refresh(new_group)
        
        logger.info(f"[GROUP] 복사 완료 | original={group_id} | new={new_group.id}")
        return new_group

    async def add_blog_with_slot_validation(
        self,
        user: User,
        group_id: int,
        blog_id: int
    ) -> AddBlogResult:
        """
        블로그 추가 시 슬롯 검증 포함

        Returns:
            AddBlogResult: 성공/실패 결과와 충돌 정보
        """
        logger.info(f"[ADD_BLOG_WITH_SLOT] group_id={group_id}, blog_id={blog_id}")

        # 그룹 및 블로그 검증
        group = await self.get_group_by_id(user, group_id)
        if not group:
            return AddBlogResult(
                success=False,
                message=f"그룹을 찾을 수 없습니다: {group_id}"
            )

        blog_query = select(Blog).where(
            and_(Blog.id == blog_id, Blog.user_id == user.id)
        )
        blog_result = await self.db.execute(blog_query)
        blog = blog_result.scalar_one_or_none()

        if not blog:
            return AddBlogResult(
                success=False,
                message=f"블로그를 찾을 수 없습니다: {blog_id}"
            )

        # WordPress 블로그는 바로 추가
        if blog.platform.value != "blogger":
            await self._add_blog_direct(group_id, blog_id)
            return AddBlogResult(
                success=True,
                message=f"{blog.platform.value} 블로그가 성공적으로 추가되었습니다"
            )

        # Blogger 블로그는 슬롯 검증 필요
        if not blog.google_credential_id:
            return AddBlogResult(
                success=False,
                message="Blogger 블로그에 Google 계정이 연결되지 않았습니다"
            )

        return await self._add_blogger_blog_with_slot_check(group, blog)

    async def remove_blog_with_slot_release(
        self,
        user: User,
        group_id: int,
        blog_id: int
    ) -> bool:
        """블로그 제거 시 슬롯 해제 포함"""
        logger.info(f"[REMOVE_BLOG_WITH_SLOT] group_id={group_id}, blog_id={blog_id}")

        # 그룹 검증
        group = await self.get_group_by_id(user, group_id)
        if not group:
            raise ValueError(f"그룹을 찾을 수 없습니다: {group_id}")

        # 블로그 정보 조회
        blog_query = select(Blog).where(Blog.id == blog_id)
        blog_result = await self.db.execute(blog_query)
        blog = blog_result.scalar_one_or_none()

        # 블로그-그룹 연결 해제
        await self.db.execute(
            delete(BlogGroupLink).where(
                and_(
                    BlogGroupLink.group_id == group_id,
                    BlogGroupLink.blog_id == blog_id
                )
            )
        )

        # Blogger 블로그이고 Google 계정이 있다면 슬롯 해제
        if blog and blog.platform.value == "blogger" and blog.google_credential_id:
            slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)
            await slot_manager.release_slots_by_blog(blog_id, group_id)

        await self.db.commit()
        logger.info(f"[REMOVE_BLOG_WITH_SLOT] 완료: group_id={group_id}, blog_id={blog_id}")
        return True

    async def _add_blog_direct(self, group_id: int, blog_id: int) -> None:
        """블로그 직접 추가 (WordPress 등)"""
        # 기존 연결 확인
        existing_query = select(BlogGroupLink).where(
            and_(
                BlogGroupLink.group_id == group_id,
                BlogGroupLink.blog_id == blog_id
            )
        )
        result = await self.db.execute(existing_query)
        if result.scalar_one_or_none():
            logger.info(f"[ADD_BLOG_DIRECT] 이미 연결됨: group_id={group_id}, blog_id={blog_id}")
            return

        # 새 연결 생성
        link = BlogGroupLink(group_id=group_id, blog_id=blog_id)
        self.db.add(link)
        await self.db.commit()

    async def _add_blogger_blog_with_slot_check(
        self,
        group: ProfileGroup,
        blog: Blog
    ) -> AddBlogResult:
        """Blogger 블로그 슬롯 검증 후 추가"""
        slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)

        try:
            # 그룹의 프로파일 스케줄 분석
            schedules = await self._extract_group_schedules(group)

            if not schedules:
                # 스케줄이 없으면 바로 추가
                await self._add_blog_direct(group.id, blog.id)
                return AddBlogResult(
                    success=True,
                    message="스케줄이 없는 그룹에 블로그가 추가되었습니다"
                )

            # 슬롯 검증
            validation_result = await slot_manager.validate_blog_schedules(blog.id, schedules)

            if validation_result.valid:
                # 모든 슬롯 예약 가능 - 실제 예약 진행
                reservations = [
                    SlotReservation(
                        profile_id=schedule.profile_id,
                        day_of_week=schedule.day_of_week,
                        hour=schedule.hour,
                        minute=schedule.minute
                    )
                    for schedule in schedules
                ]

                reserved_slots = await slot_manager.reserve_multiple_slots(
                    blog_id=blog.id,
                    group_id=group.id,
                    reservations=reservations
                )

                # 블로그-그룹 연결
                await self._add_blog_direct(group.id, blog.id)

                return AddBlogResult(
                    success=True,
                    message=f"블로그가 성공적으로 추가되었습니다 ({len(reserved_slots)}개 슬롯 예약)",
                    reserved_slots=[
                        SlotInfo(
                            day_of_week=slot.day_of_week,
                            hour=slot.hour,
                            minute=slot.minute,
                            blog_id=blog.id,
                            blog_name=blog.name,
                            group_id=group.id
                        )
                        for slot in reserved_slots
                    ]
                )

            else:
                # 충돌 발생
                return AddBlogResult(
                    success=False,
                    message=f"시간 슬롯 충돌 ({len(validation_result.conflicts)}개)",
                    conflicts=validation_result.conflicts,
                    suggestions=validation_result.suggestions
                )

        except Exception as e:
            logger.error(f"[ADD_BLOGGER_BLOG] 오류: {e}")
            return AddBlogResult(
                success=False,
                message=f"블로그 추가 중 오류 발생: {str(e)}"
            )

    async def _extract_group_schedules(self, group: ProfileGroup) -> List[ScheduleInfo]:
        """그룹의 프로파일 스케줄 추출"""
        schedules = []

        for profile_link in group.profile_links:
            # 프로파일 정보 로딩
            profile_query = select(PublishProfile).where(
                PublishProfile.id == profile_link.profile_id
            )
            profile_result = await self.db.execute(profile_query)
            profile = profile_result.scalar_one_or_none()

            if not profile or not profile.schedule_matrix:
                continue

            try:
                # schedule_matrix는 JSON 문자열로 저장됨
                matrix_data = json.loads(profile.schedule_matrix) if isinstance(profile.schedule_matrix, str) else profile.schedule_matrix

                # 7x24 매트릭스에서 활성 스케줄 추출
                for day in range(7):  # 월요일=0 ~ 일요일=6
                    day_str = str(day)
                    if day_str in matrix_data:
                        for hour_str, is_active in matrix_data[day_str].items():
                            if is_active:
                                hour = int(hour_str)
                                # 기본 분은 0분으로 설정 (필요시 프로파일 설정에서 추출)
                                schedule = ScheduleInfo(
                                    profile_id=profile.id,
                                    profile_name=profile.name,
                                    day_of_week=day,
                                    hour=hour,
                                    minute=0  # 기본값, 향후 프로파일 세밀 설정으로 확장 가능
                                )
                                schedules.append(schedule)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"[EXTRACT_SCHEDULES] 프로파일 스케줄 파싱 오류: profile_id={profile.id}, error={e}")
                continue

        logger.debug(f"[EXTRACT_SCHEDULES] group_id={group.id}, schedule_count={len(schedules)}")
        return schedules

    async def _add_blogs_with_validation(
        self,
        user: User,
        group: ProfileGroup,
        blog_ids: List[int]
    ) -> Dict[str, Any]:
        """블로그 목록을 플랫폼별로 검증하여 추가"""
        results = {
            "success_count": 0,
            "failed_blogs": [],
            "warnings": []
        }

        for blog_id in blog_ids:
            try:
                # 블로그 정보 조회
                blog_query = select(Blog).where(
                    and_(Blog.id == blog_id, Blog.user_id == user.id)
                )
                blog_result = await self.db.execute(blog_query)
                blog = blog_result.scalar_one_or_none()

                if not blog:
                    results["failed_blogs"].append({
                        "blog_id": blog_id,
                        "reason": "블로그를 찾을 수 없습니다"
                    })
                    continue

                # Blogger 플랫폼인 경우 슬롯 검증
                if blog.is_blogger:
                    add_result = await self._add_blogger_blog_with_slot_check(group, blog)
                    if not add_result.success:
                        results["failed_blogs"].append({
                            "blog_id": blog_id,
                            "blog_name": blog.name,
                            "reason": add_result.message,
                            "conflicts": add_result.conflicts
                        })
                        logger.warning(f"[ADD_BLOGS] Blogger 블로그 추가 실패: {blog.name} - {add_result.message}")
                        continue

                    if add_result.reserved_slots:
                        results["warnings"].append(f"블로그 '{blog.name}': {len(add_result.reserved_slots)}개 슬롯 예약")

                else:
                    # WordPress 등 다른 플랫폼은 바로 추가
                    await self._add_blog_direct(group.id, blog_id)

                results["success_count"] += 1

            except Exception as e:
                logger.error(f"[ADD_BLOGS] 블로그 추가 오류: blog_id={blog_id}, error={e}")
                results["failed_blogs"].append({
                    "blog_id": blog_id,
                    "reason": f"처리 중 오류: {str(e)}"
                })

        return results

    async def _release_existing_blogger_slots(self, group_id: int) -> None:
        """그룹의 기존 Blogger 블로그 슬롯 해제"""
        # 그룹에 연결된 Blogger 블로그들 조회
        query = select(Blog).join(BlogGroupLink).where(
            and_(
                BlogGroupLink.group_id == group_id,
                Blog.platform == BlogPlatform.BLOGGER,
                Blog.google_credential_id.isnot(None)
            )
        )
        result = await self.db.execute(query)
        blogger_blogs = result.scalars().all()

        # 각 블로그의 슬롯 해제
        for blog in blogger_blogs:
            try:
                slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)
                await slot_manager.release_slots_by_blog(blog.id, group_id)
                logger.debug(f"[RELEASE_SLOTS] 해제 완료: blog_id={blog.id}, group_id={group_id}")
            except Exception as e:
                logger.error(f"[RELEASE_SLOTS] 해제 실패: blog_id={blog.id}, error={e}")

        if blogger_blogs:
            logger.info(f"[RELEASE_SLOTS] 그룹 {group_id}: {len(blogger_blogs)}개 Blogger 블로그 슬롯 해제")
