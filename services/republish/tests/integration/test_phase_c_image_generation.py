"""
Phase C 이미지 생성 통합 테스트

ImageGenerator, AIImageService, generator.py 파이프라인 검증
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from app.services.generation.image_generator import (
    ImageGenerator, ImageResult,
)
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


def _make_blog_with_image_mode(
    image_mode: str = "template",
    ai_config: dict = None,
    overlay_config: dict = None,
) -> MagicMock:
    """이미지 설정이 포함된 Mock Blog 생성"""
    blog = create_mock_blog(
        blog_id=1, ai_config=ai_config or {"writing_ai": {"provider": "openai"}},
    )
    blog.image_mode = image_mode
    blog.overlay_config = overlay_config or {}
    return blog


def _make_module_with_image(
    enabled: bool = True,
    prompt_template: str = None,
    aspect_ratio: str = "16:9",
    style: str = "realistic",
    quality: str = "standard",
) -> MagicMock:
    """이미지 생성 설정이 포함된 Mock Module 생성 (통합 파라미터)"""
    settings = {
        "content_generation": {"provider": "openai"},
        "generation_prompt": "제목: {title}\n{reference_materials}",
        "image_generation": {
            "enabled": enabled,
            "aspect_ratio": aspect_ratio,
            "style": style,
            "quality": quality,
            "prompt_template": prompt_template or "블로그 이미지: {title}",
        },
    }
    return create_mock_module(module_id=1, settings=settings)


# ============================================================
# TestImageGeneratorRouting: image_mode별 라우팅 테스트
# ============================================================

class TestImageGeneratorRouting:
    """ImageGenerator의 image_mode별 라우팅 검증"""

    @pytest.mark.asyncio
    async def test_disabled_skips_generation(self, mock_db):
        """image_mode가 알려지지 않은 값이고 enabled=False면 건너뜀

        Note: image_mode가 template/openai/ai/both이면
        enabled 체크를 우회하므로, 미지정 모드에서만 테스트
        """
        gen = ImageGenerator(mock_db, user_id=1)
        blog = _make_blog_with_image_mode("custom")
        settings = {"image_generation": {"enabled": False}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_url is None

    @pytest.mark.asyncio
    async def test_no_image_settings_skips(self, mock_db):
        """image_mode가 알려지지 않은 값이고 image_generation 키 없으면 건너뜀"""
        gen = ImageGenerator(mock_db, user_id=1)
        blog = _make_blog_with_image_mode("custom")

        result = await gen.generate(blog, "테스트 제목", {})

        assert result.success is True
        assert result.image_url is None

    @pytest.mark.asyncio
    async def test_openai_mode_calls_ai(self, mock_db):
        """image_mode='openai'면 AI 이미지 서비스 호출"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/test.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        blog = _make_blog_with_image_mode("openai")
        settings = {"image_generation": {"enabled": True, "provider": "dalle"}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_mode == "ai"
        assert result.provider == "dalle"
        gen.ai_image.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ai_alias_works(self, mock_db):
        """image_mode='ai'도 AI 이미지 서비스 호출"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/test.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        blog = _make_blog_with_image_mode("ai")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_mode == "ai"

    @pytest.mark.asyncio
    async def test_template_mode_calls_template(self, mock_db):
        """image_mode='template'면 템플릿 이미지 서비스 호출"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/template.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog_with_image_mode("template")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_mode == "template"
        assert result.provider == "template"
        gen.template_image.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_both_mode_ai_success(self, mock_db):
        """image_mode='both'일 때 AI 성공하면 both 모드 결과 반환"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/section.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog_with_image_mode("both")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.image_mode == "both"
        assert result.image_url == "/static/generated/images/ai.png"

    @pytest.mark.asyncio
    async def test_both_mode_ai_fails_fallback_template(self, mock_db):
        """image_mode='both'일 때 AI 실패하면 템플릿 폴백 후 both 반환"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value=None)
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/fallback.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog_with_image_mode("both")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_mode == "both"
        assert result.image_url == "/static/generated/images/fallback.png"

    @pytest.mark.asyncio
    async def test_none_mode_skips(self, mock_db):
        """image_mode='none'이면 이미지 생성 안 함"""
        gen = ImageGenerator(mock_db, user_id=1)
        blog = _make_blog_with_image_mode("none")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(blog, "테스트 제목", settings)

        assert result.success is True
        assert result.image_url is None


# ============================================================
# TestAIImageService: AI 이미지 서비스 호출 테스트
# ============================================================

class TestAIImageService:
    """AIImageService 호출 검증 (Phase 3: 변환된 파라미터 수신)"""

    @pytest.mark.asyncio
    async def test_dalle_prompt_template_applied(self, mock_db):
        """prompt_template의 {title} 치환이 적용됨"""
        from app.services.generation.ai_image_service import AIImageService

        service = AIImageService(mock_db, user_id=1)
        service.key_manager.get_available_key = AsyncMock(
            return_value=MagicMock(id=1, api_key="sk-test"),
        )

        captured_prompt = None

        async def mock_dalle_api(api_key, prompt, model, size, quality, style):
            nonlocal captured_prompt
            captured_prompt = prompt
            return b"fake-image-bytes"

        service._call_dalle_api = mock_dalle_api
        service._save_image_bytes = AsyncMock(
            return_value="/static/generated/images/result.png",
        )
        service.key_manager.mark_key_used = AsyncMock()

        result = await service.generate(
            title="테스트 주제",
            provider="dalle",
            provider_params={"size": "1024x1024", "quality": "standard", "style": "natural", "model": "dall-e-3"},
            prompt_template="블로그 이미지: {title}",
            blog_id=1,
        )

        assert result is not None
        assert captured_prompt == "블로그 이미지: 테스트 주제"

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self, mock_db):
        """API 키 없으면 None 반환"""
        from app.services.generation.ai_image_service import AIImageService

        service = AIImageService(mock_db, user_id=1)
        service.key_manager.get_available_key = AsyncMock(return_value=None)

        result = await service.generate(
            title="테스트",
            provider="dalle",
            provider_params={"size": "1024x1024", "quality": "standard", "style": "natural", "model": "dall-e-3"},
            prompt_template="",
            blog_id=1,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_nanobanana_no_key_returns_none(self, mock_db):
        """Nanobanana provider에 Google API 키 없으면 None 반환"""
        from app.services.generation.ai_image_service import AIImageService

        service = AIImageService(mock_db, user_id=1)
        service.key_manager.get_available_key = AsyncMock(return_value=None)

        result = await service.generate(
            title="테스트",
            provider="nanobanana",
            provider_params={"aspect_ratio": "16:9", "style": "realistic", "model": "gemini-2.0-flash-exp"},
            prompt_template="",
            blog_id=1,
        )

        assert result is None


# ============================================================
# TestGeneratorPipelineImage: 파이프라인 이미지 통합 테스트
# ============================================================

class TestGeneratorPipelineImage:
    """ContentGenerator 파이프라인의 이미지 생성 단계 검증"""

    def _build_generator(
        self, mock_db, blog, module, title,
        image_result=None,
    ):
        """이미지 생성 포함 테스트용 ContentGenerator 생성"""
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
            ),
        )
        gen.reference_collector.collect_and_summarize = AsyncMock(
            return_value=create_mock_reference_result(count=0),
        )
        gen.ai_service.generate = AsyncMock(return_value=DEFAULT_AI_RESPONSE)
        gen.internal_linker.insert_links = AsyncMock(
            return_value=SAMPLE_MARKDOWN,
        )
        gen.substitution_processor.process = AsyncMock(
            return_value=SAMPLE_HTML,
        )

        if image_result is None:
            image_result = ImageResult(success=True)
        gen.image_generator.generate = AsyncMock(return_value=image_result)

        return gen

    @pytest.mark.asyncio
    async def test_image_url_in_result(self, mock_db, sample_title):
        """이미지 URL이 GenerationResult에 포함"""
        blog = _make_blog_with_image_mode("openai")
        module = _make_module_with_image(enabled=True)

        gen = self._build_generator(
            mock_db, blog, module, sample_title,
            image_result=ImageResult(
                success=True,
                image_url="/static/generated/images/test.png",
                image_mode="ai",
                provider="dalle",
                ai_model="dall-e-3",
            ),
        )

        result = await gen.generate(
            blog_id=1, prompt_module_id=1, source_title_id=1,
        )

        assert result.success is True
        assert result.image_url == "/static/generated/images/test.png"
        assert result.ai_model_image == "dall-e-3"

    @pytest.mark.asyncio
    async def test_no_image_when_disabled(self, mock_db, sample_title):
        """이미지 비활성화 시 image_url=None"""
        blog = _make_blog_with_image_mode("template")
        module = _make_module_with_image(enabled=False)

        gen = self._build_generator(
            mock_db, blog, module, sample_title,
            image_result=ImageResult(success=True),
        )

        result = await gen.generate(
            blog_id=1, prompt_module_id=1, source_title_id=1,
        )

        assert result.success is True
        assert result.image_url is None
        assert result.ai_model_image is None

    @pytest.mark.asyncio
    async def test_image_failure_does_not_break_pipeline(
        self, mock_db, sample_title,
    ):
        """이미지 생성 실패해도 글 생성은 정상 완료"""
        blog = _make_blog_with_image_mode("openai")
        module = _make_module_with_image(enabled=True)

        gen = self._build_generator(
            mock_db, blog, module, sample_title,
        )
        gen.image_generator.generate = AsyncMock(
            side_effect=RuntimeError("이미지 생성 오류"),
        )

        result = await gen.generate(
            blog_id=1, prompt_module_id=1, source_title_id=1,
        )

        assert result.success is True
        assert result.image_url is None
        assert result.final_html == SAMPLE_HTML

    @pytest.mark.asyncio
    async def test_image_failure_result_does_not_break(
        self, mock_db, sample_title,
    ):
        """ImageResult.success=False여도 글 생성 계속"""
        blog = _make_blog_with_image_mode("openai")
        module = _make_module_with_image(enabled=True)

        gen = self._build_generator(
            mock_db, blog, module, sample_title,
            image_result=ImageResult(
                success=False, error="API 오류",
            ),
        )

        result = await gen.generate(
            blog_id=1, prompt_module_id=1, source_title_id=1,
        )

        assert result.success is True
        assert result.image_url is None

    @pytest.mark.asyncio
    async def test_image_generator_receives_correct_args(
        self, mock_db, sample_title,
    ):
        """ImageGenerator.generate()에 올바른 인자가 전달"""
        blog = _make_blog_with_image_mode("openai")
        module = _make_module_with_image(enabled=True)

        gen = self._build_generator(
            mock_db, blog, module, sample_title,
        )

        await gen.generate(
            blog_id=1, prompt_module_id=1, source_title_id=1,
        )

        call_kwargs = gen.image_generator.generate.call_args[1]
        assert call_kwargs["title"] == "SEO 최적화된 테스트 제목"
        assert "image_generation" in call_kwargs["module_settings"]
        assert "final_html" in call_kwargs


# ============================================================
# TestImageResult: ImageResult 데이터클래스 테스트
# ============================================================

class TestImageResult:
    """ImageResult 데이터 구조 검증"""

    def test_default_values(self):
        """기본값 확인"""
        result = ImageResult(success=True)
        assert result.image_url is None
        assert result.image_mode is None
        assert result.provider is None
        assert result.ai_model is None
        assert result.generation_time_seconds == 0
        assert result.error is None
        assert result.final_html is None

    def test_full_values(self):
        """모든 필드 설정"""
        result = ImageResult(
            success=True,
            image_url="/static/generated/images/test.png",
            image_mode="ai",
            provider="dalle",
            ai_model="dall-e-3",
            generation_time_seconds=5,
            final_html="<h2>섹션</h2><p>내용</p>",
        )
        assert result.image_url == "/static/generated/images/test.png"
        assert result.ai_model == "dall-e-3"
        assert result.final_html is not None
