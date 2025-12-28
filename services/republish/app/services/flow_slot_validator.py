"""
플로우 슬롯 검증 서비스

Features:
- Blogger 블로그 슬롯 검증
- 모듈 기반 스케줄 추출
- 가용 슬롯 자동 할당
- 슬롯 해제 관리
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import json

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.module import Module
from ..models.blog import Blog, BlogPlatform
from ..models.google_account_policy import GoogleAccountPolicy
from ..models.blogger_global_slot import BloggerGlobalSlot
from ..models.flow_blog import FlowBlog
from ..schemas.blogger_slot import AddBlogResult, SlotInfo, ScheduleInfo, SlotReservation
from ..services.blogger_slot_service import BloggerGlobalSlotManager
from ..core.logger import get_logger

logger = get_logger("flow_slot_validator", "app.log")


class FlowSlotValidator:
    """플로우 슬롯 검증 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_single_blog_with_validation(
        self,
        user_id: int,
        flow: Flow,
        blog_id: int
    ) -> Dict[str, Any]:
        """개별 블로그 슬롯 검증 후 추가"""
        try:
            # 블로그 정보 조회
            blog_query = select(Blog).where(
                and_(Blog.id == blog_id, Blog.user_id == user_id)
            )
            blog_result = await self.db.execute(blog_query)
            blog = blog_result.scalar_one_or_none()

            if not blog:
                return {
                    "success": False,
                    "error": {
                        "blog_id": blog_id,
                        "reason": "블로그를 찾을 수 없습니다"
                    }
                }

            # Blogger 플랫폼인 경우 슬롯 검증
            if blog.is_blogger:
                add_result = await self.add_blogger_blog_with_slot_check(flow, blog)
                if not add_result.success:
                    return {
                        "success": False,
                        "error": {
                            "blog_id": blog_id,
                            "blog_name": blog.name,
                            "reason": add_result.message,
                            "conflicts": getattr(add_result, 'conflicts', [])
                        }
                    }

                # 슬롯 예약 성공
                await self.add_blog_direct(flow.id, blog_id)
                warning = None
                if hasattr(add_result, 'reserved_slots') and add_result.reserved_slots:
                    warning = f"블로그 '{blog.name}': {len(add_result.reserved_slots)}개 슬롯 예약"

                return {
                    "success": True,
                    "warning": warning
                }
            else:
                # WordPress 등 다른 플랫폼은 바로 추가
                await self.add_blog_direct(flow.id, blog_id)
                return {"success": True}

        except Exception as e:
            logger.error(f"[ADD_SINGLE_BLOG] 오류: blog_id={blog_id}, error={e}")
            return {
                "success": False,
                "error": {
                    "blog_id": blog_id,
                    "reason": f"처리 중 오류: {str(e)}"
                }
            }

    async def add_blog_direct(self, flow_id: int, blog_id: int) -> None:
        """블로그-플로우 직접 연결"""
        link = FlowBlog(flow_id=flow_id, blog_id=blog_id)
        self.db.add(link)

    async def release_flow_blogger_slots(self, flow_id: int) -> None:
        """플로우의 모든 Blogger 블로그 슬롯 해제"""
        # 플로우에 연결된 Blogger 블로그들 조회
        query = select(Blog).join(FlowBlog).where(
            and_(
                FlowBlog.flow_id == flow_id,
                Blog.platform == BlogPlatform.BLOGGER,
                Blog.google_credential_id.isnot(None)
            )
        )
        result = await self.db.execute(query)
        blogger_blogs = result.scalars().all()

        # 각 블로그의 슬롯 해제
        for blog in blogger_blogs:
            await self.release_single_blog_slots(flow_id, blog.id)

    async def release_single_blog_slots(self, flow_id: int, blog_id: int) -> None:
        """개별 Blogger 블로그 슬롯 해제"""
        try:
            # 블로그 정보 조회
            blog_query = select(Blog).where(Blog.id == blog_id)
            blog_result = await self.db.execute(blog_query)
            blog = blog_result.scalar_one_or_none()

            if not blog or not blog.google_credential_id:
                return

            slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)
            await slot_manager.release_blog_slots(blog_id)
            logger.info(f"[SLOT_RELEASE] 블로그 {blog_id} 슬롯 해제 완료")

        except Exception as e:
            logger.error(f"[SLOT_RELEASE] 오류: blog_id={blog_id}, error={e}")

    async def add_blogger_blog_with_slot_check(
        self,
        flow: Flow,
        blog: Blog
    ) -> AddBlogResult:
        """Blogger 블로그 슬롯 검증 후 추가 (모듈 기반)"""
        slot_manager = BloggerGlobalSlotManager(self.db, blog.google_credential_id)

        try:
            # 플로우의 모듈 스케줄 분석
            schedules = await self.extract_flow_schedules(flow)

            if not schedules:
                # 스케줄이 없으면 바로 추가
                return AddBlogResult(
                    success=True,
                    message="스케줄이 없는 플로우에 블로그가 추가되었습니다"
                )

            # Google 정책 조회
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
                available_minute = await self.find_available_minute(
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
                        profile_id=schedule.profile_id,  # 모듈 ID를 profile_id로 사용
                        profile_name=schedule.profile_name,  # 모듈 이름
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
                group_id=flow.id,  # flow_id를 group_id로 사용
                reservations=reservations
            )

            return AddBlogResult(
                success=True,
                message=f"블로그가 성공적으로 추가되었습니다 ({len(reserved_slots)}개 슬롯 자동 할당)",
                reserved_slots=[
                    SlotInfo(
                        day_of_week=slot.day_of_week,
                        hour=slot.hour,
                        minute=slot.minute,
                        blog_id=slot.blog_id
                    )
                    for slot in reserved_slots
                ]
            )

        except Exception as e:
            logger.error(f"[BLOGGER_SLOT_CHECK] 오류: {e}")
            return AddBlogResult(
                success=False,
                message=f"슬롯 검증 중 오류가 발생했습니다: {str(e)}"
            )

    async def extract_flow_schedules(self, flow: Flow) -> List[ScheduleInfo]:
        """플로우의 모듈 스케줄 추출"""
        schedules = []

        # 플로우에 연결된 모듈들 조회
        modules_query = (
            select(Module)
            .join(FlowModule)
            .where(FlowModule.flow_id == flow.id)
        )
        modules_result = await self.db.execute(modules_query)
        modules = modules_result.scalars().all()

        for module in modules:
            try:
                if not module.schedule_matrix:
                    logger.debug(f"[EXTRACT_SCHEDULES] module_id={module.id} - 스케줄 매트릭스가 없음")
                    continue

                matrix_data = module.schedule_matrix
                module_interval = module.manual_interval_minutes or 60

                # 스케줄 매트릭스 형식 확인 및 처리
                if isinstance(matrix_data, list) and len(matrix_data) == 7:
                    # 2D 배열 형식: [[false, true, ...], [...], ...]
                    for day, day_schedule in enumerate(matrix_data):
                        if isinstance(day_schedule, list) and len(day_schedule) == 24:
                            for hour, is_active in enumerate(day_schedule):
                                if is_active:
                                    # 모듈 간격에 따른 분 단위 배치
                                    minute = await self.calculate_optimal_minute(
                                        module.id, day, hour, module_interval
                                    )
                                    schedule = ScheduleInfo(
                                        profile_id=module.id,  # 모듈 ID를 profile_id로 사용
                                        profile_name=module.name,
                                        day_of_week=day,
                                        hour=hour,
                                        minute=minute
                                    )
                                    schedules.append(schedule)

                else:
                    logger.warning(f"[EXTRACT_SCHEDULES] 지원하지 않는 schedule_matrix 형식: module_id={module.id}, type={type(matrix_data)}")

            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                logger.warning(f"[EXTRACT_SCHEDULES] 모듈 스케줄 파싱 오류: module_id={module.id}, error={e}")
                continue

        logger.debug(f"[EXTRACT_SCHEDULES] flow_id={flow.id}, schedule_count={len(schedules)}")
        return schedules

    async def calculate_optimal_minute(
        self,
        module_id: int,
        day_of_week: int,
        hour: int,
        interval_minutes: int
    ) -> int:
        """모듈 간격 기반 최적 minute 계산"""
        # 15분 단위로 정규화
        normalized_interval = max(15, (interval_minutes // 15) * 15)

        # 모듈 ID와 시간을 기반으로 일관된 minute 계산
        # 이는 동일한 모듈이 동일한 시간대에 항상 같은 minute을 얻도록 보장
        time_hash = hash((module_id, day_of_week, hour)) % (60 // normalized_interval)
        return (time_hash * normalized_interval) % 60

    async def find_available_minute(
        self,
        google_credential_id: int,
        day_of_week: int,
        hour: int,
        min_interval_minutes: int
    ) -> Optional[int]:
        """해당 시간대에서 사용 가능한 minute 찾기"""
        # 최소 간격을 15분 단위로 정규화
        normalized_interval = max(15, (min_interval_minutes // 15) * 15)
        slots_per_hour = 60 // normalized_interval

        # 가용 minute 목록 생성 (0, 15, 30, 45 등)
        available_minutes = [i * normalized_interval for i in range(slots_per_hour)]

        # 이미 예약된 슬롯 조회
        existing_slots = await self.get_existing_slots(
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

    async def get_existing_slots(
        self,
        google_credential_id: int,
        day_of_week: int,
        hour: int
    ) -> List[BloggerGlobalSlot]:
        """기존 예약된 슬롯 조회"""
        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == google_credential_id,
                BloggerGlobalSlot.day_of_week == day_of_week,
                BloggerGlobalSlot.hour == hour
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()