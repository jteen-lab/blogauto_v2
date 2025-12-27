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

            # Google 정책 조회
            from ..models.google_account_policy import GoogleAccountPolicy
            from sqlalchemy import select

            policy_query = select(GoogleAccountPolicy).where(
                GoogleAccountPolicy.google_credential_id == blog.google_credential_id
            )
            policy_result = await self.db.execute(policy_query)
            policy = policy_result.scalar_one_or_none()

            if not policy:
                return AddBlogResult(
                    success=False,
                    message="Google 계정 정책을 찾을 수 없습니다"
                )

            # 각 스케줄에 대해 가용 minute 자동 할당
            adjusted_schedules = []
            conflicts = []

            for schedule in schedules:
                available_minute = await self._find_available_minute(
                    blog.google_credential_id,
                    schedule.day_of_week,
                    schedule.hour,
                    policy.min_interval_minutes
                )

                if available_minute is None:
                    # 이 시간대는 모든 슬롯 점유됨 - 충돌 기록
                    conflicts.append(f"[{schedule.day_of_week}일 {schedule.hour:02d}시] 모든 슬롯 점유됨")
                else:
                    # 가용 minute으로 스케줄 업데이트
                    adjusted_schedule = ScheduleInfo(
                        profile_id=schedule.profile_id,
                        profile_name=schedule.profile_name,
                        day_of_week=schedule.day_of_week,
                        hour=schedule.hour,
                        minute=available_minute
                    )
                    adjusted_schedules.append(adjusted_schedule)

                    logger.info(f"[AUTO_SLOT_ALLOCATION] 블로그 {blog.id}: {schedule.day_of_week}일 {schedule.hour:02d}:{available_minute:02d} 할당")

            # 충돌이 발생한 경우
            if conflicts:
                return AddBlogResult(
                    success=False,
                    message=f"시간 슬롯 충돌 ({len(conflicts)}개): " + ", ".join(conflicts),
                    conflicts=conflicts
                )

            # 가용 슬롯을 찾았으므로 직접 예약 진행 (이미 충돌 검사 완료)
            reservations = [
                SlotReservation(
                    profile_id=schedule.profile_id,
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=schedule.minute
                )
                for schedule in adjusted_schedules
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
                message=f"블로그가 성공적으로 추가되었습니다 ({len(reserved_slots)}개 슬롯 자동 할당)",
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

                # 프로파일 간격 계산
                profile_interval = profile.calculated_interval_minutes

                # 2D 배열 형식과 딕셔너리 형식 모두 지원
                if isinstance(matrix_data, list):
                    # 2D 배열 형식: [[false,false,false,true,true,...], [false,false,...], ...]
                    for day in range(min(7, len(matrix_data))):
                        day_schedule = matrix_data[day]
                        if isinstance(day_schedule, list):
                            for hour in range(min(24, len(day_schedule))):
                                if day_schedule[hour]:  # true인 경우
                                    # 프로파일 간격에 따른 분 단위 배치
                                    minute = await self._calculate_optimal_minute(
                                        profile.id, day, hour, profile_interval
                                    )
                                    schedule = ScheduleInfo(
                                        profile_id=profile.id,
                                        profile_name=profile.name,
                                        day_of_week=day,
                                        hour=hour,
                                        minute=minute
                                    )
                                    schedules.append(schedule)

                elif isinstance(matrix_data, dict):
                    # 딕셔너리 형식: {"0": {"9": true, "10": true}, ...} (기존 형식)
                    for day in range(7):  # 월요일=0 ~ 일요일=6
                        day_str = str(day)
                        if day_str in matrix_data:
                            for hour_str, is_active in matrix_data[day_str].items():
                                if is_active:
                                    hour = int(hour_str)
                                    # 프로파일 간격에 따른 분 단위 배치
                                    minute = await self._calculate_optimal_minute(
                                        profile.id, day, hour, profile_interval
                                    )
                                    schedule = ScheduleInfo(
                                        profile_id=profile.id,
                                        profile_name=profile.name,
                                        day_of_week=day,
                                        hour=hour,
                                        minute=minute
                                    )
                                    schedules.append(schedule)

                else:
                    logger.warning(f"[EXTRACT_SCHEDULES] 지원하지 않는 schedule_matrix 형식: profile_id={profile.id}, type={type(matrix_data)}")

            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
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

    async def _calculate_optimal_minute(
        self,
        profile_id: int,
        day_of_week: int,
        hour: int,
        profile_interval_minutes: int
    ) -> int:
        """프로파일 간격에 따른 최적 분 단위 계산"""
        # 프로파일 ID를 기반으로 일관된 분 할당
        # 같은 프로파일은 항상 같은 패턴으로 분이 배정됨

        # 최소 간격을 기준으로 시간당 가능한 슬롯 수 계산
        min_interval = max(15, profile_interval_minutes)  # 최소 15분 간격 보장

        # 시간당 슬롯 수 (15분 단위로 정규화)
        # 15분=4슬롯, 30분=2슬롯, 60분=1슬롯
        normalized_interval = max(15, (min_interval // 15) * 15)  # 15분 단위로 반올림
        slots_per_hour = 60 // normalized_interval

        if slots_per_hour <= 1:
            # 시간당 1슬롯만 가능하면 항상 0분
            return 0

        # 프로파일 ID 기반 해시로 일관된 분 선택
        # 같은 프로파일은 항상 같은 슬롯을 선택하도록
        profile_hash = hash(f"{profile_id}_{day_of_week}_{hour}") % slots_per_hour
        minute = profile_hash * normalized_interval

        # 시간 경계 확인
        if minute >= 60:
            minute = 0

        logger.debug(f"[CALC_MINUTE] profile_id={profile_id}, interval={min_interval}, "
                    f"slots_per_hour={slots_per_hour}, minute={minute}")

        return minute

    async def _add_slot_distribution_logic(
        self,
        schedules: List[ScheduleInfo],
        google_credential_id: int
    ) -> List[ScheduleInfo]:
        """
        같은 Google 계정의 여러 블로그가 동일 시간대 사용 시 분 단위 분산

        Args:
            schedules: 스케줄 정보 리스트
            google_credential_id: Google 계정 ID

        Returns:
            분 단위가 조정된 스케줄 정보 리스트
        """
        # 시간대별로 스케줄 그룹화
        time_groups = {}
        for schedule in schedules:
            time_key = f"{schedule.day_of_week}_{schedule.hour}"
            if time_key not in time_groups:
                time_groups[time_key] = []
            time_groups[time_key].append(schedule)

        adjusted_schedules = []

        for time_key, time_schedules in time_groups.items():
            if len(time_schedules) == 1:
                # 단일 스케줄은 그대로 사용
                adjusted_schedules.extend(time_schedules)
                continue

            # 동일 시간대의 여러 스케줄 분산 처리
            day_of_week, hour = map(int, time_key.split('_'))

            # 15분 단위 슬롯 계산 (0, 15, 30, 45분)
            available_minutes = [0, 15, 30, 45]

            for i, schedule in enumerate(time_schedules):
                # 라운드 로빈 방식으로 분 배정
                assigned_minute = available_minutes[i % len(available_minutes)]

                # 새로운 스케줄 정보 생성
                adjusted_schedule = ScheduleInfo(
                    profile_id=schedule.profile_id,
                    profile_name=schedule.profile_name,
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=assigned_minute
                )
                adjusted_schedules.append(adjusted_schedule)

                logger.debug(f"[SLOT_DISTRIBUTION] {time_key}시간대 {i+1}번째 스케줄: minute={assigned_minute}")

        return adjusted_schedules

    async def _get_existing_slots(
        self,
        google_credential_id: int,
        day_of_week: int,
        hour: int
    ) -> List[BloggerGlobalSlot]:
        """특정 시간대에 이미 예약된 슬롯 조회"""
        from ..models.blogger_global_slot import BloggerGlobalSlot
        from sqlalchemy import select, and_

        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == google_credential_id,
                BloggerGlobalSlot.day_of_week == day_of_week,
                BloggerGlobalSlot.hour == hour
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def _find_available_minute(
        self,
        google_credential_id: int,
        day_of_week: int,
        hour: int,
        min_interval_minutes: int
    ) -> Optional[int]:
        """
        해당 시간대에서 사용 가능한 minute 찾기

        Args:
            google_credential_id: Google 계정 ID
            day_of_week: 요일 (0=월요일)
            hour: 시간 (0-23)
            min_interval_minutes: 최소 간격 (분)

        Returns:
            사용 가능한 minute (0-59) 또는 None (모든 슬롯 점유됨)
        """
        # 최소 간격을 15분 단위로 정규화
        normalized_interval = max(15, (min_interval_minutes // 15) * 15)
        slots_per_hour = 60 // normalized_interval

        # 가용 minute 목록 생성 (0, 15, 30, 45 등)
        available_minutes = [i * normalized_interval for i in range(slots_per_hour)]

        # 이미 예약된 슬롯 조회
        existing_slots = await self._get_existing_slots(
            google_credential_id, day_of_week, hour
        )
        occupied_minutes = {slot.minute for slot in existing_slots}

        # 사용 가능한 첫 번째 minute 반환
        for minute in available_minutes:
            if minute not in occupied_minutes:
                logger.debug(f"[FIND_MINUTE] {day_of_week}일 {hour}시: minute={minute} 가용")
                return minute

        # 모든 슬롯이 점유됨
        logger.warning(f"[FIND_MINUTE] {day_of_week}일 {hour}시: 모든 슬롯 점유됨 (occupied: {occupied_minutes})")
        return None
