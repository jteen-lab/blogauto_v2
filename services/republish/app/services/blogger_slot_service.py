"""
Blogger 전역 슬롯 관리 서비스

Features:
- Google 계정별 시간 슬롯 예약/해제
- 슬롯 충돌 검증 및 대안 제시
- 프로파일 스케줄 기반 자동 슬롯 할당
- 동시성 안전 트랜잭션 처리
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..models.google_credential import GoogleCredential
from ..models.google_account_policy import GoogleAccountPolicy
from ..models.blogger_global_slot import BloggerGlobalSlot
from ..models.blog import Blog
from ..schemas.blogger_slot import (
    SlotInfo, SlotConflict, SlotSuggestion, ValidationResult,
    ScheduleInfo, SlotReservation, AddBlogResult
)
from ..core.logger import get_logger

logger = get_logger("blogger_slot", "strategy.log")


class BloggerGlobalSlotManager:
    """구글 블로거 전역 슬롯 관리자"""

    def __init__(self, db: AsyncSession, google_credential_id: int):
        self.db = db
        self.google_credential_id = google_credential_id

    async def get_policy(self) -> GoogleAccountPolicy:
        """계정 정책 조회"""
        query = select(GoogleAccountPolicy).where(
            GoogleAccountPolicy.google_credential_id == self.google_credential_id
        )
        result = await self.db.execute(query)
        policy = result.scalar_one_or_none()

        if not policy:
            logger.warning(f"[GET_POLICY] 정책 없음: credential_id={self.google_credential_id}")
            raise ValueError(f"Google 계정 정책을 찾을 수 없습니다: {self.google_credential_id}")

        return policy

    async def get_slots_per_hour(self) -> int:
        """시간당 슬롯 수"""
        policy = await self.get_policy()
        return policy.slots_per_hour

    async def get_all_reserved_slots(self, day_of_week: int = None) -> List[BloggerGlobalSlot]:
        """예약된 슬롯 조회"""
        query = select(BloggerGlobalSlot).where(
            BloggerGlobalSlot.google_credential_id == self.google_credential_id
        )

        if day_of_week is not None:
            query = query.where(BloggerGlobalSlot.day_of_week == day_of_week)

        query = query.order_by(
            BloggerGlobalSlot.day_of_week,
            BloggerGlobalSlot.hour,
            BloggerGlobalSlot.minute
        )

        result = await self.db.execute(query)
        slots = result.scalars().all()

        logger.debug(f"[GET_RESERVED] credential_id={self.google_credential_id}, day={day_of_week}, count={len(slots)}")
        return slots

    async def get_available_slots(self, day_of_week: int, hour: int) -> List[int]:
        """특정 시간의 가용 슬롯 분(minute) 목록"""
        policy = await self.get_policy()

        # 시간 허용 여부 확인
        if not policy.is_hour_allowed(hour):
            return []

        # 예약된 슬롯 조회
        query = select(BloggerGlobalSlot.minute).where(
            and_(
                BloggerGlobalSlot.google_credential_id == self.google_credential_id,
                BloggerGlobalSlot.day_of_week == day_of_week,
                BloggerGlobalSlot.hour == hour
            )
        )
        result = await self.db.execute(query)
        reserved_minutes = {row[0] for row in result.fetchall()}

        # 가능한 슬롯 분 계산 (정책의 간격에 따라)
        slots_per_hour = policy.slots_per_hour
        interval_minutes = 60 // slots_per_hour

        available_minutes = []
        for i in range(slots_per_hour):
            minute = i * interval_minutes
            if minute not in reserved_minutes:
                available_minutes.append(minute)

        logger.debug(f"[GET_AVAILABLE] day={day_of_week}, hour={hour}, available={available_minutes}")
        return available_minutes

    async def get_slot_status_by_hour(self, day_of_week: int) -> Dict[int, List[SlotInfo]]:
        """요일별 시간당 슬롯 현황"""
        policy = await self.get_policy()
        slots = await self.get_all_reserved_slots(day_of_week)

        # 시간별로 그룹핑
        hour_slots = {}
        for hour in range(24):
            if policy.is_hour_allowed(hour):
                hour_slots[hour] = []

        # 예약된 슬롯 정보 추가
        for slot in slots:
            if slot.hour in hour_slots:
                # 블로그 정보 조회 (지연 로딩)
                blog_name = None
                if slot.blog_id:
                    blog_query = select(Blog.name).where(Blog.id == slot.blog_id)
                    blog_result = await self.db.execute(blog_query)
                    blog_name = blog_result.scalar_one_or_none()

                slot_info = SlotInfo(
                    day_of_week=slot.day_of_week,
                    hour=slot.hour,
                    minute=slot.minute,
                    blog_id=slot.blog_id,
                    blog_name=blog_name,
                    group_id=slot.group_id
                )
                hour_slots[slot.hour].append(slot_info)

        return hour_slots

    async def can_reserve_slot(
        self,
        blog_id: int,
        day_of_week: int,
        hour: int,
        minute: int
    ) -> Tuple[bool, str, dict]:
        """슬롯 예약 가능 여부 확인"""
        policy = await self.get_policy()

        # 시간대 허용 여부
        if not policy.is_hour_allowed(hour):
            return False, f"허용되지 않는 시간대: {hour:02d}:00", {"allowed_hours": policy.allowed_hours_range}

        # 분 단위 검증
        slots_per_hour = policy.slots_per_hour
        valid_minutes = [i * (60 // slots_per_hour) for i in range(slots_per_hour)]
        if minute not in valid_minutes:
            return False, f"허용되지 않는 분: {minute}", {"valid_minutes": valid_minutes}

        # 충돌 검사
        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == self.google_credential_id,
                BloggerGlobalSlot.day_of_week == day_of_week,
                BloggerGlobalSlot.hour == hour,
                BloggerGlobalSlot.minute == minute
            )
        )
        result = await self.db.execute(query)
        existing_slot = result.scalar_one_or_none()

        if existing_slot:
            return False, "슬롯이 이미 예약됨", {
                "conflicting_blog_id": existing_slot.blog_id,
                "conflicting_group_id": existing_slot.group_id
            }

        return True, "예약 가능", {}

    async def validate_blog_schedules(
        self,
        blog_id: int,
        schedules: List[ScheduleInfo]
    ) -> ValidationResult:
        """블로그 스케줄 일괄 검증"""
        logger.info(f"[VALIDATE_SCHEDULES] blog_id={blog_id}, schedule_count={len(schedules)}")

        conflicts = []
        reservable = []

        for schedule in schedules:
            can_reserve, message, details = await self.can_reserve_slot(
                blog_id=blog_id,
                day_of_week=schedule.day_of_week,
                hour=schedule.hour,
                minute=schedule.minute
            )

            if can_reserve:
                slot_info = SlotInfo(
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=schedule.minute,
                    blog_id=blog_id
                )
                reservable.append(slot_info)
            else:
                # 대안 슬롯 찾기
                alternatives = await self.get_available_slots(schedule.day_of_week, schedule.hour)

                conflict = SlotConflict(
                    day_of_week=schedule.day_of_week,
                    hour=schedule.hour,
                    minute=schedule.minute,
                    profile_name=schedule.profile_name,
                    conflicting_blog_name="",
                    conflicting_group_name="",
                    alternatives=alternatives
                )
                conflicts.append(conflict)

        # 제안사항 생성
        suggestions = await self._generate_suggestions(conflicts)

        result = ValidationResult(
            valid=len(conflicts) == 0,
            conflicts=conflicts,
            reservable=reservable,
            suggestions=suggestions
        )

        logger.info(f"[VALIDATE_SCHEDULES] blog_id={blog_id}, valid={result.valid}, conflicts={len(conflicts)}")
        return result

    async def reserve_slot(
        self,
        blog_id: int,
        group_id: int,
        profile_id: int,
        day_of_week: int,
        hour: int,
        minute: int
    ) -> BloggerGlobalSlot:
        """단일 슬롯 예약"""
        # 예약 가능 여부 확인
        can_reserve, message, details = await self.can_reserve_slot(
            blog_id, day_of_week, hour, minute
        )

        if not can_reserve:
            raise ValueError(f"슬롯 예약 불가: {message}")

        # 슬롯 생성
        slot = BloggerGlobalSlot(
            google_credential_id=self.google_credential_id,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            blog_id=blog_id,
            group_id=group_id,
            profile_id=profile_id
        )

        self.db.add(slot)
        await self.db.flush()  # ID 생성

        logger.info(f"[RESERVE_SLOT] slot_id={slot.id}, blog_id={blog_id}, time={day_of_week}-{hour:02d}:{minute:02d}")
        return slot

    async def reserve_multiple_slots(
        self,
        blog_id: int,
        group_id: int,
        reservations: List[SlotReservation]
    ) -> List[BloggerGlobalSlot]:
        """여러 슬롯 일괄 예약"""
        reserved_slots = []

        try:
            for reservation in reservations:
                slot = await self.reserve_slot(
                    blog_id=blog_id,
                    group_id=group_id,
                    profile_id=reservation.profile_id,
                    day_of_week=reservation.day_of_week,
                    hour=reservation.hour,
                    minute=reservation.minute
                )
                reserved_slots.append(slot)

            await self.db.commit()
            logger.info(f"[RESERVE_MULTIPLE] blog_id={blog_id}, reserved_count={len(reserved_slots)}")
            return reserved_slots

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[RESERVE_MULTIPLE] 일괄 예약 실패: {e}")
            raise

    async def release_slots_by_blog(self, blog_id: int, group_id: int = None):
        """블로그의 슬롯 해제"""
        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == self.google_credential_id,
                BloggerGlobalSlot.blog_id == blog_id
            )
        )

        if group_id:
            query = query.where(BloggerGlobalSlot.group_id == group_id)

        result = await self.db.execute(query)
        slots = result.scalars().all()

        for slot in slots:
            await self.db.delete(slot)

        await self.db.commit()
        logger.info(f"[RELEASE_BLOG] blog_id={blog_id}, group_id={group_id}, released_count={len(slots)}")

    async def release_slots_by_group(self, group_id: int):
        """그룹의 모든 슬롯 해제"""
        query = select(BloggerGlobalSlot).where(
            and_(
                BloggerGlobalSlot.google_credential_id == self.google_credential_id,
                BloggerGlobalSlot.group_id == group_id
            )
        )

        result = await self.db.execute(query)
        slots = result.scalars().all()

        for slot in slots:
            await self.db.delete(slot)

        await self.db.commit()
        logger.info(f"[RELEASE_GROUP] group_id={group_id}, released_count={len(slots)}")

    async def suggest_alternative_slots(
        self,
        day_of_week: int,
        preferred_hours: List[int]
    ) -> List[SlotSuggestion]:
        """대체 슬롯 제안"""
        suggestions = []
        policy = await self.get_policy()

        for hour in preferred_hours:
            if policy.is_hour_allowed(hour):
                available_minutes = await self.get_available_slots(day_of_week, hour)

                if available_minutes:
                    recommendation = f"{hour:02d}시에 {len(available_minutes)}개 슬롯 가용"
                    suggestion = SlotSuggestion(
                        hour=hour,
                        available_minutes=available_minutes,
                        recommendation=recommendation
                    )
                    suggestions.append(suggestion)

        return suggestions

    async def _generate_suggestions(self, conflicts: List[SlotConflict]) -> List[SlotSuggestion]:
        """충돌 기반 제안사항 생성"""
        suggestions = []
        policy = await self.get_policy()

        # 충돌이 있는 시간대 근처에서 대안 찾기
        for conflict in conflicts:
            # 같은 시간대 다른 분
            if conflict.alternatives:
                suggestion = SlotSuggestion(
                    hour=conflict.hour,
                    available_minutes=conflict.alternatives,
                    recommendation=f"{conflict.hour:02d}시 다른 분에 가용 슬롯 있음"
                )
                suggestions.append(suggestion)

            # 인근 시간대
            for hour_offset in [-1, 1]:
                nearby_hour = conflict.hour + hour_offset
                if 0 <= nearby_hour <= 23 and policy.is_hour_allowed(nearby_hour):
                    available = await self.get_available_slots(conflict.day_of_week, nearby_hour)
                    if available:
                        suggestion = SlotSuggestion(
                            hour=nearby_hour,
                            available_minutes=available,
                            recommendation=f"인근 시간대 {nearby_hour:02d}시에 슬롯 가용"
                        )
                        suggestions.append(suggestion)
                        break  # 하나만 찾으면 충분

        return suggestions[:5]  # 최대 5개 제안