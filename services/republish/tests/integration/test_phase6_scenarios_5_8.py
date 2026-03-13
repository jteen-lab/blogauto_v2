"""
Phase 6: 이미지 생성 통합 설정 검증 (시나리오 5~8)

시나리오 5: both 모드 소스 설정
시나리오 6: template 모드
시나리오 7: quality=HD + Nanobanana
시나리오 8: 레거시 데이터 마이그레이션
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.generation.image_generator import ImageGenerator, ImageResult
from app.services.generation.image_param_converter import (
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
# 시나리오 5: both 모드 + cover=ai, section=template
# ============================================================

class TestScenario5_BothModeSourceConfig:
    """both 모드: cover=ai, section=template 소스 분리 동작"""

    @pytest.mark.asyncio
    async def test_cover_ai_section_template(self, mock_db):
        """대표=AI, 섹션=템플릿으로 분리 생성"""
        gen = ImageGenerator(mock_db, user_id=1)

        ai_call_count = 0
        tpl_call_count = 0

        async def mock_ai_gen(**kwargs):
            nonlocal ai_call_count
            ai_call_count += 1
            return {
                "image_url": f"/static/ai_{ai_call_count}.png",
                "provider": "dalle",
                "model": "dall-e-3",
            }

        async def mock_tpl_gen(**kwargs):
            nonlocal tpl_call_count
            tpl_call_count += 1
            return {
                "image_url": f"/static/tpl_{tpl_call_count}.png",
                "provider": "template",
                "model": None,
            }

        gen.ai_image.generate = mock_ai_gen
        gen.template_image.generate = mock_tpl_gen
        blog = _make_blog(
            image_mode="both",
            overlay_config={
                "cover_source": "ai",
                "section_source": "template",
            },
        )
        html = "<h2>섹션A</h2><p>A</p><h2>섹션B</h2><p>B</p>"

        result = await gen.generate(
            blog, "테스트", UNIFIED_MODULE_SETTINGS, final_html=html,
        )

        assert result.success is True
        assert "ai_1" in result.image_url
        assert all(
            img["source"] == "template" for img in result.section_images
        )
        assert len(result.section_images) == 2

    @pytest.mark.asyncio
    async def test_cover_template_section_ai(self, mock_db):
        """반대로 cover=template, section=ai"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/tpl.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog(
            image_mode="both",
            overlay_config={
                "cover_source": "template",
                "section_source": "ai",
            },
        )
        html = "<h2>섹션</h2><p>내용</p>"

        result = await gen.generate(
            blog, "테스트", UNIFIED_MODULE_SETTINGS, final_html=html,
        )

        assert result.image_url == "/static/tpl.png"
        assert result.section_images[0]["source"] == "ai"


# ============================================================
# 시나리오 6: template 모드
# ============================================================

class TestScenario6_TemplateMode:
    """template 모드: AI 생성 건너뜀, 템플릿만 사용"""

    @pytest.mark.asyncio
    async def test_template_mode_skips_ai(self, mock_db):
        """template 모드에서 AI 서비스 호출 안 함"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock()
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/tpl.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog(image_mode="template")

        result = await gen.generate(blog, "테스트", UNIFIED_MODULE_SETTINGS)

        assert result.success is True
        assert result.image_mode == "template"
        assert result.provider == "template"
        gen.ai_image.generate.assert_not_awaited()
        gen.template_image.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_template_mode_ignores_final_html(self, mock_db):
        """template 모드에서 final_html 전달해도 섹션 이미지 생성 안 함"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/tpl.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog(image_mode="template")

        result = await gen.generate(
            blog, "테스트", UNIFIED_MODULE_SETTINGS,
            final_html=THREE_SECTION_HTML,
        )

        assert result.section_images is None
        assert result.final_html is None


# ============================================================
# 시나리오 7: quality=HD + Nanobanana 블로그
# ============================================================

class TestScenario7_QualityHdNanobanana:
    """quality=HD + Nanobanana → HD 무시됨"""

    def test_nanobanana_ignores_quality(self):
        """Nanobanana 변환 시 quality 파라미터 미포함"""
        params = convert_to_provider_params(
            {"aspect_ratio": "1:1", "style": "vivid", "quality": "hd"},
            provider="nanobanana",
        )
        assert "quality" not in params
        assert params["style"] == "artistic"
        assert params["aspect_ratio"] == "1:1"

    def test_dalle_preserves_hd(self):
        """DALL-E는 quality=hd 보존"""
        params = convert_to_provider_params(
            {"aspect_ratio": "1:1", "style": "vivid", "quality": "hd"},
            provider="dalle",
        )
        assert params["quality"] == "hd"

    @pytest.mark.asyncio
    async def test_e2e_nanobanana_hd_not_in_params(self, mock_db):
        """E2E: Nanobanana 블로그에 HD 설정 시 params에 quality 없음"""
        gen = ImageGenerator(mock_db, user_id=1)
        captured_kwargs = {}

        async def mock_generate(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "image_url": "/static/nano.png",
                "provider": "nanobanana",
                "model": "gemini-2.0-flash-exp",
            }

        gen.ai_image.generate = mock_generate
        blog = _make_blog(image_mode="ai", image_provider="nanobanana")
        settings = {
            "image_generation": {
                "enabled": True,
                "aspect_ratio": "16:9",
                "style": "realistic",
                "quality": "hd",
            },
        }

        await gen.generate(blog, "테스트", settings)

        assert "quality" not in captured_kwargs["provider_params"]


# ============================================================
# 시나리오 8: 기존 모듈 데이터 마이그레이션
# ============================================================

class TestScenario8_LegacyMigration:
    """dalle{}/nanobanana{} 레거시 → 통합 키 변환"""

    def test_migrate_dalle_settings(self):
        """DALL-E 레거시 설정 → 통합 키"""
        legacy = {
            "enabled": True,
            "provider": "dalle",
            "dalle": {
                "size": "1792x1024",
                "quality": "standard",
                "style": "natural",
            },
            "nanobanana": {},
            "prompt_template": "이미지: {title}",
            "images_per_post": 1,
        }
        result = migrate_legacy_image_settings(legacy)

        assert result["aspect_ratio"] == "16:9"
        assert result["style"] == "realistic"
        assert result["quality"] == "standard"
        assert result["prompt_template"] == "이미지: {title}"
        assert "dalle" not in result
        assert "nanobanana" not in result
        assert "provider" not in result
        assert "images_per_post" not in result

    def test_migrate_nanobanana_settings(self):
        """Nanobanana 레거시 설정 → 통합 키"""
        legacy = {
            "enabled": True,
            "provider": "nanobanana",
            "dalle": {},
            "nanobanana": {
                "aspectRatio": "9:16",
                "style": "cartoon",
            },
            "prompt_template": "이미지: {title}",
        }
        result = migrate_legacy_image_settings(legacy)

        assert result["aspect_ratio"] == "9:16"
        assert result["style"] == "cartoon"
        assert result["quality"] == "standard"
        assert "nanobanana" not in result
        assert "provider" not in result

    def test_already_unified_unchanged(self):
        """이미 통합 형식이면 그대로 반환"""
        unified = {
            "enabled": True,
            "aspect_ratio": "16:9",
            "style": "realistic",
            "quality": "standard",
        }
        result = migrate_legacy_image_settings(unified)
        assert result is unified

    def test_no_legacy_keys_unchanged(self):
        """레거시 키 없으면 그대로 반환"""
        minimal = {"enabled": True, "prompt_template": "test"}
        result = migrate_legacy_image_settings(minimal)
        assert result is minimal

    def test_migrate_dalle_1024x1024(self):
        """DALL-E size=1024x1024 → aspect_ratio=1:1"""
        legacy = {
            "dalle": {"size": "1024x1024", "style": "vivid", "quality": "hd"},
        }
        result = migrate_legacy_image_settings(legacy)

        assert result["aspect_ratio"] == "1:1"
        assert result["style"] == "vivid"
        assert result["quality"] == "hd"

    def test_migrate_dalle_9_16(self):
        """DALL-E size=1024x1792 → aspect_ratio=9:16"""
        legacy = {
            "dalle": {"size": "1024x1792", "style": "natural", "quality": "standard"},
        }
        result = migrate_legacy_image_settings(legacy)
        assert result["aspect_ratio"] == "9:16"

    @pytest.mark.asyncio
    async def test_e2e_legacy_module_auto_migrated(self, mock_db):
        """E2E: 레거시 모듈 데이터가 generate()에서 자동 변환"""
        gen = ImageGenerator(mock_db, user_id=1)
        captured_kwargs = {}

        async def mock_generate(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "image_url": "/static/test.png",
                "provider": "dalle",
                "model": "dall-e-3",
            }

        gen.ai_image.generate = mock_generate
        blog = _make_blog(image_mode="openai", image_provider="openai")

        legacy_settings = {
            "image_generation": {
                "enabled": True,
                "provider": "dalle",
                "dalle": {
                    "size": "1792x1024",
                    "quality": "standard",
                    "style": "natural",
                },
                "nanobanana": {},
                "prompt_template": "이미지: {title}",
                "images_per_post": 1,
            },
        }

        result = await gen.generate(blog, "테스트", legacy_settings)

        assert result.success is True
        assert captured_kwargs["provider_params"]["size"] == "1792x1024"
        assert captured_kwargs["provider_params"]["style"] == "natural"

    def test_migrate_removes_cover_section_source(self):
        """마이그레이션 시 cover_source/section_source 제거"""
        legacy = {
            "enabled": True,
            "dalle": {"size": "1024x1024", "style": "vivid", "quality": "standard"},
            "cover_source": "ai",
            "section_source": "template",
        }
        result = migrate_legacy_image_settings(legacy)

        assert "cover_source" not in result
        assert "section_source" not in result
