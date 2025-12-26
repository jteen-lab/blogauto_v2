"""
슬롯 검증 수정 확인 테스트

이 테스트는 schedule_matrix 파싱 오류 수정 후
실제로 슬롯 검증이 작동하는지 확인합니다.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import json
from typing import List

from ..models.user import User
from ..models.blog import Blog, BlogPlatform
from ..models.google_credential import GoogleCredential
from ..models.google_account_policy import GoogleAccountPolicy
from ..models.profile_group import ProfileGroup
from ..models.publish_profile import PublishProfile
from ..models.group_profile_link import GroupProfileLink
from ..services.group_service import GroupService
from ..services.blogger_slot_service import BloggerGlobalSlotManager


class TestSlotValidationFix:
    """슬롯 검증 수정 확인"""

    @pytest.fixture
    async def setup_validation_test(self, db_session: AsyncSession):
        """슬롯 검증 테스트 데이터 준비"""
        # 사용자
        user = User(
            email="validation@test.com",
            hashed_password="hashed",
            full_name="Validation Test User"
        )
        db_session.add(user)
        await db_session.flush()

        # Google 계정
        credential = GoogleCredential(
            user_id=user.id,
            google_email="validation@gmail.com"
        )
        credential.set_tokens("test_token", "test_refresh", 3600)
        db_session.add(credential)
        await db_session.flush()

        # 정책 (시간당 2슬롯, 9-18시)
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

        # Blogger 블로그
        blog = Blog(
            user_id=user.id,
            google_credential_id=credential.id,
            name="Validation Test Blog",
            url="https://validation.blogspot.com",
            platform=BlogPlatform.BLOGGER
        )
        db_session.add(blog)

        # 2D 배열 형식 프로파일 (화요일 10시, 14시)
        matrix_2d = []
        for day in range(7):
            day_schedule = [False] * 24
            if day == 1:  # 화요일
                day_schedule[10] = True
                day_schedule[14] = True
            matrix_2d.append(day_schedule)

        profile = PublishProfile(
            user_id=user.id,
            name="Validation Test Profile",
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        await db_session.commit()

        return {
            "user": user,
            "credential": credential,
            "policy": policy,
            "blog": blog,
            "profile": profile
        }

    async def test_schedule_extraction_works(self, db_session: AsyncSession, setup_validation_test):
        """스케줄 추출이 실제로 작동하는지 확인"""
        data = await setup_validation_test
        group_service = GroupService(db_session)

        # 그룹 생성
        group = ProfileGroup(
            user_id=data["user"].id,
            name="Validation Test Group"
        )
        db_session.add(group)
        await db_session.flush()

        # 프로파일 연결
        link = GroupProfileLink(
            group_id=group.id,
            profile_id=data["profile"].id
        )
        db_session.add(link)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(group, ['profile_links'])

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(group)

        # 검증: 이전에는 빈 리스트였지만 이제는 2개 스케줄이 추출되어야 함
        assert len(schedules) == 2, f"Expected 2 schedules, got {len(schedules)}"

        # 화요일 10시, 14시 스케줄 확인
        schedule_times = [(s.day_of_week, s.hour) for s in schedules]
        assert (1, 10) in schedule_times, "Tuesday 10:00 schedule missing"
        assert (1, 14) in schedule_times, "Tuesday 14:00 schedule missing"

        # 프로파일 정보 확인
        for schedule in schedules:
            assert schedule.profile_id == data["profile"].id
            assert schedule.profile_name == "Validation Test Profile"

    async def test_slot_validation_actually_runs(self, db_session: AsyncSession, setup_validation_test):
        """슬롯 검증이 실제로 실행되는지 확인"""
        data = await setup_validation_test
        group_service = GroupService(db_session)

        # 그룹 생성 (블로그 포함)
        group_data = {
            "name": "Validation Test Group",
            "profile_ids": [data["profile"].id],
            "blog_ids": [data["blog"].id]
        }

        group = await group_service.create_group(data["user"], group_data)

        # 그룹 생성 성공 확인
        assert group is not None
        assert len(group.profile_links) == 1
        assert len(group.blog_links) == 1  # 블로그가 성공적으로 추가됨

        # 슬롯이 실제로 예약되었는지 확인
        slot_manager = BloggerGlobalSlotManager(db_session, data["credential"].id)
        slots = await slot_manager.get_all_reserved_slots()

        # 검증: 이전에는 0개였지만 이제는 2개 슬롯이 예약되어야 함
        assert len(slots) == 2, f"Expected 2 slots reserved, got {len(slots)}"

        # 예약된 슬롯 시간 확인
        slot_times = [(s.day_of_week, s.hour, s.minute) for s in slots]
        assert (1, 10, 0) in slot_times, "Tuesday 10:00 slot not reserved"
        assert (1, 14, 0) in slot_times, "Tuesday 14:00 slot not reserved"

        # 블로그 ID 확인
        for slot in slots:
            assert slot.blog_id == data["blog"].id
            assert slot.google_credential_id == data["credential"].id

    async def test_slot_conflict_detection_works(self, db_session: AsyncSession, setup_validation_test):
        """슬롯 충돌 감지가 작동하는지 확인"""
        data = await setup_validation_test
        group_service = GroupService(db_session)

        # 첫 번째 그룹 생성 (슬롯 예약)
        group1_data = {
            "name": "First Validation Group",
            "profile_ids": [data["profile"].id],
            "blog_ids": [data["blog"].id]
        }
        group1 = await group_service.create_group(data["user"], group1_data)
        assert len(group1.blog_links) == 1  # 성공적으로 추가

        # 두 번째 블로그 생성 (같은 Google 계정)
        blog2 = Blog(
            user_id=data["user"].id,
            google_credential_id=data["credential"].id,
            name="Second Validation Blog",
            url="https://validation2.blogspot.com",
            platform=BlogPlatform.BLOGGER
        )
        db_session.add(blog2)
        await db_session.commit()

        # 두 번째 그룹 생성 시도 (동일한 프로파일, 다른 블로그 - 충돌 발생)
        group2_data = {
            "name": "Second Validation Group",
            "profile_ids": [data["profile"].id],
            "blog_ids": [blog2.id]
        }
        group2 = await group_service.create_group(data["user"], group2_data)

        # 그룹은 생성되지만 블로그는 충돌로 인해 추가되지 않음
        assert group2 is not None
        assert len(group2.profile_links) == 1
        assert len(group2.blog_links) == 0, "Blog should not be added due to slot conflict"

        # 슬롯은 여전히 첫 번째 블로그만 가지고 있어야 함
        slot_manager = BloggerGlobalSlotManager(db_session, data["credential"].id)
        slots = await slot_manager.get_all_reserved_slots()

        assert len(slots) == 2  # 첫 번째 블로그의 슬롯만
        for slot in slots:
            assert slot.blog_id == data["blog"].id, "Slots should belong to first blog only"

    async def test_empty_schedule_handling(self, db_session: AsyncSession, setup_validation_test):
        """빈 스케줄 처리 확인"""
        data = await setup_validation_test
        group_service = GroupService(db_session)

        # 빈 스케줄 프로파일 생성
        empty_matrix = [[False] * 24 for _ in range(7)]
        empty_profile = PublishProfile(
            user_id=data["user"].id,
            name="Empty Schedule Profile",
            schedule_matrix=json.dumps(empty_matrix)
        )
        db_session.add(empty_profile)
        await db_session.commit()

        # 빈 스케줄로 그룹 생성
        group_data = {
            "name": "Empty Schedule Group",
            "profile_ids": [empty_profile.id],
            "blog_ids": [data["blog"].id]
        }
        group = await group_service.create_group(data["user"], group_data)

        # 스케줄이 없으므로 블로그가 바로 추가되어야 함
        assert len(group.blog_links) == 1

        # 슬롯은 예약되지 않아야 함
        slot_manager = BloggerGlobalSlotManager(db_session, data["credential"].id)
        slots = await slot_manager.get_all_reserved_slots()
        assert len(slots) == 0, "No slots should be reserved for empty schedule"