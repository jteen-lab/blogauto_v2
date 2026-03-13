"""
Phase 5 섹션 이미지 파이프라인 테스트

섹션 파싱, 섹션별 이미지 생성, HTML 삽입 검증
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.generation.image_generator import ImageGenerator, ImageResult
from tests.fixtures.generation_pipeline_fixtures import create_mock_blog


MULTI_SECTION_HTML = (
    "<h1>제목</h1>"
    "<h2>서론</h2><p>서론 내용</p>"
    "<h2>본론 1</h2><p>본론 내용</p>"
    "<h2>본론 2</h2><p>추가 내용</p>"
    "<h2>결론</h2><p>마무리</p>"
)


def _make_blog_with_image_mode(
    image_mode: str = "template",
    ai_config: dict = None,
    overlay_config: dict = None,
) -> MagicMock:
    """이미지 설정이 포함된 Mock Blog 생성"""
    blog = create_mock_blog(
        blog_id=1,
        ai_config=ai_config or {"writing_ai": {"provider": "openai"}},
    )
    blog.image_mode = image_mode
    blog.overlay_config = overlay_config or {}
    return blog


# ============================================================
# TestSectionParsing: 섹션 파싱 테스트
# ============================================================

class TestSectionParsing:
    """섹션 파싱 로직 검증"""

    def test_parse_sections_extracts_h2(self, mock_db):
        """final_html에서 h2 태그 파싱"""
        gen = ImageGenerator(mock_db, user_id=1)
        sections = gen._parse_sections(MULTI_SECTION_HTML)

        assert len(sections) == 4
        assert sections[0]["heading"] == "서론"
        assert sections[1]["heading"] == "본론 1"
        assert sections[2]["heading"] == "본론 2"
        assert sections[3]["heading"] == "결론"

    def test_parse_sections_ignores_h1_h3(self, mock_db):
        """h1, h3 태그는 무시하고 h2만 파싱"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = "<h1>제목</h1><h3>소제목</h3><h2>섹션</h2>"
        sections = gen._parse_sections(html)

        assert len(sections) == 1
        assert sections[0]["heading"] == "섹션"

    def test_parse_sections_strips_inner_html(self, mock_db):
        """h2 내부 HTML 태그 제거 후 텍스트만 추출"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = '<h2><strong>강조</strong> 제목</h2>'
        sections = gen._parse_sections(html)

        assert len(sections) == 1
        assert sections[0]["heading"] == "강조 제목"

    def test_parse_sections_empty_html(self, mock_db):
        """빈 HTML이면 빈 리스트"""
        gen = ImageGenerator(mock_db, user_id=1)
        sections = gen._parse_sections("<p>h2 없는 글</p>")
        assert sections == []

    def test_parse_sections_with_attributes(self, mock_db):
        """h2에 class/id 등 속성이 있어도 파싱"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = '<h2 class="heading" id="s1">속성 있는 제목</h2>'
        sections = gen._parse_sections(html)

        assert len(sections) == 1
        assert sections[0]["heading"] == "속성 있는 제목"

    def test_parse_sections_positions_ascending(self, mock_db):
        """end_position이 순서대로 증가"""
        gen = ImageGenerator(mock_db, user_id=1)
        sections = gen._parse_sections(MULTI_SECTION_HTML)

        for i in range(len(sections) - 1):
            assert sections[i]["end_position"] < sections[i + 1]["end_position"]


# ============================================================
# TestSectionImageInsertion: 이미지 삽입 테스트
# ============================================================

class TestSectionImageInsertion:
    """섹션 이미지 HTML 삽입 검증"""

    def test_insert_section_images(self, mock_db):
        """섹션 이미지가 h2 태그 뒤에 삽입됨"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = "<h2>서론</h2><p>내용</p><h2>본론</h2><p>내용2</p>"
        sections = gen._parse_sections(html)

        section_images = [
            {
                "heading": "서론",
                "image_url": "/static/img1.png",
                "source": "template",
                "end_position": sections[0]["end_position"],
            },
            {
                "heading": "본론",
                "image_url": "/static/img2.png",
                "source": "template",
                "end_position": sections[1]["end_position"],
            },
        ]

        result = gen._insert_section_images(html, section_images)

        assert "/static/img1.png" in result
        assert "/static/img2.png" in result
        assert result.index("/static/img1.png") < result.index("/static/img2.png")

    def test_insert_preserves_original_without_images(self, mock_db):
        """섹션 이미지 없으면 원본 HTML 유지"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = "<h2>서론</h2><p>내용</p>"
        result = gen._insert_section_images(html, [])
        assert result == html

    def test_insert_adds_section_image_class(self, mock_db):
        """삽입된 이미지에 section-image 클래스 포함"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = "<h2>서론</h2><p>내용</p>"
        sections = gen._parse_sections(html)

        section_images = [{
            "heading": "서론",
            "image_url": "/static/img.png",
            "source": "ai",
            "end_position": sections[0]["end_position"],
        }]

        result = gen._insert_section_images(html, section_images)
        assert 'class="section-image"' in result
        assert 'loading="lazy"' in result

    def test_insert_sets_alt_text(self, mock_db):
        """삽입된 이미지의 alt 텍스트에 섹션 제목 사용"""
        gen = ImageGenerator(mock_db, user_id=1)
        html = "<h2>건강한 식습관</h2><p>내용</p>"
        sections = gen._parse_sections(html)

        section_images = [{
            "heading": "건강한 식습관",
            "image_url": "/static/img.png",
            "source": "template",
            "end_position": sections[0]["end_position"],
        }]

        result = gen._insert_section_images(html, section_images)
        assert 'alt="건강한 식습관"' in result


# ============================================================
# TestBothModeIntegration: both 모드 통합 테스트
# ============================================================

class TestBothModeIntegration:
    """both 모드에서 섹션 이미지 파이프라인 통합 검증"""

    @pytest.mark.asyncio
    async def test_both_mode_with_sections(self, mock_db):
        """both 모드에서 final_html 전달 시 섹션별 이미지 생성"""
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

        result = await gen.generate(
            blog, "테스트 제목", settings, final_html=MULTI_SECTION_HTML,
        )

        assert result.image_mode == "both"
        assert result.section_images is not None
        assert len(result.section_images) == 4
        assert result.final_html is not None
        assert "section-image" in result.final_html

    @pytest.mark.asyncio
    async def test_both_mode_no_final_html(self, mock_db):
        """both 모드에서 final_html 없으면 섹션 이미지 생략"""
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
        assert result.section_images is None
        assert result.final_html is None

    @pytest.mark.asyncio
    async def test_non_both_mode_ignores_final_html(self, mock_db):
        """template/ai 모드에서는 final_html을 무시"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/tpl.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog_with_image_mode("template")
        settings = {"image_generation": {"enabled": True}}

        result = await gen.generate(
            blog, "테스트", settings, final_html=MULTI_SECTION_HTML,
        )

        assert result.image_mode == "template"
        assert result.section_images is None
        assert result.final_html is None

    @pytest.mark.asyncio
    async def test_both_mode_section_source_ai(self, mock_db):
        """both 모드 section_source=ai일 때 AI로 섹션 이미지 생성"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        blog = _make_blog_with_image_mode(
            "both",
            overlay_config={"cover_source": "ai", "section_source": "ai"},
        )
        settings = {"image_generation": {"enabled": True}}
        html = "<h2>섹션1</h2><p>내용</p>"

        result = await gen.generate(
            blog, "테스트", settings, final_html=html,
        )

        assert result.section_images is not None
        assert len(result.section_images) == 1
        assert result.section_images[0]["source"] == "ai"

    @pytest.mark.asyncio
    async def test_section_image_count_matches_h2_count(self, mock_db):
        """생성된 섹션 이미지 수 = h2 태그 수"""
        gen = ImageGenerator(mock_db, user_id=1)
        gen.ai_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/ai.png",
            "provider": "dalle",
            "model": "dall-e-3",
        })
        gen.template_image.generate = AsyncMock(return_value={
            "image_url": "/static/generated/images/sec.png",
            "provider": "template",
            "model": None,
        })
        blog = _make_blog_with_image_mode("both")
        settings = {"image_generation": {"enabled": True}}
        html = "<h2>A</h2><h2>B</h2><h2>C</h2>"

        result = await gen.generate(
            blog, "테스트", settings, final_html=html,
        )

        assert len(result.section_images) == 3
