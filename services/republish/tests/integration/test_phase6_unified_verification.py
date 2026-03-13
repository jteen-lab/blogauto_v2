"""
Phase 6: 이미지 생성 통합 설정 검증 (시나리오 1~4)

시나리오 1: DALL-E 변환
시나리오 2: Nanobanana 변환
시나리오 3: title_overlay
시나리오 4: both 모드 + 섹션 이미지
시나리오 5~8은 test_phase6_scenarios_5_8.py 참조
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.generation.image_generator import ImageGenerator, ImageResult
from app.services.generation.image_param_converter import (
    normalize_provider,
    convert_to_provider_params,
    migrate_legacy_image_settings,
)
from tests.fixtures.generation_pipeline_fixtures import create_mock_blog


def _make_blog(
    image_mode: str = "openai",
    image_provider: str = "openai",
    image_model: str = None,
    overlay_config: dict = None,
) -> MagicMock:
    """이미지 테스트용 Mock Blog 생성"""
    ai_config = {
        "writing_ai": {"provider": "openai"},
        "image_ai": {"provider": image_provider},
    }
    if image_model:
        ai_config["image_ai"]["model"] = image_model
    blog = create_mock_blog(blog_id=1, ai_config=ai_config)
    blog.image_mode = image_mode
    blog.overlay_config = overlay_config or {}
    return blog


UNIFIED_MODULE_SETTINGS = {
    "image_generation": {
        "enabled": True,
        "aspect_ratio": "16:9",
        "style": "realistic",
        "quality": "standard",
        "prompt_template": "블로그 이미지: {title}",
        "title_overlay": False,
    },
}

THREE_SECTION_HTML = (
    "<h2>서론</h2><p>서론 내용</p>"
    "<h2>본론</h2><p>본론 내용</p>"
    "<h2>결론</h2><p>결론 내용</p>"
)


# ============================================================
# 시나리오 1: 블로그 A(DALL-E) + 모듈(16:9, 사실적)
# ============================================================

class TestScenario1_DalleConversion:
    """DALL-E 블로그 + 통합 파라미터 → 올바른 DALL-E 파라미터 전달"""

    def test_converter_dalle_16_9_realistic(self):
        """16:9 사실적 → DALL-E size=1792x1024, style=natural"""
        params = convert_to_provider_params(
            {"aspect_ratio": "16:9", "style": "realistic", "quality": "standard"},
            provider="openai",
        )
        assert params["size"] == "1792x1024"
        assert params["style"] == "natural"
        assert params["quality"] == "standard"
        assert params["model"] == "dall-e-3"

    def test_normalize_openai_to_dalle(self):
        """'openai' → 'dalle' 정규화"""
        assert normalize_provider("openai") == "dalle"
        assert normalize_provider("dall-e") == "dalle"
        assert normalize_provider("dalle") == "dalle"

    @pytest.mark.asyncio
    async def test_e2e_dalle_receives_correct_params(self, mock_db):
        """E2E: DALL-E 블로그에서 AI 서비스에 올바른 파라미터 전달"""
        gen = ImageGenerator(mock_db, user_id=1)
        captured_kwargs = {}

        async def mock_generate(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "image_url": "/static/generated/images/dalle.png",
                "provider": "dalle",
                "model": "dall-e-3",
            }

        gen.ai_image.generate = mock_generate
        blog = _make_blog(image_mode="openai", image_provider="openai")

        result = await gen.generate(blog, "테스트 제목", UNIFIED_MODULE_SETTINGS)

        assert result.success is True
        assert captured_kwargs["provider"] == "dalle"
        assert captured_kwargs["provider_params"]["size"] == "1792x1024"
        assert captured_kwargs["provider_params"]["style"] == "natural"
        assert captured_kwargs["provider_params"]["quality"] == "standard"


# ============================================================
# 시나리오 2: 블로그 B(Nanobanana) + 같은 모듈
# ============================================================

class TestScenario2_NanobananaConversion:
    """Nanobanana 블로그 + 같은 통합 파라미터 → Nanobanana 파라미터 전달"""

    def test_converter_nanobanana_16_9_realistic(self):
        """16:9 사실적 → Nanobanana aspectRatio=16:9, style=realistic"""
        params = convert_to_provider_params(
            {"aspect_ratio": "16:9", "style": "realistic", "quality": "standard"},
            provider="nanobanana",
        )
        assert params["aspect_ratio"] == "16:9"
        assert params["style"] == "realistic"
        assert params["model"] == "gemini-2.0-flash-exp"

    def test_normalize_gemini_to_nanobanana(self):
        """'gemini' → 'nanobanana' 정규화"""
        assert normalize_provider("gemini") == "nanobanana"
        assert normalize_provider("nanobanana") == "nanobanana"

    @pytest.mark.asyncio
    async def test_e2e_nanobanana_receives_correct_params(self, mock_db):
        """E2E: Nanobanana 블로그에서 올바른 파라미터 전달"""
        gen = ImageGenerator(mock_db, user_id=1)
        captured_kwargs = {}

        async def mock_generate(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "image_url": "/static/generated/images/nano.png",
                "provider": "nanobanana",
                "model": "gemini-2.0-flash-exp",
            }

        gen.ai_image.generate = mock_generate
        blog = _make_blog(
            image_mode="ai", image_provider="nanobanana",
        )

        result = await gen.generate(blog, "테스트 제목", UNIFIED_MODULE_SETTINGS)

        assert result.success is True
        assert captured_kwargs["provider"] == "nanobanana"
        assert captured_kwargs["provider_params"]["aspect_ratio"] == "16:9"
        assert captured_kwargs["provider_params"]["style"] == "realistic"

    @pytest.mark.asyncio
    async def test_same_module_different_blog_different_params(self, mock_db):
        """같은 모듈을 다른 블로그에 적용 시 다른 provider 파라미터 생성"""
        gen = ImageGenerator(mock_db, user_id=1)
        captured_calls = []

        async def mock_generate(**kwargs):
            captured_calls.append(kwargs.copy())
            return {
                "image_url": "/static/generated/images/test.png",
                "provider": kwargs["provider"],
                "model": "test",
            }

        gen.ai_image.generate = mock_generate

        # 블로그 A: DALL-E
        blog_a = _make_blog(image_mode="ai", image_provider="openai")
        await gen.generate(blog_a, "테스트", UNIFIED_MODULE_SETTINGS)

        # 블로그 B: Nanobanana
        blog_b = _make_blog(image_mode="ai", image_provider="nanobanana")
        await gen.generate(blog_b, "테스트", UNIFIED_MODULE_SETTINGS)

        assert captured_calls[0]["provider"] == "dalle"
        assert captured_calls[1]["provider"] == "nanobanana"
        assert captured_calls[0]["provider_params"]["size"] == "1792x1024"
        assert captured_calls[1]["provider_params"]["aspect_ratio"] == "16:9"


# ============================================================
# 시나리오 3: title_overlay=true + DALL-E
# ============================================================

class TestScenario3_TitleOverlay:
    """title_overlay=True일 때 AI 이미지 위에 오버레이 적용"""

    @pytest.mark.asyncio
    async def test_overlay_requires_overlay_config(self, mock_db):
        """title_overlay=True + overlay_config 없으면 실패"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        blog = _make_blog(
            image_mode="openai", overlay_config=None,
        )
        blog.overlay_config = None
        settings = {
            "image_generation": {
                **UNIFIED_MODULE_SETTINGS["image_generation"],
                "title_overlay": True,
            },
        }

        result = await gen.generate(blog, "테스트", settings)

        assert result.success is False
        assert "overlay_config" in result.error

    @pytest.mark.asyncio
    async def test_overlay_skipped_when_false(self, mock_db):
        """title_overlay=False면 오버레이 건너뜀"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        blog = _make_blog(image_mode="openai")

        result = await gen.generate(blog, "테스트", UNIFIED_MODULE_SETTINGS)

        assert result.success is True
        assert result.image_url == "/static/generated/images/ai.png"


# ============================================================
# 시나리오 4: both 모드 + 3섹션 글
# ============================================================

class TestScenario4_BothModeWithSections:
    """both 모드에서 대표 1장 + 섹션 3장 생성 및 글에 삽입"""

    @pytest.mark.asyncio
    async def test_cover_plus_3_sections(self, mock_db):
        """대표 이미지 1장 + 섹션 이미지 3장 생성"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/cover.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/section.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog(image_mode="both")

        result = await gen.generate(
            blog, "테스트 제목", UNIFIED_MODULE_SETTINGS,
            final_html=THREE_SECTION_HTML,
        )

        assert result.success is True
        assert result.image_mode == "both"
        assert result.image_url == "/static/generated/images/cover.png"
        assert result.section_images is not None
        assert len(result.section_images) == 3

    @pytest.mark.asyncio
    async def test_section_images_inserted_in_html(self, mock_db):
        """섹션 이미지가 HTML에 삽입됨"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/cover.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/sec.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog(image_mode="both")

        result = await gen.generate(
            blog, "테스트", UNIFIED_MODULE_SETTINGS,
            final_html=THREE_SECTION_HTML,
        )

        assert result.final_html is not None
        assert result.final_html.count("section-image") == 3
        assert result.final_html.count("sec.png") == 3
