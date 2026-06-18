"""리뉴얼 전용 생성 경로 오케스트레이션 테스트 (mock 기반, 라이브 호출 없음)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blog import BlogPlatform
from app.services.renewal.renewal_generator import RenewalGenerator
from app.services.renewal.renewal_plan import RenewalPlan


def _wire(rg):
    rg.gen.reference_collector.collect_and_summarize = AsyncMock(
        return_value=SimpleNamespace(count=2, to_prompt_injection=lambda: "[참조]")
    )
    rg.gen.internal_linker.insert_links = AsyncMock(
        side_effect=lambda content, **k: content
    )
    rg.gen.substitution_processor.process = AsyncMock(
        side_effect=lambda content, **k: f"<div>{content}</div>"
    )
    rg.gen.ai_service = MagicMock()


def _blog():
    return SimpleNamespace(
        id=1, platform=BlogPlatform.WORDPRESS, ai_config={},
        editor_type="classic", name="t",
    )


@pytest.mark.asyncio
async def test_keep_title_reuse_image():
    db = MagicMock(); db.get = AsyncMock(return_value=None)
    rg = RenewalGenerator(db); _wire(rg)
    plan = RenewalPlan(recombine_title=False, image_action="reuse",
                       reuse_image_url="https://i.ibb.co/x.webp")
    module = SimpleNamespace(id=5, settings={})
    with patch("app.services.renewal.renewal_generator.generate_content_with_meta",
               new=AsyncMock(return_value={"content": "본문", "model": "m", "provider": "p"})), \
         patch("app.services.publishing.seo_meta_builder.SEOMetaBuilder") as SEO:
        SEO.return_value.build.return_value = {"focus_keyphrase": "k"}
        res = await rg.regenerate(_blog(), module, "원본 제목", plan)
    assert res.success
    assert res.title == "원본 제목"            # 제목 유지
    assert res.image_url == "https://i.ibb.co/x.webp"
    assert "i.ibb.co" in res.content_html      # 기존 이미지 주입됨


@pytest.mark.asyncio
async def test_recombine_title_new_image():
    db = MagicMock(); db.get = AsyncMock(return_value=None)
    rg = RenewalGenerator(db); _wire(rg)
    rg.gen.title_recombiner.recombine = AsyncMock(
        return_value=SimpleNamespace(recombined_title="재조합된 제목", ai_model="m")
    )
    rg.gen._generate_image_with_retry = AsyncMock(
        return_value=SimpleNamespace(success=True, image_url="/static/generated/images/new.webp", final_html="<div>본문</div><img src='/static/generated/images/new.webp'>")
    )
    plan = RenewalPlan(recombine_title=True, image_action="new")
    module = SimpleNamespace(id=5, settings={})
    with patch("app.services.renewal.renewal_generator.generate_content_with_meta",
               new=AsyncMock(return_value={"content": "본문", "model": "m", "provider": "p"})), \
         patch("app.services.publishing.seo_meta_builder.SEOMetaBuilder") as SEO:
        SEO.return_value.build.return_value = None
        res = await rg.regenerate(_blog(), module, "원본 제목", plan)
    assert res.success
    assert res.title == "재조합된 제목"
    assert res.image_url == "/static/generated/images/new.webp"


@pytest.mark.asyncio
async def test_reference_required_zero_aborts():
    db = MagicMock(); db.get = AsyncMock(return_value=None)
    rg = RenewalGenerator(db); _wire(rg)
    rg.gen.reference_collector.collect_and_summarize = AsyncMock(
        return_value=SimpleNamespace(count=0, to_prompt_injection=lambda: "")
    )
    plan = RenewalPlan(recombine_title=False, image_action="new")
    module = SimpleNamespace(id=5, settings={"reference": {"required": True}})
    res = await rg.regenerate(_blog(), module, "원본 제목", plan)
    assert res.success is False
    assert "참조자료" in res.error


def test_renewal_prompt_inherit_default():
    from app.services.renewal.renewal_generator import RenewalGenerator
    assert RenewalGenerator._renewal_prompt({}, "<p>x</p>") == ("", "", "")


def test_renewal_prompt_new_mode():
    from app.services.renewal.renewal_generator import RenewalGenerator
    s = {"content_generation": {"renewal_prompt": {"mode": "new", "text": "새 {title}"}}}
    o, e, x = RenewalGenerator._renewal_prompt(s, "<p>기존</p>")
    assert o == "새 {title}" and e == "" and x == "기존"


def test_renewal_prompt_additional_injects_existing():
    from app.services.renewal.renewal_generator import RenewalGenerator
    s = {"content_generation": {"renewal_prompt": {"mode": "additional", "text": "보존 확장"}}}
    o, e, x = RenewalGenerator._renewal_prompt(s, "<h2>T</h2><p>본문</p>")
    assert o == ""
    assert "보존 확장" in e and "T 본문" in e
    assert x == "T 본문"


def test_strip_html_caps_length():
    from app.services.renewal.renewal_generator import RenewalGenerator, EXISTING_CONTENT_MAX_CHARS
    long = "<p>" + ("가" * (EXISTING_CONTENT_MAX_CHARS + 500)) + "</p>"
    assert len(RenewalGenerator._strip_html(long)) == EXISTING_CONTENT_MAX_CHARS
