"""
Phase B 설정값 정규화 통합 테스트

ContentGenerator와 AIService의 설정값 우선순위 및 전달 로직을 검증합니다.

검증 대상:
1. generator.py - AI provider/temperature/max_tokens/system_prompt 우선순위
2. generator.py - 프롬프트 우선순위 (user_prompt_template > generation_prompt > 기본값)
3. ai_service.py - system_prompt 파라미터 전달
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.generation.generator import (
    ContentGenerator, DEFAULT_CONTENT_PROMPT,
)
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_blog,
    create_mock_main_title,
    create_mock_module,
    create_mock_recombine_result,
    create_mock_reference_result,
    create_db_get_side_effect,
    create_auto_id_add,
)


SAMPLE_MARKDOWN = "## 서론\n테스트 내용입니다.\n## 본론\n본문 내용"
SAMPLE_HTML = "<h2>서론</h2><p>테스트 내용입니다.</p>"
DEFAULT_AI_RESPONSE = {
    "content": SAMPLE_MARKDOWN,
    "model": "gpt-4o-mini",
    "provider": "openai",
}


def _make_blog_module(ai_config: dict, module_settings: dict):
    """테스트용 Blog + Module 쌍 생성"""
    blog = create_mock_blog(blog_id=1, ai_config=ai_config)
    module = create_mock_module(module_id=1, settings=module_settings)
    return blog, module


def _build_generator(
    mock_db: MagicMock,
    blog: MagicMock,
    module: MagicMock,
    title: MagicMock,
) -> ContentGenerator:
    """
    설정값 테스트용 ContentGenerator 생성

    ai_service.generate를 AsyncMock으로 교체하여
    호출 인자를 검증할 수 있도록 합니다.
    """
    mock_db.get = AsyncMock(side_effect=create_db_get_side_effect(
        MainTitle={title.id: title},
        Blog={blog.id: blog},
        Module={module.id: module},
    ))
    mock_db.add = MagicMock(side_effect=create_auto_id_add(start_id=100))

    gen = ContentGenerator(mock_db, user_id=1)

    gen.title_recombiner.recombine = AsyncMock(
        return_value=create_mock_recombine_result(
            original=title.title, recombined="SEO 최적화된 테스트 제목",
        )
    )
    gen.reference_collector.collect_and_summarize = AsyncMock(
        return_value=create_mock_reference_result(count=0)
    )
    gen.ai_service.generate = AsyncMock(return_value=DEFAULT_AI_RESPONSE)
    gen.internal_linker.insert_links = AsyncMock(return_value=SAMPLE_MARKDOWN)
    gen.substitution_processor.process = AsyncMock(return_value=SAMPLE_HTML)
    return gen


async def _run_and_get_ai_kwargs(mock_db, blog, module, title):
    """파이프라인 실행 후 ai_service.generate()에 전달된 kwargs 반환"""
    gen = _build_generator(mock_db, blog, module, title)
    await gen.generate(
        blog_id=blog.id,
        prompt_module_id=module.id,
        source_title_id=title.id,
    )
    _, kwargs = gen.ai_service.generate.call_args
    return gen, kwargs


# ============================================================
# TestContentGenerationSettings: 설정 정규화 핵심 테스트
# ============================================================

class TestContentGenerationSettings:
    """ContentGenerator._generate_content_with_meta() 설정 정규화 테스트"""

    @pytest.mark.asyncio
    async def test_module_provider_overrides_blog(
        self, mock_db, sample_title
    ):
        """모듈 provider="google"이 블로그 provider="openai"보다 우선"""
        blog, module = _make_blog_module(
            ai_config={
                "writing_ai": {"provider": "openai", "model": "gpt-4o-mini"},
                "title_ai": {"provider": "openai", "model": "gpt-4o-mini"},
            },
            module_settings={
                "content_generation": {"enabled": True, "provider": "google"},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["provider"] == "google"

    @pytest.mark.asyncio
    async def test_blog_provider_fallback(self, mock_db, sample_title):
        """모듈에 provider 없으면 Blog.writing_ai.provider 사용"""
        blog, module = _make_blog_module(
            ai_config={
                "writing_ai": {"provider": "anthropic"},
                "title_ai": {"provider": "openai"},
            },
            module_settings={
                "content_generation": {},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_module_temperature_applied(self, mock_db, sample_title):
        """모듈 temperature=0.3이 기본값 0.7 대신 적용"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {"provider": "openai", "temperature": 0.3},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_module_max_tokens_applied(self, mock_db, sample_title):
        """모듈 max_tokens=8000이 기본값 4000 대신 적용"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {"provider": "openai", "max_tokens": 8000},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["max_tokens"] == 8000

    @pytest.mark.asyncio
    async def test_system_prompt_passed(self, mock_db, sample_title):
        """content_generation.system_prompt가 ai_service에 전달"""
        sys_prompt = "당신은 전문 블로거입니다."
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {
                    "provider": "openai", "system_prompt": sys_prompt,
                },
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["system_prompt"] == sys_prompt

    @pytest.mark.asyncio
    async def test_legacy_generation_prompt_fallback(
        self, mock_db, sample_title
    ):
        """user_prompt_template 없으면 generation_prompt 레거시 키 사용"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {"provider": "openai"},
                "generation_prompt": "레거시: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert "레거시:" in kwargs["prompt"]
        assert "{title}" not in kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_new_user_prompt_template_priority(
        self, mock_db, sample_title
    ):
        """user_prompt_template이 generation_prompt보다 우선"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {
                    "provider": "openai",
                    "user_prompt_template": "새형식: {title}\n{reference_materials}",
                },
                "generation_prompt": "레거시: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert "새형식:" in kwargs["prompt"]
        assert "레거시:" not in kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_title_recombine_uses_title_ai_provider(
        self, mock_db, sample_title
    ):
        """제목 재조합 시 blog.title_ai.provider 사용 (content_generation.provider 무시)"""
        blog, module = _make_blog_module(
            ai_config={
                "writing_ai": {"provider": "openai"},
                "title_ai": {"provider": "anthropic"},
            },
            module_settings={
                "content_generation": {"enabled": True, "provider": "google"},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        gen, _ = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        _, recombine_kwargs = gen.title_recombiner.recombine.call_args
        assert recombine_kwargs["provider"] == "anthropic"


# ============================================================
# TestAIServiceSystemPrompt: system_prompt 전달 테스트
# ============================================================

class TestAIServiceSystemPrompt:
    """AIService.generate() system_prompt 파라미터 전달 테스트"""

    @pytest.mark.asyncio
    async def test_generate_passes_system_prompt(self, mock_db):
        """generate(system_prompt=...) → _try_provider에 전달"""
        from app.services.ai.ai_service import AIService

        service = AIService(mock_db, user_id=1)
        service._try_provider = AsyncMock(return_value=DEFAULT_AI_RESPONSE)
        service._get_provider_order = MagicMock(return_value=["openai"])

        await service.generate(
            prompt="테스트", provider="openai",
            system_prompt="시스템 프롬프트",
        )

        call_args = service._try_provider.call_args
        assert call_args[0][5] == "시스템 프롬프트"

    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self, mock_db):
        """system_prompt 미전달 시 None 전달"""
        from app.services.ai.ai_service import AIService

        service = AIService(mock_db, user_id=1)
        service._try_provider = AsyncMock(return_value=DEFAULT_AI_RESPONSE)
        service._get_provider_order = MagicMock(return_value=["openai"])

        await service.generate(prompt="테스트", provider="openai")

        call_args = service._try_provider.call_args
        assert call_args[0][5] is None


# ============================================================
# TestDefaultValueFallbacks: 기본값 폴백 엣지 케이스
# ============================================================

class TestDefaultValueFallbacks:
    """기본값 폴백 동작 검증"""

    @pytest.mark.asyncio
    async def test_temperature_default(self, mock_db, sample_title):
        """temperature 미설정 시 기본값 0.7"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {"provider": "openai"},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_max_tokens_default(self, mock_db, sample_title):
        """max_tokens 미설정 시 기본값 4000"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {"provider": "openai"},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["max_tokens"] == 4000

    @pytest.mark.asyncio
    async def test_default_prompt_when_both_missing(
        self, mock_db, sample_title
    ):
        """프롬프트 모두 없으면 DEFAULT_CONTENT_PROMPT 사용"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={"content_generation": {"provider": "openai"}},
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert "다음 주제로 블로그 글을 작성해주세요" in kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_system_prompt_none_when_empty_string(
        self, mock_db, sample_title
    ):
        """빈 문자열 system_prompt는 None으로 변환"""
        blog, module = _make_blog_module(
            ai_config={"writing_ai": {"provider": "openai"}},
            module_settings={
                "content_generation": {
                    "provider": "openai", "system_prompt": "",
                },
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        _, kwargs = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        assert kwargs["system_prompt"] is None

    @pytest.mark.asyncio
    async def test_title_recombine_falls_back_to_title_ai(
        self, mock_db, sample_title
    ):
        """모듈에 provider 없으면 title_ai.provider 폴백"""
        blog, module = _make_blog_module(
            ai_config={
                "writing_ai": {"provider": "openai"},
                "title_ai": {"provider": "anthropic"},
            },
            module_settings={
                "content_generation": {},
                "generation_prompt": "제목: {title}\n{reference_materials}",
            },
        )
        gen, _ = await _run_and_get_ai_kwargs(
            mock_db, blog, module, sample_title
        )
        _, recombine_kwargs = gen.title_recombiner.recombine.call_args
        assert recombine_kwargs["provider"] == "anthropic"
