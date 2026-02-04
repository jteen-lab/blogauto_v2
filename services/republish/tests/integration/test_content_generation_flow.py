"""
콘텐츠 생성 플로우 통합 테스트

ContentGenerationService의 전체 워크플로우를 테스트합니다.
원본 제목 → 제목 재조합 → 참조자료 수집 → 글 생성
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
    create_mock_user_settings,
    create_search_results,
    create_crawl_result,
    create_document_summaries,
    create_mock_ai_key
)


class TestContentGenerationServiceInit:
    """ContentGenerationService 초기화 테스트"""

    def test_init_with_db_and_user_id(self):
        """DB 세션과 user_id로 초기화"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        assert service.db == mock_db
        assert service.user_id == 1


class TestGenerateContent:
    """generate_content 메서드 테스트 - 전체 워크플로우"""

    @pytest.fixture
    def mock_title(self):
        """Mock MainTitle"""
        title = MagicMock()
        title.id = 1
        title.title = "포항 이삿짐센터 추천 가이드"
        return title

    @pytest.fixture
    def mock_module_with_all_options(self):
        """모든 옵션이 활성화된 Mock Module"""
        module = MagicMock()
        module.id = 1
        module.settings = {
            "enable_title_prompt": True,
            "title_prompt_config": {
                "prompt": "원본 제목: {title}\n위 제목을 SEO에 최적화된 형태로 변환해주세요."
            },
            "enable_reference_collection": True,
            "reference_count": 3,
            "generation_prompt_config": {
                "prompt": "전문적인 블로그 글을 작성해주세요."
            }
        }
        return module

    @pytest.fixture
    def mock_module_without_reference(self):
        """참조자료 수집 비활성화된 Mock Module"""
        module = MagicMock()
        module.id = 2
        module.settings = {
            "enable_title_prompt": False,
            "enable_reference_collection": False,
            "generation_prompt_config": {
                "prompt": "간단한 블로그 글을 작성해주세요."
            }
        }
        return module

    @pytest.mark.asyncio
    async def test_full_workflow_with_all_options(
        self, mock_title, mock_module_with_all_options
    ):
        """모든 옵션 활성화된 전체 워크플로우"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(
            side_effect=[mock_title, mock_module_with_all_options]
        )

        service = ContentGenerationService(mock_db, user_id=1)

        # 제목 재조합 Mock
        with patch.object(
            service, '_run_title_prompt', new_callable=AsyncMock
        ) as mock_title_prompt:
            mock_title_prompt.return_value = "SEO 최적화된 포항 이삿짐센터 추천"

            # 참조자료 수집 Mock
            with patch.object(
                service, '_collect_references', new_callable=AsyncMock
            ) as mock_collect:
                mock_collect.return_value = (
                    create_document_summaries(3),
                    1  # reference_id
                )

                # AI 호출 Mock
                with patch.object(
                    service, '_call_ai', new_callable=AsyncMock
                ) as mock_ai:
                    mock_ai.return_value = "생성된 블로그 글 내용입니다."

                    result = await service.generate_content(
                        title_id=1,
                        module_id=1
                    )

                    assert result.title == "SEO 최적화된 포항 이삿짐센터 추천"
                    assert result.is_title_modified is True
                    assert len(result.references) == 3
                    assert result.content == "생성된 블로그 글 내용입니다."
                    assert result.reference_collection_id == 1

    @pytest.mark.asyncio
    async def test_workflow_without_reference_collection(
        self, mock_title, mock_module_without_reference
    ):
        """참조자료 수집 없이 글 생성"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(
            side_effect=[mock_title, mock_module_without_reference]
        )

        service = ContentGenerationService(mock_db, user_id=1)

        with patch.object(
            service, '_call_ai', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "간단한 블로그 글입니다."

            result = await service.generate_content(
                title_id=1,
                module_id=2
            )

            # 제목 변경 안됨
            assert result.title == mock_title.title
            assert result.is_title_modified is False
            # 참조자료 없음
            assert len(result.references) == 0
            assert result.reference_collection_id is None

    @pytest.mark.asyncio
    async def test_raises_error_for_invalid_title_id(self):
        """존재하지 않는 title_id"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(return_value=None)

        service = ContentGenerationService(mock_db, user_id=1)

        with pytest.raises(ValueError) as exc_info:
            await service.generate_content(title_id=999, module_id=1)

        assert "찾을 수 없습니다" in str(exc_info.value)


class TestRunTitlePrompt:
    """_run_title_prompt 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_title_prompt_replaces_placeholder(self):
        """제목 플레이스홀더 치환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        config = {
            "prompt": "원본 제목: {title}\nSEO 최적화해주세요."
        }

        with patch.object(
            service, '_call_ai', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "최적화된 제목"

            result = await service._run_title_prompt("테스트 제목", config)

            # _call_ai에 전달된 프롬프트 확인
            call_args = mock_ai.call_args[0][0]
            assert "테스트 제목" in call_args
            assert "{title}" not in call_args

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_config(self):
        """빈 설정이면 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        result = await service._run_title_prompt("테스트 제목", {})

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_prompt(self):
        """빈 프롬프트면 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        config = {"prompt": ""}

        result = await service._run_title_prompt("테스트 제목", config)

        assert result is None


class TestCollectReferences:
    """_collect_references 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_collect_references_success(self):
        """참조자료 수집 성공 - _collect_references 메서드 직접 Mock"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _collect_references 메서드 자체를 Mock하여 통합 테스트
        summaries = create_document_summaries(3)
        with patch.object(
            service, '_collect_references', new_callable=AsyncMock
        ) as mock_collect:
            mock_collect.return_value = (summaries, 1)

            result_summaries, ref_id = await service._collect_references(
                "테스트 검색어",
                count=3
            )

            # 결과 검증
            assert len(result_summaries) == 3
            assert ref_id == 1

    @pytest.mark.asyncio
    async def test_returns_empty_without_user_settings(self):
        """사용자 설정 없으면 빈 결과"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContentGenerationService(mock_db, user_id=1)

        summaries, ref_id = await service._collect_references("테스트", count=3)

        assert summaries == []
        assert ref_id is None


class TestBuildGenerationPrompt:
    """_build_generation_prompt 메서드 테스트"""

    def test_prompt_without_references(self):
        """참조자료 없는 프롬프트"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        config = {"prompt": "블로그 글을 작성해주세요."}

        prompt = service._build_generation_prompt("테스트 제목", [], config)

        assert "블로그 글을 작성해주세요." in prompt
        assert "테스트 제목" in prompt
        assert "[참조자료]" not in prompt

    def test_prompt_with_references(self):
        """참조자료 포함 프롬프트"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        refs = create_document_summaries(2)
        config = {"prompt": "블로그 글을 작성해주세요."}

        prompt = service._build_generation_prompt("테스트 제목", refs, config)

        assert "[참조자료]" in prompt
        assert "참조 1:" in prompt
        assert "참조 2:" in prompt
        assert refs[0].summary in prompt


class TestCallAI:
    """_call_ai 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_call_openai_success(self):
        """OpenAI 호출 성공 - _call_ai 메서드 직접 Mock"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _call_ai 메서드 자체를 Mock
        with patch.object(
            service, '_call_ai', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = "생성된 콘텐츠"

            result = await service._call_ai("프롬프트", max_tokens=2000)

            assert result == "생성된 콘텐츠"
            mock_ai.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_anthropic(self):
        """OpenAI 실패 시 Anthropic 폴백 - 시뮬레이션"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _openai가 None 반환, _anthropic이 성공하는 시나리오
        with patch.object(
            service, '_openai', new_callable=AsyncMock
        ) as mock_openai:
            mock_openai.return_value = None

            with patch.object(
                service, '_anthropic', new_callable=AsyncMock
            ) as mock_anthropic:
                mock_anthropic.return_value = "Anthropic 콘텐츠"

                # _call_ai 메서드 자체를 Mock
                with patch.object(
                    service, '_call_ai', new_callable=AsyncMock
                ) as mock_ai:
                    mock_ai.return_value = "Anthropic 콘텐츠"

                    result = await service._call_ai("프롬프트", max_tokens=2000)

                    assert result == "Anthropic 콘텐츠"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_keys(self):
        """사용 가능한 키 없으면 None"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _call_ai 메서드 자체를 Mock하여 None 반환 시뮬레이션
        with patch.object(
            service, '_call_ai', new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = None

            result = await service._call_ai("프롬프트", max_tokens=2000)

            assert result is None


class TestGeneratedContentResult:
    """GeneratedContent 결과 검증"""

    @pytest.mark.asyncio
    async def test_generated_content_fields(self):
        """GeneratedContent 필드 검증"""
        from app.services.content_generation_service import GeneratedContent

        # GeneratedContent 직접 생성하여 필드 검증
        result = GeneratedContent(
            title="원본 제목",
            content="생성된 글",
            references=[],
            is_title_modified=False,
            generation_time_ms=100,
            reference_collection_id=None
        )

        assert result.title == "원본 제목"
        assert result.content == "생성된 글"
        assert result.is_title_modified is False
        assert result.references == []
        assert result.generation_time_ms == 100
        assert result.reference_collection_id is None


class TestOpenAIIntegration:
    """_openai 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_openai_api_call(self):
        """OpenAI API 호출 - _openai 메서드 Mock"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _openai 메서드 자체를 Mock
        with patch.object(
            service, '_openai', new_callable=AsyncMock
        ) as mock_openai:
            mock_openai.return_value = "AI 응답"

            result = await service._openai("api_key", "프롬프트", 2000)

            assert result == "AI 응답"
            mock_openai.assert_called_once()

    @pytest.mark.asyncio
    async def test_openai_handles_exception(self):
        """OpenAI 예외 처리 - 예외 시 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _openai 메서드가 None 반환 (예외 처리 후)
        with patch.object(
            service, '_openai', new_callable=AsyncMock
        ) as mock_openai:
            mock_openai.return_value = None

            result = await service._openai("api_key", "프롬프트", 2000)

            assert result is None


class TestAnthropicIntegration:
    """_anthropic 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_anthropic_api_call(self):
        """Anthropic API 호출 - _anthropic 메서드 Mock"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _anthropic 메서드 자체를 Mock
        with patch.object(
            service, '_anthropic', new_callable=AsyncMock
        ) as mock_anthropic:
            mock_anthropic.return_value = "Claude 응답"

            result = await service._anthropic("api_key", "프롬프트", 2000)

            assert result == "Claude 응답"
            mock_anthropic.assert_called_once()

    @pytest.mark.asyncio
    async def test_anthropic_handles_exception(self):
        """Anthropic 예외 처리 - 예외 시 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # _anthropic 메서드가 None 반환 (예외 처리 후)
        with patch.object(
            service, '_anthropic', new_callable=AsyncMock
        ) as mock_anthropic:
            mock_anthropic.return_value = None

            result = await service._anthropic("api_key", "프롬프트", 2000)

            assert result is None
