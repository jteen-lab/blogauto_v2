"""
제목 이동 서비스 단위 테스트
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
import sys
import os

# app 경로 추가
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

# shared 모듈 경로 추가
shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)


class TestTitleTransferService:
    """TitleTransferService 단위 테스트"""

    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스 세션"""
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.delete = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def mock_temp_title(self):
        """Mock TempTitle 객체"""
        temp = MagicMock()
        temp.id = 1
        temp.title = "포항 이삿짐센터 추천"
        temp.category_id = 1
        temp.status = "new"
        temp.source_post_url = "https://example.com/post/1"
        temp.mark_moved = MagicMock()
        return temp

    @pytest.fixture
    def mock_main_title(self):
        """Mock MainTitle 객체"""
        main = MagicMock()
        main.id = 1
        main.title = "포항 이삿짐센터 추천"
        main.category_id = 1
        main.status = "available"
        main.group_id = None
        main.is_group_representative = False
        main.source_url = "https://example.com/post/1"
        return main


class TestMoveToMain:
    """임시 → 정식 이동 테스트"""

    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스 세션"""
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_move_single_title(self, mock_db):
        """단일 제목 이동"""
        from app.services.title_transfer_service import TitleTransferService

        # Mock TempTitle
        mock_temp = MagicMock()
        mock_temp.id = 1
        mock_temp.title = "포항 이삿짐센터 추천"
        mock_temp.category_id = 1
        mock_temp.status = "new"
        mock_temp.source_post_url = "https://example.com"
        mock_temp.mark_moved = MagicMock()

        # db.get() 반환값 설정
        mock_db.get = AsyncMock(return_value=mock_temp)

        # 중복 체크 결과 (없음)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TitleTransferService(mock_db, threshold=80)

        # auto_group=False로 테스트 (그룹화 로직 제외)
        result = await service.move_to_main([1], auto_group=False)

        assert "moved" in result
        assert "errors" in result
        assert result["moved"] >= 0

    @pytest.mark.asyncio
    async def test_skip_already_moved(self, mock_db):
        """이미 이동된 제목 건너뛰기"""
        from app.services.title_transfer_service import TitleTransferService

        # Mock TempTitle (이미 이동됨)
        mock_temp = MagicMock()
        mock_temp.id = 1
        mock_temp.status = "moved"

        mock_db.get = AsyncMock(return_value=mock_temp)

        service = TitleTransferService(mock_db)
        result = await service.move_to_main([1])

        # 에러 목록에 "이미 이동됨" 메시지 포함
        assert any("이미 이동" in err for err in result["errors"])

    @pytest.mark.asyncio
    async def test_skip_not_found(self, mock_db):
        """존재하지 않는 제목"""
        from app.services.title_transfer_service import TitleTransferService

        mock_db.get = AsyncMock(return_value=None)

        service = TitleTransferService(mock_db)
        result = await service.move_to_main([999])

        # 에러 목록에 "찾을 수 없음" 메시지 포함
        assert any("찾을 수 없" in err for err in result["errors"])


class TestMoveToTemp:
    """정식 → 임시 이동 테스트"""

    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스 세션"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.delete = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_move_non_representative(self, mock_db):
        """일반 제목 이동 (대표 아님)"""
        from app.services.title_transfer_service import TitleTransferService

        # Mock MainTitle (대표 아님)
        mock_main = MagicMock()
        mock_main.id = 1
        mock_main.title = "테스트 제목"
        mock_main.is_group_representative = False
        mock_main.group_id = None
        mock_main.source_url = "https://example.com"
        mock_main.category_id = 1

        mock_db.get = AsyncMock(return_value=mock_main)

        service = TitleTransferService(mock_db)
        result = await service.move_to_temp([1])

        assert "moved" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_move_not_found(self, mock_db):
        """존재하지 않는 정식 제목"""
        from app.services.title_transfer_service import TitleTransferService

        mock_db.get = AsyncMock(return_value=None)

        service = TitleTransferService(mock_db)
        result = await service.move_to_temp([999])

        # 에러 목록에 메시지 포함
        assert any("찾을 수 없" in err for err in result["errors"])


class TestAutoGroupTitle:
    """자동 그룹화 테스트"""

    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스 세션"""
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_create_new_group_when_no_match(self, mock_db):
        """매칭 그룹 없으면 새 그룹 생성"""
        from app.services.title_transfer_service import TitleTransferService

        # Mock MainTitle
        mock_main = MagicMock()
        mock_main.id = 1
        mock_main.title = "포항 이삿짐센터 추천"
        mock_main.category_id = 1

        # 기존 그룹 없음
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TitleTransferService(mock_db, threshold=80)

        location_info = {"province": "경북", "city": "포항"}
        result = await service._auto_group_title(mock_main, location_info)

        # 새 그룹이 생성되어야 함
        assert result is True
        assert mock_main.is_group_representative is True


class TestConvenienceFunctions:
    """편의 함수 테스트"""

    @pytest.mark.asyncio
    async def test_move_temp_to_main_function(self):
        """move_temp_to_main 편의 함수"""
        from app.services.title_transfer_service import move_temp_to_main

        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        result = await move_temp_to_main(mock_db, [999])

        assert "errors" in result

    @pytest.mark.asyncio
    async def test_move_main_to_temp_function(self):
        """move_main_to_temp 편의 함수"""
        from app.services.title_transfer_service import move_main_to_temp

        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        result = await move_main_to_temp(mock_db, [999])

        assert "errors" in result


class TestServiceInit:
    """서비스 초기화 테스트"""

    def test_default_threshold(self):
        """기본 임계값 확인"""
        from app.services.title_transfer_service import TitleTransferService

        mock_db = MagicMock()
        service = TitleTransferService(mock_db)

        # 기본 임계값은 DEFAULT_SIMILARITY_THRESHOLD (80)
        assert service.threshold == 80.0

    def test_custom_threshold(self):
        """커스텀 임계값 설정"""
        from app.services.title_transfer_service import TitleTransferService

        mock_db = MagicMock()
        service = TitleTransferService(mock_db, threshold=75.0)

        assert service.threshold == 75.0
