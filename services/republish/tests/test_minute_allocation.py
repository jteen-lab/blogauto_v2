"""
분 단위 배치 로직 테스트

Test Cases:
1. 프로파일 간격에 따른 분 단위 계산 (15분, 30분, 60분)
2. 동일 시간대 여러 스케줄의 분 단위 분산
3. 프로파일 ID 해시 기반 일관된 분 배정
4. 시간당 최대 슬롯 수 제한 확인
5. 슬롯 분배 로직의 라운드 로빈 방식 검증
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
from app.schemas.blogger_slot import ScheduleInfo


class TestMinuteAllocation:
    """분 단위 배치 로직 테스트"""

    @pytest.fixture
    async def setup_minute_test_data(self, db_session: AsyncSession):
        """분 단위 테스트 데이터 준비"""
        # 테스트 사용자
        user = User(
            email="minute@test.com",
            hashed_password="hashed",
            full_name="Minute Test User"
        )
        db_session.add(user)
        await db_session.flush()

        # Google 계정
        credential = GoogleCredential(
            user_id=user.id,
            google_email="minute@gmail.com"
        )
        credential.set_tokens("test_token", "test_refresh", 3600)
        db_session.add(credential)
        await db_session.flush()

        # 정책 (최소 15분 간격)
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

        # 블로그 생성
        blog = Blog(
            user_id=user.id,
            google_credential_id=credential.id,
            name="Minute Test Blog",
            url="https://minute.blogspot.com",
            platform=BlogPlatform.BLOGGER
        )
        db_session.add(blog)

        # 그룹 생성
        group = ProfileGroup(
            user_id=user.id,
            name="Minute Test Group"
        )
        db_session.add(group)
        await db_session.flush()

        await db_session.commit()

        return {
            "user": user,
            "credential": credential,
            "policy": policy,
            "blog": blog,
            "group": group
        }

    async def test_15_minute_interval_allocation(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 1: 15분 간격 설정 시 분 단위 배치"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 15분 간격 프로파일 생성 (화요일 10시 활성)
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[1][10] = True  # 화요일 10시

        profile = PublishProfile(
            user_id=data["user"].id,
            name="15min Interval Profile",
            manual_interval_minutes=15,
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        # 프로파일을 그룹에 연결
        link = GroupProfileLink(
            group_id=data["group"].id,
            profile_id=profile.id
        )
        db_session.add(link)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출 및 분 단위 확인
        schedules = await group_service._extract_group_schedules(data["group"])

        assert len(schedules) == 1
        schedule = schedules[0]
        assert schedule.day_of_week == 1  # 화요일
        assert schedule.hour == 10

        # 15분 간격이므로 가능한 분: 0, 15, 30, 45
        assert schedule.minute in [0, 15, 30, 45]

    async def test_30_minute_interval_allocation(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 2: 30분 간격 설정 시 분 단위 배치"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 30분 간격 프로파일 생성 (수요일 14시 활성)
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[2][14] = True  # 수요일 14시

        profile = PublishProfile(
            user_id=data["user"].id,
            name="30min Interval Profile",
            manual_interval_minutes=30,
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        # 프로파일을 그룹에 연결
        link = GroupProfileLink(
            group_id=data["group"].id,
            profile_id=profile.id
        )
        db_session.add(link)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출 및 분 단위 확인
        schedules = await group_service._extract_group_schedules(data["group"])

        assert len(schedules) == 1
        schedule = schedules[0]
        assert schedule.day_of_week == 2  # 수요일
        assert schedule.hour == 14

        # 30분 간격이므로 가능한 분: 0, 30
        assert schedule.minute in [0, 30]

    async def test_consistent_minute_allocation_same_profile(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 3: 같은 프로파일은 항상 같은 분 단위 배정"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 프로파일 생성 (월요일과 화요일 10시 활성)
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[0][10] = True  # 월요일 10시
        matrix_2d[1][10] = True  # 화요일 10시

        profile = PublishProfile(
            user_id=data["user"].id,
            name="Consistent Profile",
            manual_interval_minutes=15,
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        # 프로파일을 그룹에 연결
        link = GroupProfileLink(
            group_id=data["group"].id,
            profile_id=profile.id
        )
        db_session.add(link)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 첫 번째 추출
        schedules1 = await group_service._extract_group_schedules(data["group"])

        # 두 번째 추출 (같은 프로파일)
        schedules2 = await group_service._extract_group_schedules(data["group"])

        # 결과 비교
        assert len(schedules1) == len(schedules2) == 2

        # 같은 프로파일, 같은 시간의 분 단위는 항상 동일해야 함
        for s1 in schedules1:
            for s2 in schedules2:
                if (s1.profile_id == s2.profile_id and
                    s1.day_of_week == s2.day_of_week and
                    s1.hour == s2.hour):
                    assert s1.minute == s2.minute

    async def test_slot_distribution_for_multiple_schedules(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 4: 동일 시간대 여러 스케줄의 분 단위 분산"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 여러 프로파일 생성 (모두 화요일 10시 활성)
        profiles = []
        for i in range(3):
            matrix_2d = [[False] * 24 for _ in range(7)]
            matrix_2d[1][10] = True  # 화요일 10시

            profile = PublishProfile(
                user_id=data["user"].id,
                name=f"Profile {i}",
                manual_interval_minutes=15,
                schedule_matrix=json.dumps(matrix_2d)
            )
            db_session.add(profile)
            profiles.append(profile)

        await db_session.flush()

        # 모든 프로파일을 그룹에 연결
        for profile in profiles:
            link = GroupProfileLink(
                group_id=data["group"].id,
                profile_id=profile.id
            )
            db_session.add(link)

        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출
        schedules = await group_service._extract_group_schedules(data["group"])

        # 슬롯 분배 로직 적용
        adjusted_schedules = await group_service._add_slot_distribution_logic(
            schedules, data["credential"].id
        )

        assert len(adjusted_schedules) == 3

        # 모든 스케줄이 같은 시간(화요일 10시)이지만 다른 분을 가져야 함
        minutes = [schedule.minute for schedule in adjusted_schedules]

        # 중복된 분이 없어야 함 (최대 4개 슬롯: 0, 15, 30, 45분)
        assert len(set(minutes)) == 3  # 3개 스케줄 모두 다른 분

        # 모든 분은 15분 단위여야 함
        for minute in minutes:
            assert minute in [0, 15, 30, 45]

    async def test_hourly_slot_limit(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 5: 시간당 최대 슬롯 수 제한"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 5개 프로파일 생성 (모두 화요일 10시 활성) - 15분 간격으로는 4개만 가능
        profiles = []
        for i in range(5):
            matrix_2d = [[False] * 24 for _ in range(7)]
            matrix_2d[1][10] = True  # 화요일 10시

            profile = PublishProfile(
                user_id=data["user"].id,
                name=f"Profile {i}",
                manual_interval_minutes=15,
                schedule_matrix=json.dumps(matrix_2d)
            )
            db_session.add(profile)
            profiles.append(profile)

        await db_session.flush()

        # 모든 프로파일을 그룹에 연결
        for profile in profiles:
            link = GroupProfileLink(
                group_id=data["group"].id,
                profile_id=profile.id
            )
            db_session.add(link)

        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출
        schedules = await group_service._extract_group_schedules(data["group"])

        # 슬롯 분배 로직 적용
        adjusted_schedules = await group_service._add_slot_distribution_logic(
            schedules, data["credential"].id
        )

        assert len(adjusted_schedules) == 5

        # 분 단위별 개수 확인
        minute_counts = {}
        for schedule in adjusted_schedules:
            minute = schedule.minute
            minute_counts[minute] = minute_counts.get(minute, 0) + 1

        # 라운드 로빈이므로 일부 분은 중복될 수 있음 (5개 스케줄 → 4개 슬롯)
        # 0분:2개, 15분:1개, 30분:1개, 45분:1개 형태로 분배됨
        assert max(minute_counts.values()) <= 2  # 한 분에 최대 2개까지

    async def test_60_minute_interval_single_slot(self, db_session: AsyncSession, setup_minute_test_data):
        """테스트 6: 60분 간격 설정 시 시간당 단일 슬롯 (0분 고정)"""
        data = await setup_minute_test_data
        group_service = GroupService(db_session)

        # 60분 간격 프로파일 생성
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[3][15] = True  # 목요일 15시

        profile = PublishProfile(
            user_id=data["user"].id,
            name="60min Interval Profile",
            manual_interval_minutes=60,
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile)
        await db_session.flush()

        # 프로파일을 그룹에 연결
        link = GroupProfileLink(
            group_id=data["group"].id,
            profile_id=profile.id
        )
        db_session.add(link)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출 및 분 단위 확인
        schedules = await group_service._extract_group_schedules(data["group"])

        assert len(schedules) == 1
        schedule = schedules[0]
        assert schedule.day_of_week == 3  # 목요일
        assert schedule.hour == 15

        # 60분 간격이므로 무조건 0분
        assert schedule.minute == 0