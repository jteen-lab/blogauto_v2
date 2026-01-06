"""
그룹 슬롯 관리 서비스 - 슬롯 계산/분배/조회
"""

from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.blogger_global_slot import BloggerGlobalSlot
from ..schemas.blogger_slot import ScheduleInfo
from ..core.logger import get_logger

logger = get_logger("group_slot_service", "app.log")


class GroupSlotService:
    """그룹 슬롯 계산 및 분배 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_optimal_minute(
        self,
        profile_id: int,
        day_of_week: int,
        hour: int,
        profile_interval_minutes: int,
    ) -> int:
        """
        프로파일 간격에 따른 최적 분 단위 계산

        같은 프로파일은 항상 일관된 분이 배정됨 (해시 기반)
        """
        min_interval = max(15, profile_interval_minutes)
        normalized_interval = max(15, (min_interval // 15) * 15)
        slots_per_hour = 60 // normalized_interval

        if slots_per_hour <= 1:
            return 0

        profile_hash = hash(f"{profile_id}_{day_of_week}_{hour}") % slots_per_hour
        minute = profile_hash * normalized_interval

        if minute >= 60:
            minute = 0

        logger.debug(
            f"[CALC_MINUTE] profile_id={profile_id}, interval={min_interval}, "
            f"slots_per_hour={slots_per_hour}, minute={minute}"
        )

        return minute

    async def distribute_slots(
        self, schedules: List[ScheduleInfo], google_credential_id: int
    ) -> List[ScheduleInfo]:
        """
        같은 Google 계정의 여러 블로그가 동일 시간대 사용 시 분 단위 분산

        라운드 로빈 방식으로 15분 단위 슬롯 배정
        """
        time_groups = {}
        for schedule in schedules:
            time_key = f"{schedule.day_of_week}_{schedule.hour}"
            if time_key not in time_groups:
                time_groups[time_key] = []
            time_groups[time_key].append(schedule)

        adjusted_schedules = []

        for time_key, time_schedules in time_groups.items():
            if len(time_schedules) == 1:
                adjusted_schedules.extend(time_schedules)
                continue

            day_of_week, hour = map(int, time_key.split("_"))
            available_minutes = [0, 15, 30, 45]

            for i, schedule in enumerate(time_schedules):
                assigned_minute = available_minutes[i % len(available_minutes)]
                adjusted_schedule = ScheduleInfo(
                    profile_id=schedule.profile_id,
                    profile_name=schedule.profile_name,
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=assigned_minute,
                )
                adjusted_schedules.append(adjusted_schedule)
                logger.debug(
                    f"[SLOT_DISTRIBUTION] {time_key}시간대 {i + 1}번째 스케줄: minute={assigned_minute}"
                )

        return adjusted_schedules

    async def get_existing_slots(
        self, google_credential_id: int, day_of_week: int, hour: int
    ) -> List[BloggerGlobalSlot]:
        """특정 시간대에 이미 예약된 슬롯 조회"""
        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == google_credential_id,
                BloggerGlobalSlot.day_of_week == day_of_week,
                BloggerGlobalSlot.hour == hour,
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def find_available_minute(
        self,
        google_credential_id: int,
        day_of_week: int,
        hour: int,
        min_interval_minutes: int,
    ) -> Optional[int]:
        """
        해당 시간대에서 사용 가능한 minute 찾기

        Returns:
            사용 가능한 minute (0-59) 또는 None (모든 슬롯 점유됨)
        """
        normalized_interval = max(15, (min_interval_minutes // 15) * 15)
        slots_per_hour = 60 // normalized_interval
        available_minutes = [i * normalized_interval for i in range(slots_per_hour)]

        existing_slots = await self.get_existing_slots(
            google_credential_id, day_of_week, hour
        )
        occupied_minutes = {slot.minute for slot in existing_slots}

        for minute in available_minutes:
            if minute not in occupied_minutes:
                logger.debug(
                    f"[FIND_MINUTE] {day_of_week}일 {hour}시: minute={minute} 가용"
                )
                return minute

        logger.warning(
            f"[FIND_MINUTE] {day_of_week}일 {hour}시: 모든 슬롯 점유됨 (occupied: {occupied_minutes})"
        )
        return None
