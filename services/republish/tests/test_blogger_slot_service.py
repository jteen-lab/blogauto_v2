"""
Blogger 슬롯 관리 서비스 테스트

Test Cases:
1. 빈 슬롯에 예약 성공
2. 동일 슬롯 중복 예약 실패
3. 다른 그룹에서 동일 슬롯 예약 시도 - 충돌 감지
4. 슬롯 해제 후 재예약 성공
5. 대체 슬롯 추천 정확성
6. 정책 변경 시 슬롯 재계산
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import List

# 테스트용 모의 데이터 생성을 위한 임포트
from ..models.google_credential import GoogleCredential
from ..models.google_account_policy import GoogleAccountPolicy
from ..models.blogger_global_slot import BloggerGlobalSlot
from ..models.blog import Blog, BlogPlatform
from ..models.user import User
from ..services.blogger_slot_service import BloggerGlobalSlotManager
from ..schemas.blogger_slot import ScheduleInfo


class TestBloggerSlotService:
    """Blogger 슬롯 서비스 테스트"""

    @pytest.fixture
    async def setup_test_data(self, db_session: AsyncSession):
        """테스트 데이터 준비"""
        # 테스트 사용자
        user = User(
            email="test@example.com",
            hashed_password="hashed",
            full_name="Test User"
        )
        db_session.add(user)
        await db_session.flush()

        # 테스트 Google 계정
        credential = GoogleCredential(
            user_id=user.id,
            google_email="test@gmail.com"
        )
        credential.set_tokens("test_access_token", "test_refresh_token", 3600)
        db_session.add(credential)
        await db_session.flush()

        # 테스트 정책 (시간당 2슬롯, 9-18시)
        policy = GoogleAccountPolicy(
            google_credential_id=credential.id,
            min_interval_minutes=30,
            max_daily_per_blog=10,
            max_daily_total=50,
            allowed_hours_start=9,
            allowed_hours_end=18,
            safety_mode=True
        )
        db_session.add(policy)

        # 테스트 블로그
        blog = Blog(
            user_id=user.id,
            google_credential_id=credential.id,
            name="Test Blog",
            url="https://test.blogspot.com",
            platform=BlogPlatform.BLOGGER
        )
        db_session.add(blog)
        await db_session.flush()

        await db_session.commit()

        return {
            "user": user,
            "credential": credential,
            "policy": policy,
            "blog": blog
        }

    async def test_successful_slot_reservation(self, db_session: AsyncSession, setup_test_data):
        """테스트 1: 빈 슬롯에 예약 성공"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 슬롯 예약 가능 여부 확인
        can_reserve, message, details = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=1,  # 화요일
            hour=10,        # 10시
            minute=0        # 0분
        )

        assert can_reserve is True
        assert "예약 가능" in message

        # 실제 예약
        slot = await slot_manager.reserve_slot(
            blog_id=blog_id,
            group_id=1,
            profile_id=1,
            day_of_week=1,
            hour=10,
            minute=0
        )

        assert slot is not None
        assert slot.blog_id == blog_id
        assert slot.day_of_week == 1
        assert slot.hour == 10
        assert slot.minute == 0

    async def test_duplicate_slot_reservation_failure(self, db_session: AsyncSession, setup_test_data):
        """테스트 2: 동일 슬롯 중복 예약 실패"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 첫 번째 예약
        await slot_manager.reserve_slot(
            blog_id=blog_id,
            group_id=1,
            profile_id=1,
            day_of_week=1,
            hour=10,
            minute=0
        )

        # 동일 슬롯에 두 번째 예약 시도
        can_reserve, message, details = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=1,
            hour=10,
            minute=0
        )

        assert can_reserve is False
        assert "이미 예약됨" in message
        assert "conflicting_blog_id" in details

    async def test_slot_conflict_detection(self, db_session: AsyncSession, setup_test_data):
        """테스트 3: 다른 그룹에서 동일 슬롯 예약 시도 - 충돌 감지"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 그룹 1에서 슬롯 예약
        await slot_manager.reserve_slot(
            blog_id=blog_id,
            group_id=1,
            profile_id=1,
            day_of_week=2,
            hour=14,
            minute=30
        )

        # 스케줄 검증 (충돌 포함)
        schedules = [
            ScheduleInfo(
                profile_id=2,
                profile_name="Test Profile 2",
                day_of_week=2,
                hour=14,
                minute=30  # 충돌하는 시간
            ),
            ScheduleInfo(
                profile_id=2,
                profile_name="Test Profile 2",
                day_of_week=2,
                hour=15,
                minute=0   # 가능한 시간
            )
        ]

        validation_result = await slot_manager.validate_blog_schedules(blog_id, schedules)

        assert validation_result.valid is False
        assert len(validation_result.conflicts) == 1
        assert len(validation_result.reservable) == 1
        assert validation_result.conflicts[0].hour == 14
        assert validation_result.conflicts[0].minute == 30

    async def test_slot_release_and_reuse(self, db_session: AsyncSession, setup_test_data):
        """테스트 4: 슬롯 해제 후 재예약 성공"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 슬롯 예약
        await slot_manager.reserve_slot(
            blog_id=blog_id,
            group_id=1,
            profile_id=1,
            day_of_week=3,
            hour=11,
            minute=0
        )

        # 예약 확인
        can_reserve, _, _ = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=3,
            hour=11,
            minute=0
        )
        assert can_reserve is False

        # 슬롯 해제
        await slot_manager.release_slots_by_blog(blog_id, 1)

        # 해제 후 재예약 가능 확인
        can_reserve, message, _ = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=3,
            hour=11,
            minute=0
        )
        assert can_reserve is True
        assert "예약 가능" in message

    async def test_alternative_slot_suggestions(self, db_session: AsyncSession, setup_test_data):
        """테스트 5: 대체 슬롯 추천 정확성"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 10시 0분 슬롯 예약 (10시의 첫 번째 슬롯)
        await slot_manager.reserve_slot(
            blog_id=blog_id,
            group_id=1,
            profile_id=1,
            day_of_week=1,
            hour=10,
            minute=0
        )

        # 10시 대체 슬롯 조회
        available_minutes = await slot_manager.get_available_slots(1, 10)

        # 정책상 시간당 2슬롯(30분 간격)이므로 30분 슬롯이 가용해야 함
        assert 30 in available_minutes
        assert 0 not in available_minutes  # 이미 예약됨

        # 대체 슬롯 추천
        suggestions = await slot_manager.suggest_alternative_slots(1, [10, 11])

        assert len(suggestions) > 0
        # 10시에 30분 슬롯이 추천되어야 함
        suggestion_10 = next((s for s in suggestions if s.hour == 10), None)
        assert suggestion_10 is not None
        assert 30 in suggestion_10.available_minutes

    async def test_policy_enforcement(self, db_session: AsyncSession, setup_test_data):
        """테스트 6: 정책 준수 확인"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 허용 시간 외 예약 시도 (18시 이후)
        can_reserve, message, details = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=1,
            hour=19,  # 19시 (정책: 9-18시)
            minute=0
        )

        assert can_reserve is False
        assert "허용되지 않는 시간대" in message
        assert "allowed_hours" in details

        # 잘못된 분 단위 예약 시도
        can_reserve, message, details = await slot_manager.can_reserve_slot(
            blog_id=blog_id,
            day_of_week=1,
            hour=10,
            minute=15  # 정책상 0, 30분만 허용
        )

        assert can_reserve is False
        assert "허용되지 않는 분" in message
        assert "valid_minutes" in details

    async def test_get_slots_per_hour(self, db_session: AsyncSession, setup_test_data):
        """테스트: 시간당 슬롯 수 계산"""
        data = await setup_test_data
        credential_id = data["credential"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)
        slots_per_hour = await slot_manager.get_slots_per_hour()

        # 정책: 30분 간격 = 시간당 2슬롯
        assert slots_per_hour == 2

    async def test_slot_status_by_hour(self, db_session: AsyncSession, setup_test_data):
        """테스트: 시간대별 슬롯 현황 조회"""
        data = await setup_test_data
        credential_id = data["credential"].id
        blog_id = data["blog"].id

        slot_manager = BloggerGlobalSlotManager(db_session, credential_id)

        # 몇 개 슬롯 예약
        await slot_manager.reserve_slot(blog_id, 1, 1, 1, 10, 0)
        await slot_manager.reserve_slot(blog_id, 1, 1, 1, 11, 30)

        # 화요일 현황 조회
        hour_slots = await slot_manager.get_slot_status_by_hour(1)

        # 10시에 1개 슬롯 있어야 함
        assert 10 in hour_slots
        assert len(hour_slots[10]) == 1
        assert hour_slots[10][0].minute == 0

        # 11시에 1개 슬롯 있어야 함
        assert 11 in hour_slots
        assert len(hour_slots[11]) == 1
        assert hour_slots[11][0].minute == 30

        # 빈 시간대는 빈 리스트
        assert 12 in hour_slots
        assert len(hour_slots[12]) == 0