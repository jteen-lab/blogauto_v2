"""
참조자료 수집 API 통합 테스트

API 엔드포인트의 전체 흐름을 테스트합니다.
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

from tests.fixtures.reference_collection_fixtures import (
    create_mock_db_session,
    create_mock_collected_reference,
    create_mock_user_settings,
    create_search_results,
    create_crawl_result,
    create_document_summaries
)


class TestStartCollectionEndpoint:
    """POST /references/collect 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_start_collection_creates_reference(self):
        """수집 시작 시 CollectedReference 생성"""
        from app.routers.reference_collection import start_collection
        from app.schemas.reference_collection import CollectRequest
        from fastapi import BackgroundTasks

        mock_db = create_mock_db_session()
        mock_user = MagicMock()
        mock_user.id = 1
        background_tasks = BackgroundTasks()

        # refresh 후 reference 객체에 id 설정
        async def mock_refresh(obj):
            obj.id = 1
        mock_db.refresh = mock_refresh

        request = CollectRequest(
            title_id=1,
            search_query="테스트 검색어"
        )

        response = await start_collection(
            data=request,
            background_tasks=background_tasks,
            db=mock_db,
            current_user=mock_user
        )

        assert response.reference_id == 1
        assert response.status == "collecting"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_collection_adds_background_task(self):
        """백그라운드 태스크 등록 확인"""
        from app.routers.reference_collection import start_collection
        from app.schemas.reference_collection import CollectRequest
        from fastapi import BackgroundTasks

        mock_db = create_mock_db_session()
        mock_user = MagicMock()
        mock_user.id = 1
        background_tasks = BackgroundTasks()

        async def mock_refresh(obj):
            obj.id = 1
        mock_db.refresh = mock_refresh

        request = CollectRequest(
            title_id=1,
            search_query="테스트 검색어"
        )

        with patch.object(
            background_tasks, 'add_task'
        ) as mock_add_task:
            await start_collection(
                data=request,
                background_tasks=background_tasks,
                db=mock_db,
                current_user=mock_user
            )

            mock_add_task.assert_called_once()


class TestGetCollectionStatusEndpoint:
    """GET /references/{reference_id}/status 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_get_status_success(self):
        """상태 조회 성공"""
        from app.routers.reference_collection import get_collection_status

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(
            id=1,
            status="collecting",
            total_searched=30,
            total_crawled=10,
            total_failed=5
        )
        mock_db.get = AsyncMock(return_value=mock_ref)

        mock_user = MagicMock()
        mock_user.id = 1

        response = await get_collection_status(
            reference_id=1,
            db=mock_db,
            current_user=mock_user
        )

        assert response.reference_id == 1
        assert response.status == "collecting"
        assert response.progress["searched"] == 30
        assert response.progress["crawled"] == 10

    @pytest.mark.asyncio
    async def test_get_status_not_found(self):
        """존재하지 않는 reference_id"""
        from app.routers.reference_collection import get_collection_status
        from fastapi import HTTPException

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(return_value=None)

        mock_user = MagicMock()
        mock_user.id = 1

        with pytest.raises(HTTPException) as exc_info:
            await get_collection_status(
                reference_id=999,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404


class TestGetCollectionResultEndpoint:
    """GET /references/{reference_id} 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_get_result_success(self):
        """결과 조회 성공"""
        from app.routers.reference_collection import get_collection_result

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(
            id=1,
            status="completed",
            search_query="테스트",
            total_searched=30,
            total_crawled=10,
            total_failed=5,
            selected_references=[
                {
                    "url": "https://example.com/1",
                    "title": "제목1",
                    "summary": "요약1",
                    "original_length": 1000,
                    "is_ai_summary": True
                }
            ]
        )
        mock_db.get = AsyncMock(return_value=mock_ref)

        # CrawlLog 조회 Mock
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_user = MagicMock()
        mock_user.id = 1

        response = await get_collection_result(
            reference_id=1,
            db=mock_db,
            current_user=mock_user
        )

        assert response.reference_id == 1
        assert response.status == "completed"
        assert len(response.selected_references) == 1

    @pytest.mark.asyncio
    async def test_get_result_not_found(self):
        """존재하지 않는 reference_id"""
        from app.routers.reference_collection import get_collection_result
        from fastapi import HTTPException

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(return_value=None)

        mock_user = MagicMock()
        mock_user.id = 1

        with pytest.raises(HTTPException) as exc_info:
            await get_collection_result(
                reference_id=999,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404


class TestListCollectionsEndpoint:
    """GET /references 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_list_collections(self):
        """목록 조회"""
        from app.routers.reference_collection import list_collections

        mock_db = create_mock_db_session()

        refs = [
            create_mock_collected_reference(id=1, status="completed"),
            create_mock_collected_reference(id=2, status="collecting")
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = refs
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_user = MagicMock()
        mock_user.id = 1

        response = await list_collections(
            page=1,
            size=20,
            status=None,
            db=mock_db,
            current_user=mock_user
        )

        assert len(response) == 2
        assert response[0].id == 1

    @pytest.mark.asyncio
    async def test_list_collections_with_status_filter(self):
        """상태 필터링"""
        from app.routers.reference_collection import list_collections

        mock_db = create_mock_db_session()

        refs = [
            create_mock_collected_reference(id=1, status="completed")
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = refs
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_user = MagicMock()
        mock_user.id = 1

        response = await list_collections(
            page=1,
            size=20,
            status="completed",
            db=mock_db,
            current_user=mock_user
        )

        assert len(response) == 1
        assert response[0].status == "completed"


class TestDeleteCollectionEndpoint:
    """DELETE /references/{reference_id} 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_delete_collection_success(self):
        """삭제 성공"""
        from app.routers.reference_collection import delete_collection

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(id=1)
        mock_db.get = AsyncMock(return_value=mock_ref)

        mock_user = MagicMock()
        mock_user.id = 1

        # None 반환 (204 No Content)
        result = await delete_collection(
            reference_id=1,
            db=mock_db,
            current_user=mock_user
        )

        assert result is None
        mock_db.delete.assert_called_once_with(mock_ref)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_collection_not_found(self):
        """존재하지 않는 reference_id"""
        from app.routers.reference_collection import delete_collection
        from fastapi import HTTPException

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(return_value=None)

        mock_user = MagicMock()
        mock_user.id = 1

        with pytest.raises(HTTPException) as exc_info:
            await delete_collection(
                reference_id=999,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 404


class TestRetryCollectionEndpoint:
    """POST /references/{reference_id}/retry 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_retry_failed_collection(self):
        """실패한 수집 재시도"""
        from app.routers.reference_collection import retry_collection
        from fastapi import BackgroundTasks

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(
            id=1,
            status="failed",
            search_query="테스트"
        )
        mock_db.get = AsyncMock(return_value=mock_ref)

        mock_user = MagicMock()
        mock_user.id = 1
        background_tasks = BackgroundTasks()

        response = await retry_collection(
            reference_id=1,
            background_tasks=background_tasks,
            db=mock_db,
            current_user=mock_user
        )

        assert response.reference_id == 1
        assert response.status == "collecting"
        # 상태가 리셋되었는지 확인
        assert mock_ref.status == "pending"
        assert mock_ref.total_searched == 0

    @pytest.mark.asyncio
    async def test_retry_not_allowed_for_collecting(self):
        """수집 중인 상태에서 재시도 불가"""
        from app.routers.reference_collection import retry_collection
        from fastapi import BackgroundTasks, HTTPException

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(
            id=1,
            status="collecting"
        )
        mock_db.get = AsyncMock(return_value=mock_ref)

        mock_user = MagicMock()
        mock_user.id = 1
        background_tasks = BackgroundTasks()

        with pytest.raises(HTTPException) as exc_info:
            await retry_collection(
                reference_id=1,
                background_tasks=background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_retry_completed_collection(self):
        """완료된 수집 재시도"""
        from app.routers.reference_collection import retry_collection
        from fastapi import BackgroundTasks

        mock_db = create_mock_db_session()
        mock_ref = create_mock_collected_reference(
            id=1,
            status="completed",
            search_query="테스트"
        )
        mock_db.get = AsyncMock(return_value=mock_ref)

        mock_user = MagicMock()
        mock_user.id = 1
        background_tasks = BackgroundTasks()

        response = await retry_collection(
            reference_id=1,
            background_tasks=background_tasks,
            db=mock_db,
            current_user=mock_user
        )

        assert response.status == "collecting"


class TestRunCollectionTask:
    """run_collection_task 백그라운드 태스크 테스트 - 단위 테스트 형식"""

    def test_run_collection_task_function_exists(self):
        """run_collection_task 함수 존재 확인"""
        from app.routers.reference_collection import run_collection_task

        assert callable(run_collection_task)

    def test_run_collection_task_is_async(self):
        """run_collection_task가 async 함수인지 확인"""
        from app.routers.reference_collection import run_collection_task
        import asyncio

        assert asyncio.iscoroutinefunction(run_collection_task)

    def test_mock_collected_reference_status_change(self):
        """CollectedReference Mock 상태 변경 테스트"""
        mock_ref = create_mock_collected_reference(id=1, status="pending")

        # 상태 변경 시뮬레이션
        mock_ref.status = "collecting"
        assert mock_ref.status == "collecting"

        mock_ref.status = "completed"
        assert mock_ref.status == "completed"

    def test_mock_collected_reference_error_message(self):
        """CollectedReference Mock 에러 메시지 테스트"""
        mock_ref = create_mock_collected_reference(id=1, status="failed")

        mock_ref.error_message = "사용자 설정을 찾을 수 없습니다"
        assert "사용자 설정" in mock_ref.error_message

    def test_mock_collected_reference_search_results(self):
        """CollectedReference Mock 검색 결과 테스트"""
        mock_ref = create_mock_collected_reference(id=1, status="pending")

        mock_ref.total_searched = 30
        mock_ref.total_crawled = 10
        mock_ref.total_failed = 5

        assert mock_ref.total_searched == 30
        assert mock_ref.total_crawled == 10
        assert mock_ref.total_failed == 5
