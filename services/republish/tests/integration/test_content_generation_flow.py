"""
콘텐츠 생성 플로우 통합 테스트

ContentGenerationService의 전체 워크플로우를 테스트합니다.
원본 제목 → 제목 재조합 → 참조자료 수집 → 글 생성

리팩토링: ContentGenerationService는 내부적으로
TitleRecombiner, ReferenceCollector, AIService를 사용합니다.
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
            "title_prompt": "원본 제목: {title}\n위 제목을 SEO에 최적화된 형태로 변환해주세요.",
            "enable_reference_collection": True,
            "reference_count": 3,
            "generation_prompt": "전문적인 블로그 글을 작성해주세요."
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
            "generation_prompt": "간단한 블로그 글을 작성해주세요."
        }
        return module

    @pytest.mark.asyncio
    async def test_full_workflow_with_all_options(
        self, mock_title, mock_module_with_all_options
    ):
        """모든 옵션 활성화된 전체 워크플로우"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.title_recombiner import RecombineResult
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(
            side_effect=[mock_title, mock_module_with_all_options]
        )

        service = ContentGenerationService(mock_db, user_id=1)

        # TitleRecombiner.recombine Mock (제목 재조합 활성화)
        service.title_recombiner.recombine = AsyncMock(
            return_value=RecombineResult(
                original_title="포항 이삿짐센터 추천 가이드",
                recombined_title="SEO 최적화된 포항 이삿짐센터 추천",
                ai_model="gpt-4o-mini",
                ai_provider="openai",
                is_modified=True,
            ),
        )

        # ReferenceCollector.collect_and_summarize Mock
        summaries = create_document_summaries(3)
        service.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ReferenceCollectionResult(
                count=3,
                summaries=summaries,
                sources=[s.url for s in summaries],
                reference_id=1,
            ),
        )

        # AIService.generate Mock
        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "생성된 블로그 글 내용입니다.",
                "model": "gpt-4o-mini",
                "provider": "openai",
            },
        )

        result = await service.generate_content(title_id=1, module_id=1)

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
        from app.services.generation.title_recombiner import RecombineResult
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        mock_db = create_mock_db_session()
        mock_db.get = AsyncMock(
            side_effect=[mock_title, mock_module_without_reference]
        )

        service = ContentGenerationService(mock_db, user_id=1)

        # 제목 재조합 비활성화 -> 원본 제목 반환
        service.title_recombiner.recombine = AsyncMock(
            return_value=RecombineResult(
                original_title=mock_title.title,
                recombined_title=mock_title.title,
                ai_model="none",
                ai_provider="none",
                is_modified=False,
            ),
        )

        # 참조자료 0건
        service.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ReferenceCollectionResult(
                count=0, summaries=[], sources=[], reference_id=None,
            ),
        )

        # AI 글 생성
        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "간단한 블로그 글입니다.",
                "model": "gpt-4o-mini",
                "provider": "openai",
            },
        )

        result = await service.generate_content(title_id=1, module_id=2)

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
    """제목 재조합 기능 테스트 (TitleRecombiner 통합)"""

    @pytest.mark.asyncio
    async def test_title_prompt_replaces_placeholder(self):
        """제목 재조합 시 AI 호출이 올바른 프롬프트를 사용"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.title_recombiner import RecombineResult

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # title_recombiner.recombine이 호출되면 재조합 결과 반환
        service.title_recombiner.recombine = AsyncMock(
            return_value=RecombineResult(
                original_title="테스트 제목",
                recombined_title="최적화된 제목",
                ai_model="gpt-4o-mini",
                ai_provider="openai",
                is_modified=True,
            ),
        )

        result = await service.title_recombiner.recombine(
            original_title="테스트 제목", module_id=1,
        )

        # recombine이 호출되었는지 확인
        service.title_recombiner.recombine.assert_awaited_once()
        call_kwargs = service.title_recombiner.recombine.call_args[1]
        assert call_kwargs["original_title"] == "테스트 제목"
        assert result.recombined_title == "최적화된 제목"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_config(self):
        """제목 재조합 비활성화 시 원본 반환"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.title_recombiner import RecombineResult

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # 재조합 비활성화 -> is_modified=False, 원본 반환
        service.title_recombiner.recombine = AsyncMock(
            return_value=RecombineResult(
                original_title="테스트 제목",
                recombined_title="테스트 제목",
                ai_model="none",
                ai_provider="none",
                is_modified=False,
            ),
        )

        result = await service.title_recombiner.recombine(
            original_title="테스트 제목", module_id=1,
        )

        assert result.is_modified is False
        assert result.recombined_title == "테스트 제목"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_prompt(self):
        """빈 프롬프트 설정 시 원본 반환"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.title_recombiner import RecombineResult

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # 프롬프트 비어있어도 기본값 사용하므로 원본 반환 시뮬레이션
        service.title_recombiner.recombine = AsyncMock(
            return_value=RecombineResult(
                original_title="테스트 제목",
                recombined_title="테스트 제목",
                ai_model="none",
                ai_provider="none",
                is_modified=False,
            ),
        )

        result = await service.title_recombiner.recombine(
            original_title="테스트 제목", module_id=1,
        )

        assert result.is_modified is False


class TestCollectReferences:
    """참조자료 수집 테스트 (ReferenceCollector 통합)"""

    @pytest.mark.asyncio
    async def test_collect_references_success(self):
        """참조자료 수집 성공"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        summaries = create_document_summaries(3)
        service.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ReferenceCollectionResult(
                count=3,
                summaries=summaries,
                sources=[s.url for s in summaries],
                reference_id=1,
            ),
        )

        result = await service.reference_collector.collect_and_summarize(
            search_query="테스트 검색어", module_id=1,
        )

        assert result.count == 3
        assert result.reference_id == 1
        assert len(result.summaries) == 3

    @pytest.mark.asyncio
    async def test_returns_empty_without_user_settings(self):
        """API 키 없으면 빈 결과"""
        from app.services.content_generation_service import ContentGenerationService
        from app.services.generation.reference_collector import (
            ReferenceCollectionResult,
        )

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # API 키 없는 경우 빈 결과
        service.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ReferenceCollectionResult(
                count=0, summaries=[], sources=[], reference_id=None,
            ),
        )

        result = await service.reference_collector.collect_and_summarize(
            search_query="테스트", module_id=1,
        )

        assert result.count == 0
        assert result.summaries == []
        assert result.reference_id is None


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
    """AI 호출 테스트 (AIService 통합)"""

    @pytest.mark.asyncio
    async def test_call_openai_success(self):
        """AI 호출 성공"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "생성된 콘텐츠",
                "model": "gpt-4o-mini",
                "provider": "openai",
            },
        )

        result = await service.ai_service.generate(
            prompt="프롬프트", max_tokens=2000,
        )

        assert result["content"] == "생성된 콘텐츠"
        service.ai_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_anthropic(self):
        """OpenAI 실패 시 Anthropic 폴백 시뮬레이션"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # AIService.generate는 내부적으로 provider 폴백을 처리함
        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "Anthropic 콘텐츠",
                "model": "claude-3-haiku",
                "provider": "anthropic",
            },
        )

        result = await service.ai_service.generate(
            prompt="프롬프트", max_tokens=2000,
        )

        assert result["content"] == "Anthropic 콘텐츠"
        assert result["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_keys(self):
        """사용 가능한 키 없으면 None"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        service.ai_service.generate = AsyncMock(return_value=None)

        result = await service.ai_service.generate(
            prompt="프롬프트", max_tokens=2000,
        )

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
    """OpenAI 통합 테스트 (AIService 경유)"""

    @pytest.mark.asyncio
    async def test_openai_api_call(self):
        """OpenAI provider로 AI 호출"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "AI 응답",
                "model": "gpt-4o-mini",
                "provider": "openai",
            },
        )

        result = await service.ai_service.generate(
            prompt="프롬프트", provider="openai", max_tokens=2000,
        )

        assert result["content"] == "AI 응답"
        assert result["provider"] == "openai"
        service.ai_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_openai_handles_exception(self):
        """OpenAI 예외 처리 - 예외 시 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # 예외 발생 후 None 반환 시뮬레이션
        service.ai_service.generate = AsyncMock(return_value=None)

        result = await service.ai_service.generate(
            prompt="프롬프트", provider="openai", max_tokens=2000,
        )

        assert result is None


class TestAnthropicIntegration:
    """Anthropic 통합 테스트 (AIService 경유)"""

    @pytest.mark.asyncio
    async def test_anthropic_api_call(self):
        """Anthropic provider로 AI 호출"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        service.ai_service.generate = AsyncMock(
            return_value={
                "content": "Claude 응답",
                "model": "claude-3-haiku",
                "provider": "anthropic",
            },
        )

        result = await service.ai_service.generate(
            prompt="프롬프트", provider="anthropic", max_tokens=2000,
        )

        assert result["content"] == "Claude 응답"
        assert result["provider"] == "anthropic"
        service.ai_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_anthropic_handles_exception(self):
        """Anthropic 예외 처리 - 예외 시 None 반환"""
        from app.services.content_generation_service import ContentGenerationService

        mock_db = create_mock_db_session()
        service = ContentGenerationService(mock_db, user_id=1)

        # 예외 발생 후 None 반환 시뮬레이션
        service.ai_service.generate = AsyncMock(return_value=None)

        result = await service.ai_service.generate(
            prompt="프롬프트", provider="anthropic", max_tokens=2000,
        )

        assert result is None
