"""
자동 슬롯 할당 테스트

Test Cases:
1. 첫 번째 블로그: minute=0 할당
2. 두 번째 블로그: minute=0 점유됨 → minute=30 자동 할당
3. 세 번째 블로그: minute=0,30 점유됨 → minute=15 자동 할당
4. 네 번째 블로그: minute=0,15,30 점유됨 → minute=45 자동 할당
5. 다섯 번째 블로그: 모든 슬롯 점유됨 → 충돌 오류
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import json
from typing import List

from app.models.user import User
from app.models.blog import Blog, BlogPlatform
from app.models.google_credential import GoogleCredential
from app.models.google_account_policy import GoogleAccountPolicy
from app.models.profile_group import ProfileGroup
from app.models.publish_profile import PublishProfile
from app.models.group_profile_link import GroupProfileLink
from app.services.group_service import GroupService
from app.services.blogger_slot_service import BloggerGlobalSlotManager


class TestAutoSlotAllocation:
    """자동 슬롯 할당 테스트"""

    @pytest.fixture
    async def setup_auto_allocation_data(self, db_session: AsyncSession):
        """자동 할당 테스트 데이터 준비"""
        # 테스트 사용자
        user = User(
            email="auto@test.com",
            hashed_password="hashed",
            full_name="Auto Allocation Test User"
        )
        db_session.add(user)
        await db_session.flush()

        # Google 계정
        credential = GoogleCredential(
            user_id=user.id,
            google_email="auto@gmail.com"
        )
        credential.set_tokens("test_token", "test_refresh", 3600)
        db_session.add(credential)
        await db_session.flush()

        # 정책 (15분 간격 → 시간당 4슬롯)
        policy = GoogleAccountPolicy(
            google_credential_id=credential.id,
            min_interval_minutes=15,
            max_daily_per_blog=10,
            max_daily_total=50,
            allowed_hours_start=9,
            allowed_hours_end=18,
            safety_mode=True
        )
        db_session.add(policy)

        # 프로파일 생성 (화요일 10시 활성)
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[1][10] = True  # 화요일 10시

        profile = PublishProfile(
            user_id=user.id,
            name="Auto Test Profile",
            manual_interval_minutes=15,
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        # 그룹 생성
        group = ProfileGroup(
            user_id=user.id,
            name="Auto Test Group"
        )
        db_session.add(group)
        await db_session.flush()

        # 프로파일을 그룹에 연결
        link = GroupProfileLink(
            group_id=group.id,
            profile_id=profile.id
        )
        db_session.add(link)

        await db_session.commit()

        return {
            "user": user,
            "credential": credential,
            "policy": policy,
            "profile": profile,
            "group": group
        }

    async def test_sequential_slot_allocation(self, db_session: AsyncSession, setup_auto_allocation_data):
        """테스트: 순차적 자동 슬롯 할당"""
        data = await setup_auto_allocation_data
        group_service = GroupService(db_session)

        # 4개 블로그 생성 (동일 Google 계정)
        blogs = []
        for i in range(4):
            blog = Blog(
                user_id=data["user"].id,
                google_credential_id=data["credential"].id,
                name=f"Auto Blog {i+1}",
                url=f"https://auto{i+1}.blogspot.com",
                platform=BlogPlatform.BLOGGER
            )
            db_session.add(blog)
            blogs.append(blog)

        await db_session.flush()
        await db_session.commit()

        expected_minutes = [0, 15, 30, 45]  # 15분 간격으로 순차 할당 예상
        allocated_minutes = []

        # 순차적으로 블로그 추가
        for i, blog in enumerate(blogs):
            result = await group_service.add_blog_with_slot_validation(
                data["user"], data["group"].id, blog.id
            )

            assert result.success, f"블로그 {i+1} 추가 실패: {result.message}"
            assert len(result.reserved_slots) == 1, f"블로그 {i+1}: 예상 슬롯 수 1개"

            allocated_minute = result.reserved_slots[0].minute
            allocated_minutes.append(allocated_minute)

            print(f"블로그 {i+1}: minute={allocated_minute} 할당")

        # 분 단위가 중복되지 않았는지 확인
        assert len(set(allocated_minutes)) == len(allocated_minutes), f"중복된 분 할당: {allocated_minutes}"

        # 모든 분이 15분 단위인지 확인
        for minute in allocated_minutes:
            assert minute in [0, 15, 30, 45], f"잘못된 분 할당: {minute}"

    async def test_slot_conflict_when_all_occupied(self, db_session: AsyncSession, setup_auto_allocation_data):
        """테스트: 모든 슬롯 점유 시 충돌 감지"""
        data = await setup_auto_allocation_data
        group_service = GroupService(db_session)

        # 5개 블로그 생성 (15분 간격으로는 4개만 가능)
        blogs = []
        for i in range(5):
            blog = Blog(
                user_id=data["user"].id,
                google_credential_id=data["credential"].id,
                name=f"Conflict Blog {i+1}",
                url=f"https://conflict{i+1}.blogspot.com",
                platform=BlogPlatform.BLOGGER
            )
            db_session.add(blog)
            blogs.append(blog)

        await db_session.flush()
        await db_session.commit()

        # 첫 4개 블로그는 성공
        for i in range(4):
            result = await group_service.add_blog_with_slot_validation(
                data["user"], data["group"].id, blogs[i].id
            )
            assert result.success, f"블로그 {i+1} 추가 실패: {result.message}"

        # 5번째 블로그는 충돌로 실패해야 함
        result = await group_service.add_blog_with_slot_validation(
            data["user"], data["group"].id, blogs[4].id
        )

        assert not result.success, "5번째 블로그 추가가 성공해서는 안됨"
        assert "모든 슬롯 점유됨" in result.message, f"충돌 메시지 확인: {result.message}"

    async def test_find_available_minute_logic(self, db_session: AsyncSession, setup_auto_allocation_data):
        """테스트: _find_available_minute 로직 직접 테스트"""
        data = await setup_auto_allocation_data
        group_service = GroupService(db_session)
        slot_manager = BloggerGlobalSlotManager(db_session, data["credential"].id)

        # 첫 번째 슬롯 수동 예약 (화요일 10:00)
        from app.schemas.blogger_slot import SlotReservation

        reservation = SlotReservation(
            profile_id=data["profile"].id,
            day_of_week=1,
            hour=10,
            minute=0
        )

        await slot_manager.reserve_slot(
            blog_id=999,  # 더미 블로그 ID
            group_id=data["group"].id,
            reservation=reservation
        )

        # 가용 minute 찾기 테스트
        available_minute = await group_service._find_available_minute(
            google_credential_id=data["credential"].id,
            day_of_week=1,
            hour=10,
            min_interval_minutes=15
        )

        # minute=0이 점유되었으므로 15가 반환되어야 함
        assert available_minute == 15, f"예상: 15, 실제: {available_minute}"

        # 두 번째 슬롯도 예약 (화요일 10:15)
        reservation2 = SlotReservation(
            profile_id=data["profile"].id,
            day_of_week=1,
            hour=10,
            minute=15
        )

        await slot_manager.reserve_slot(
            blog_id=998,
            group_id=data["group"].id,
            reservation=reservation2
        )

        # 이제 30이 반환되어야 함
        available_minute = await group_service._find_available_minute(
            google_credential_id=data["credential"].id,
            day_of_week=1,
            hour=10,
            min_interval_minutes=15
        )

        assert available_minute == 30, f"예상: 30, 실제: {available_minute}"

    async def test_30_minute_interval_allocation(self, db_session: AsyncSession, setup_auto_allocation_data):
        """테스트: 30분 간격 설정 시 자동 할당"""
        data = await setup_auto_allocation_data

        # 정책을 30분 간격으로 변경
        data["policy"].min_interval_minutes = 30
        db_session.add(data["policy"])
        await db_session.commit()

        group_service = GroupService(db_session)

        # 2개 블로그 생성 (30분 간격으로는 2개만 가능)
        blogs = []
        for i in range(2):
            blog = Blog(
                user_id=data["user"].id,
                google_credential_id=data["credential"].id,
                name=f"30min Blog {i+1}",
                url=f"https://30min{i+1}.blogspot.com",
                platform=BlogPlatform.BLOGGER
            )
            db_session.add(blog)
            blogs.append(blog)

        await db_session.flush()
        await db_session.commit()

        allocated_minutes = []

        # 순차적으로 블로그 추가
        for i, blog in enumerate(blogs):
            result = await group_service.add_blog_with_slot_validation(
                data["user"], data["group"].id, blog.id
            )

            assert result.success, f"30분 간격 블로그 {i+1} 추가 실패: {result.message}"

            allocated_minute = result.reserved_slots[0].minute
            allocated_minutes.append(allocated_minute)

        # 30분 간격으로만 할당되어야 함 (0, 30)
        assert set(allocated_minutes) == {0, 30}, f"30분 간격 할당 실패: {allocated_minutes}"

        # 3번째 블로그는 충돌해야 함
        blog3 = Blog(
            user_id=data["user"].id,
            google_credential_id=data["credential"].id,
            name="30min Blog 3",
            url="https://30min3.blogspot.com",
            platform=BlogPlatform.BLOGGER
        )
        db_session.add(blog3)
        await db_session.flush()
        await db_session.commit()

        result = await group_service.add_blog_with_slot_validation(
            data["user"], data["group"].id, blog3.id
        )

        assert not result.success, "30분 간격에서 3번째 블로그 추가가 성공해서는 안됨"