"""
Schedule Matrix 파싱 로직 테스트

Test Cases:
1. 2D 배열 형식 파싱 테스트
2. 딕셔너리 형식 파싱 테스트 (호환성)
3. 잘못된 형식 처리 테스트
4. 빈 데이터 처리 테스트
5. 부분 데이터 처리 테스트
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import json
from typing import List

from ..models.user import User
from ..models.profile_group import ProfileGroup
from ..models.publish_profile import PublishProfile
from ..models.group_profile_link import GroupProfileLink
from ..services.group_service import GroupService
from ..schemas.blogger_slot import ScheduleInfo


class TestScheduleMatrixParsing:
    """Schedule Matrix 파싱 테스트"""

    @pytest.fixture
    async def setup_test_user_and_group(self, db_session: AsyncSession):
        """테스트용 사용자와 그룹 생성"""
        user = User(
            email="test@example.com",
            hashed_password="hashed",
            full_name="Test User"
        )
        db_session.add(user)
        await db_session.flush()

        group = ProfileGroup(
            user_id=user.id,
            name="Test Group"
        )
        db_session.add(group)
        await db_session.flush()

        await db_session.commit()

        return {"user": user, "group": group}

    async def test_2d_array_format_parsing(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 1: 2D 배열 형식 파싱"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 2D 배열 형식 스케줄 매트릭스 (7x24)
        # 월요일(0): 9시, 10시 활성
        # 화요일(1): 14시 활성
        # 나머지: 비활성
        matrix_2d = []
        for day in range(7):
            day_schedule = [False] * 24
            if day == 0:  # 월요일
                day_schedule[9] = True
                day_schedule[10] = True
            elif day == 1:  # 화요일
                day_schedule[14] = True
            matrix_2d.append(day_schedule)

        # 프로파일 생성
        profile = PublishProfile(
            user_id=data["user"].id,
            name="2D Array Profile",
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

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(data["group"])

        # 검증: 3개 스케줄이 추출되어야 함
        assert len(schedules) == 3

        # 월요일 스케줄 확인
        monday_schedules = [s for s in schedules if s.day_of_week == 0]
        assert len(monday_schedules) == 2
        monday_hours = sorted([s.hour for s in monday_schedules])
        assert monday_hours == [9, 10]

        # 화요일 스케줄 확인
        tuesday_schedules = [s for s in schedules if s.day_of_week == 1]
        assert len(tuesday_schedules) == 1
        assert tuesday_schedules[0].hour == 14

        # 프로파일 정보 확인
        for schedule in schedules:
            assert schedule.profile_id == profile.id
            assert schedule.profile_name == "2D Array Profile"
            assert schedule.minute == 0  # 기본값

    async def test_dictionary_format_parsing(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 2: 딕셔너리 형식 파싱 (기존 호환성)"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 딕셔너리 형식 스케줄 매트릭스
        matrix_dict = {
            "1": {"10": True, "14": True},  # 화요일 10시, 14시
            "2": {"10": True}               # 수요일 10시
        }

        # 프로파일 생성
        profile = PublishProfile(
            user_id=data["user"].id,
            name="Dictionary Profile",
            schedule_matrix=json.dumps(matrix_dict)
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

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(data["group"])

        # 검증: 3개 스케줄이 추출되어야 함
        assert len(schedules) == 3

        # 화요일 스케줄 확인
        tuesday_schedules = [s for s in schedules if s.day_of_week == 1]
        assert len(tuesday_schedules) == 2
        tuesday_hours = sorted([s.hour for s in tuesday_schedules])
        assert tuesday_hours == [10, 14]

        # 수요일 스케줄 확인
        wednesday_schedules = [s for s in schedules if s.day_of_week == 2]
        assert len(wednesday_schedules) == 1
        assert wednesday_schedules[0].hour == 10

    async def test_invalid_format_handling(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 3: 잘못된 형식 처리"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 잘못된 형식들
        invalid_formats = [
            "invalid_string",
            123,
            {"invalid": "structure"},
            [["invalid", "structure"], "wrong"]
        ]

        for i, invalid_format in enumerate(invalid_formats):
            # 프로파일 생성
            profile = PublishProfile(
                user_id=data["user"].id,
                name=f"Invalid Profile {i}",
                schedule_matrix=json.dumps(invalid_format) if not isinstance(invalid_format, str) else invalid_format
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

            # 스케줄 추출 테스트 (오류 없이 빈 리스트 반환되어야 함)
            schedules = await group_service._extract_group_schedules(data["group"])
            assert isinstance(schedules, list)  # 오류 없이 처리됨

            # 정리
            await db_session.delete(link)
            await db_session.delete(profile)
            await db_session.commit()

    async def test_empty_schedule_handling(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 4: 빈 스케줄 처리"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 빈 2D 배열
        empty_2d = [[False] * 24 for _ in range(7)]

        # 프로파일 생성
        profile = PublishProfile(
            user_id=data["user"].id,
            name="Empty Schedule Profile",
            schedule_matrix=json.dumps(empty_2d)
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

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(data["group"])

        # 검증: 빈 리스트여야 함
        assert len(schedules) == 0

    async def test_partial_schedule_handling(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 5: 부분 스케줄 처리 (배열 크기가 다른 경우)"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 부분 스케줄 (요일 수가 적거나 시간 수가 적은 경우)
        partial_matrix = [
            [True, False, False, True],  # 0일차 - 4시간만
            [False, True]                # 1일차 - 2시간만
            # 나머지 요일 없음
        ]

        # 프로파일 생성
        profile = PublishProfile(
            user_id=data["user"].id,
            name="Partial Schedule Profile",
            schedule_matrix=json.dumps(partial_matrix)
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

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(data["group"])

        # 검증: 3개 스케줄이 추출되어야 함 (0시, 3시, 1시)
        assert len(schedules) == 3

        # 월요일(0) 스케줄 확인
        monday_schedules = [s for s in schedules if s.day_of_week == 0]
        assert len(monday_schedules) == 2
        monday_hours = sorted([s.hour for s in monday_schedules])
        assert monday_hours == [0, 3]

        # 화요일(1) 스케줄 확인
        tuesday_schedules = [s for s in schedules if s.day_of_week == 1]
        assert len(tuesday_schedules) == 1
        assert tuesday_schedules[0].hour == 1

    async def test_mixed_format_profiles(self, db_session: AsyncSession, setup_test_user_and_group):
        """테스트 6: 서로 다른 형식의 프로파일 혼합"""
        data = await setup_test_user_and_group
        group_service = GroupService(db_session)

        # 2D 배열 형식 프로파일
        matrix_2d = [[False] * 24 for _ in range(7)]
        matrix_2d[0][9] = True  # 월요일 9시

        profile_2d = PublishProfile(
            user_id=data["user"].id,
            name="2D Profile",
            schedule_matrix=json.dumps(matrix_2d)
        )
        db_session.add(profile_2d)

        # 딕셔너리 형식 프로파일
        matrix_dict = {"1": {"14": True}}  # 화요일 14시

        profile_dict = PublishProfile(
            user_id=data["user"].id,
            name="Dict Profile",
            schedule_matrix=json.dumps(matrix_dict)
        )
        db_session.add(profile_dict)
        await db_session.flush()

        # 두 프로파일을 그룹에 연결
        link_2d = GroupProfileLink(group_id=data["group"].id, profile_id=profile_2d.id)
        link_dict = GroupProfileLink(group_id=data["group"].id, profile_id=profile_dict.id)
        db_session.add(link_2d)
        db_session.add(link_dict)
        await db_session.commit()

        # 그룹 새로고침
        await db_session.refresh(data["group"], ['profile_links'])

        # 스케줄 추출 테스트
        schedules = await group_service._extract_group_schedules(data["group"])

        # 검증: 2개 스케줄이 추출되어야 함
        assert len(schedules) == 2

        # 각 프로파일의 스케줄 확인
        profile_ids = {s.profile_id for s in schedules}
        assert profile_2d.id in profile_ids
        assert profile_dict.id in profile_ids

        # 시간 확인
        schedule_times = {(s.day_of_week, s.hour) for s in schedules}
        assert (0, 9) in schedule_times   # 월요일 9시 (2D 배열)
        assert (1, 14) in schedule_times  # 화요일 14시 (딕셔너리)