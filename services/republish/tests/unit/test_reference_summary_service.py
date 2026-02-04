"""
참조자료 요약 서비스 단위 테스트

ReferenceSummaryService의 문서 요약 기능을 테스트합니다.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# app 경로 추가
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

from tests.fixtures.reference_collection_fixtures import (
    create_mock_db_session,
    create_crawled_documents,
    create_crawled_document,
    create_mock_ai_key,
    create_mock_openai_response,
    create_mock_anthropic_response
)


class TestReferenceSummaryServiceInit:
    """ReferenceSummaryService 초기화 테스트"""

    def test_init_with_db_and_user_id(self):
        """DB 세션과 user_id로 초기화"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        assert service.db == mock_db
        assert service.SELECT_COUNT == 3
        assert service.MAX_SUMMARY_LENGTH == 500


class TestSelectRandomDocuments:
    """select_random_documents 메서드 테스트"""

    def test_select_all_when_less_than_count(self):
        """문서 수가 count 이하면 전체 반환"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        documents = create_crawled_documents(2)
        selected = service.select_random_documents(documents, count=3)

        assert len(selected) == 2
        assert selected == documents

    def test_select_random_when_more_than_count(self):
        """문서 수가 count 초과면 랜덤 선택"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        documents = create_crawled_documents(10)
        selected = service.select_random_documents(documents, count=3)

        assert len(selected) == 3
        # 선택된 문서가 원본에 포함되어 있는지 확인
        for doc in selected:
            assert doc in documents

    def test_select_with_empty_list(self):
        """빈 리스트"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        selected = service.select_random_documents([], count=3)

        assert selected == []


class TestSummarizeDocuments:
    """summarize_documents 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_summarize_documents_with_ai(self):
        """AI를 사용한 문서 요약"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        documents = create_crawled_documents(3)

        with patch.object(
            service, '_summarize_single', new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = MagicMock(
                url="https://example.com",
                title="제목",
                summary="요약된 내용",
                is_ai_summary=True
            )

            summaries = await service.summarize_documents(documents)

            assert len(summaries) == 3
            assert mock_summarize.call_count == 3

    @pytest.mark.asyncio
    async def test_summarize_selects_random_documents(self):
        """SELECT_COUNT만큼 랜덤 선택 후 요약"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        documents = create_crawled_documents(10)

        with patch.object(
            service, '_summarize_single', new_callable=AsyncMock
        ) as mock_summarize:
            mock_summarize.return_value = MagicMock(is_ai_summary=True)

            summaries = await service.summarize_documents(documents)

            # SELECT_COUNT(3)개만 요약
            assert len(summaries) == 3


class TestSummarizeSingle:
    """_summarize_single 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_ai_summary_success(self):
        """AI 요약 성공"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        doc = create_crawled_document(content="원본 내용입니다. " * 100)

        with patch.object(
            service, '_call_ai_summary', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "AI가 요약한 내용입니다."

            summary = await service._summarize_single(doc)

            assert summary.is_ai_summary is True
            assert summary.summary == "AI가 요약한 내용입니다."
            assert summary.url == doc.url

    @pytest.mark.asyncio
    async def test_fallback_when_ai_fails(self):
        """AI 실패 시 원본 앞부분 사용"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        long_content = "원본 내용입니다. " * 100
        doc = create_crawled_document(content=long_content)

        with patch.object(
            service, '_call_ai_summary', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = None

            summary = await service._summarize_single(doc)

            assert summary.is_ai_summary is False
            # 원본 앞부분이 포함되어 있는지 확인
            assert "원본 내용" in summary.summary
            # MAX_SUMMARY_LENGTH 이하인지 확인
            assert len(summary.summary) <= service.MAX_SUMMARY_LENGTH + 3  # "..." 포함

    @pytest.mark.asyncio
    async def test_truncates_long_content_for_ai(self):
        """AI 입력용 콘텐츠 길이 제한"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        # MAX_INPUT_LENGTH보다 긴 콘텐츠
        very_long_content = "A" * 10000
        doc = create_crawled_document(content=very_long_content)

        with patch.object(
            service, '_call_ai_summary', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "요약"

            await service._summarize_single(doc)

            # _call_ai_summary에 전달된 콘텐츠 길이 확인
            call_args = mock_ai.call_args[0][0]
            assert len(call_args) <= service.MAX_INPUT_LENGTH


class TestCallAiSummary:
    """_call_ai_summary 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_openai_first_then_anthropic(self):
        """OpenAI 먼저 시도, 실패 시 Anthropic"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        mock_key = create_mock_ai_key()

        with patch.object(
            service.key_manager, 'get_available_key', new_callable=AsyncMock
        ) as mock_get_key:
            mock_get_key.return_value = mock_key

            with patch.object(
                service, '_call_openai', new_callable=AsyncMock
            ) as mock_openai:
                mock_openai.return_value = "OpenAI 요약"

                with patch.object(
                    service.key_manager, 'mark_key_used', new_callable=AsyncMock
                ):
                    result = await service._call_ai_summary("테스트 콘텐츠")

                    assert result == "OpenAI 요약"
                    mock_openai.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_anthropic(self):
        """OpenAI 실패 시 Anthropic 시도"""
        from app.services.reference_summary_service import ReferenceSummaryService
        from app.schemas.ai_api_key import AIProvider

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        mock_key = create_mock_ai_key()

        async def get_key_side_effect(provider):
            if provider == AIProvider.OPENAI:
                return None  # OpenAI 키 없음
            return mock_key

        with patch.object(
            service.key_manager, 'get_available_key', new_callable=AsyncMock
        ) as mock_get_key:
            mock_get_key.side_effect = get_key_side_effect

            with patch.object(
                service, '_call_anthropic', new_callable=AsyncMock
            ) as mock_anthropic:
                mock_anthropic.return_value = "Anthropic 요약"

                with patch.object(
                    service.key_manager, 'mark_key_used', new_callable=AsyncMock
                ):
                    result = await service._call_ai_summary("테스트 콘텐츠")

                    assert result == "Anthropic 요약"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_keys(self):
        """사용 가능한 키가 없으면 None 반환"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        with patch.object(
            service.key_manager, 'get_available_key', new_callable=AsyncMock
        ) as mock_get_key:
            mock_get_key.return_value = None

            result = await service._call_ai_summary("테스트 콘텐츠")

            assert result is None


class TestCallOpenai:
    """_call_openai 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """성공적인 OpenAI API 호출"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        mock_response = create_mock_openai_response("요약된 내용입니다.")

        with patch('app.services.reference_summary_service.openai') as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            result = await service._call_openai("test_api_key", "테스트 콘텐츠")

            assert result == "요약된 내용입니다."

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        """예외 발생 시 None 반환"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        with patch('app.services.reference_summary_service.openai') as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_openai.AsyncOpenAI.return_value = mock_client

            result = await service._call_openai("test_api_key", "테스트 콘텐츠")

            assert result is None


class TestCallAnthropic:
    """_call_anthropic 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """성공적인 Anthropic API 호출"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        mock_response = create_mock_anthropic_response("Anthropic 요약")

        with patch('app.services.reference_summary_service.anthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            result = await service._call_anthropic("test_api_key", "테스트 콘텐츠")

            assert result == "Anthropic 요약"

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        """예외 발생 시 None 반환"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        with patch('app.services.reference_summary_service.anthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            result = await service._call_anthropic("test_api_key", "테스트 콘텐츠")

            assert result is None


class TestSummaryOutputFormat:
    """요약 결과 출력 형식 테스트"""

    @pytest.mark.asyncio
    async def test_document_summary_fields(self):
        """DocumentSummary 필드 검증"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        doc = create_crawled_document(
            url="https://test.com/post/1",
            title="테스트 제목",
            content="본문 내용 " * 50,
            content_length=500
        )

        with patch.object(
            service, '_call_ai_summary', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "AI 요약 결과"

            summary = await service._summarize_single(doc)

            assert summary.url == "https://test.com/post/1"
            assert summary.title == "테스트 제목"
            assert summary.original_length == 500
            assert summary.summary == "AI 요약 결과"
            assert summary.is_ai_summary is True

    @pytest.mark.asyncio
    async def test_summary_length_limit(self):
        """요약 길이 제한"""
        from app.services.reference_summary_service import ReferenceSummaryService

        mock_db = create_mock_db_session()
        service = ReferenceSummaryService(mock_db, user_id=1)

        doc = create_crawled_document(content="내용 " * 200)

        # 매우 긴 AI 응답
        long_summary = "요약 " * 200

        with patch.object(
            service, '_call_ai_summary', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = long_summary

            summary = await service._summarize_single(doc)

            # MAX_SUMMARY_LENGTH 이하로 제한
            assert len(summary.summary) <= service.MAX_SUMMARY_LENGTH
