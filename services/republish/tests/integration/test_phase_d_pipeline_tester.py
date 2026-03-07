"""Phase D 파이프라인 테스터 통합 테스트"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.generation.pipeline_tester import PipelineTester
from app.services.generation.image_generator import ImageResult
from app.services.generation.title_recombiner import RecombineStyleResult
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_blog,
    create_mock_main_title,
    create_mock_module,
    create_mock_recombine_result,
    create_mock_reference_result,
    create_module_settings_all_enabled,
    create_db_get_side_effect,
)

SAMPLE_AI_RESPONSE = {
    "content": "## 서론\n테스트 콘텐츠",
    "model": "gpt-4o-mini",
    "provider": "openai",
}
SAMPLE_HTML = "<h2>서론</h2><p>테스트 콘텐츠</p>"


def _make_tester(mock_db, user_id: int = 1) -> PipelineTester:
    return PipelineTester(mock_db, user_id)


class TestSelectTitle:
    """Step 1: 제목 선택 테스트"""

    @pytest.mark.asyncio
    async def test_success_with_candidates(self, mock_db):
        """후보 제목이 있을 때 성공"""
        module = create_mock_module(module_id=1)
        titles = [
            create_mock_main_title(title_id=i, title=f"제목 {i}")
            for i in range(1, 4)
        ]
        mock_db.get = AsyncMock(return_value=module)

        tester = _make_tester(mock_db)
        tester.inventory_trigger.find_available_titles = AsyncMock(
            return_value=titles,
        )
        # module.settings에 categories 없으므로 _get_blog_category_filter_ids 호출됨
        tester.inventory_trigger._get_blog_category_filter_ids = AsyncMock(
            return_value=(set(), set()),
        )

        result = await tester.test_select_title(blog_id=1, module_id=1)

        assert result["success"] is True
        assert result["step"] == "select_title"
        assert result["result"]["total_candidates"] == 3
        assert result["result"]["selected_title"]["id"] in [1, 2, 3]
        # 카테고리 미설정 -> blog_category 소스, has_category_filter=False
        assert result["result"]["filter_info"]["source"] == "blog_category"
        assert result["result"]["filter_info"]["has_category_filter"] is False

    @pytest.mark.asyncio
    async def test_no_candidates(self, mock_db):
        """사용 가능한 제목이 없을 때 에러"""
        module = create_mock_module(module_id=1)
        mock_db.get = AsyncMock(return_value=module)

        tester = _make_tester(mock_db)
        tester.inventory_trigger.find_available_titles = AsyncMock(
            return_value=[],
        )

        result = await tester.test_select_title(blog_id=1, module_id=1)

        assert result["success"] is False
        assert "사용 가능한 제목이 없습니다" in result["error"]

    @pytest.mark.asyncio
    async def test_module_not_found(self, mock_db):
        """모듈이 없을 때 에러"""
        mock_db.get = AsyncMock(return_value=None)

        tester = _make_tester(mock_db)

        result = await tester.test_select_title(blog_id=1, module_id=999)

        assert result["success"] is False
        assert "모듈을 찾을 수 없습니다" in result["error"]

    @pytest.mark.asyncio
    async def test_filter_info_shows_source(self, mock_db):
        """필터 정보에 카테고리 소스가 표시됨"""
        settings = create_module_settings_all_enabled()
        settings["categories"] = [
            {"topic_id": 1, "subtopic_id": 3},
            {"topic_id": 2},
        ]
        module = create_mock_module(module_id=1, settings=settings)
        titles = [create_mock_main_title(title_id=1)]
        mock_db.get = AsyncMock(return_value=module)

        tester = _make_tester(mock_db)
        tester.inventory_trigger.find_available_titles = AsyncMock(
            return_value=titles,
        )

        result = await tester.test_select_title(blog_id=1, module_id=1)

        fi = result["result"]["filter_info"]
        assert fi["source"] == "module_settings"
        assert fi["categories"] == settings["categories"]
        assert fi["has_category_filter"] is True
        assert fi["applied_subtopic_ids"] == [3]
        assert fi["applied_topic_only_ids"] == [2]


class TestRecombineTitle:
    """Step 2: 제목 재조합 테스트"""

    @pytest.mark.asyncio
    async def test_success_with_title_id(self, mock_db, sample_title):
        """title_id로 제목 로드 후 재조합"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module},
                MainTitle={1: sample_title},
                Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        recombine_result = create_mock_recombine_result()
        tester.title_recombiner.recombine_with_styles = AsyncMock(
            return_value=[RecombineStyleResult(
                style="default", style_label="기본",
                original_title=recombine_result.original_title,
                recombined_title=recombine_result.recombined_title,
                ai_model=recombine_result.ai_model,
                ai_provider=recombine_result.ai_provider,
                is_modified=recombine_result.is_modified,
            )],
        )

        result = await tester.test_recombine_title(
            module_id=1, blog_id=1, title_id=1,
        )

        assert result["success"] is True
        assert result["result"]["is_modified"] is True
        assert result["result"]["recombined_title"] is not None

    @pytest.mark.asyncio
    async def test_success_with_title_text(self, mock_db):
        """title_text 직접 입력으로 재조합"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module},
                Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        tester.title_recombiner.recombine_with_styles = AsyncMock(
            return_value=[RecombineStyleResult(
                style="default", style_label="기본",
                original_title="직접 입력 제목",
                recombined_title="SEO 최적화된 제목",
                ai_model="gpt-4o-mini",
                ai_provider="openai",
                is_modified=True,
            )],
        )

        result = await tester.test_recombine_title(
            module_id=1, blog_id=1, title_text="직접 입력 제목",
        )

        assert result["success"] is True
        assert result["result"]["original_title"] == "직접 입력 제목"

    @pytest.mark.asyncio
    async def test_no_title_provided(self, mock_db):
        """제목 미입력 시 에러"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module},
                Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)

        result = await tester.test_recombine_title(
            module_id=1, blog_id=1,
        )

        assert result["success"] is False
        assert "제목을 지정해주세요" in result["error"]


class TestCollectReferences:
    """Step 3: 참조자료 수집 테스트"""

    @pytest.mark.asyncio
    async def test_success(self, mock_db):
        """참조자료 수집 성공"""
        module = create_mock_module(module_id=1)
        mock_db.get = AsyncMock(return_value=module)
        ref_result = create_mock_reference_result(count=3)

        tester = _make_tester(mock_db)
        tester.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ref_result,
        )

        result = await tester.test_collect_references(
            module_id=1, search_query="포항 이사",
        )

        assert result["success"] is True
        assert result["result"]["total_collected"] == 3
        assert result["result"]["search_query"] == "포항 이사"
        assert len(result["result"]["summaries"]) == 3

    @pytest.mark.asyncio
    async def test_settings_info_included(self, mock_db):
        """설정 정보가 결과에 포함됨"""
        settings = create_module_settings_all_enabled()
        module = create_mock_module(module_id=1, settings=settings)
        mock_db.get = AsyncMock(return_value=module)
        ref_result = create_mock_reference_result(count=1)

        tester = _make_tester(mock_db)
        tester.reference_collector.collect_and_summarize = AsyncMock(
            return_value=ref_result,
        )

        result = await tester.test_collect_references(
            module_id=1, search_query="테스트",
        )

        used = result["result"]["settings_used"]
        assert used["max_search"] == 30
        assert used["crawl_target"] == 10


class TestGenerateContent:
    """Step 4: 글 생성 테스트"""

    @pytest.mark.asyncio
    async def test_success(self, mock_db):
        """글 생성 성공"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module}, Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        tester.ai_service.generate = AsyncMock(
            return_value=SAMPLE_AI_RESPONSE,
        )
        tester.substitution_processor.process = AsyncMock(
            return_value=SAMPLE_HTML,
        )

        result = await tester.test_generate_content(
            module_id=1, blog_id=1, title="테스트 제목",
        )

        assert result["success"] is True
        assert result["result"]["ai_provider"] == "openai"
        assert result["result"]["content_length"] > 0

    @pytest.mark.asyncio
    async def test_module_not_found(self, mock_db):
        """모듈이 없을 때 에러"""
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Blog={1: create_mock_blog()},
            ),
        )

        tester = _make_tester(mock_db)

        result = await tester.test_generate_content(
            module_id=999, blog_id=1, title="테스트",
        )

        assert result["success"] is False
        assert "모듈을 찾을 수 없습니다" in result["error"]

    @pytest.mark.asyncio
    async def test_blog_not_found(self, mock_db):
        """블로그가 없을 때 에러"""
        module = create_mock_module(module_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(Module={1: module}),
        )

        tester = _make_tester(mock_db)

        result = await tester.test_generate_content(
            module_id=1, blog_id=999, title="테스트",
        )

        assert result["success"] is False
        assert "블로그를 찾을 수 없습니다" in result["error"]

    @pytest.mark.asyncio
    async def test_ai_failure(self, mock_db):
        """AI 생성 실패 시 에러"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module}, Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        tester.ai_service.generate = AsyncMock(return_value=None)

        result = await tester.test_generate_content(
            module_id=1, blog_id=1, title="테스트",
        )

        assert result["success"] is False
        assert "AI 글 생성 실패" in result["error"]


class TestGenerateImage:
    """Step 5: 이미지 생성 테스트"""

    @pytest.mark.asyncio
    async def test_success(self, mock_db):
        """이미지 생성 성공"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        blog.image_mode = "openai"
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module}, Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        tester.image_generator.generate = AsyncMock(
            return_value=ImageResult(
                success=True,
                image_url="/static/images/test.png",
                image_mode="ai",
                provider="dalle",
                ai_model="dall-e-3",
            ),
        )

        result = await tester.test_generate_image(
            module_id=1, blog_id=1, title="테스트",
        )

        assert result["success"] is True
        assert result["result"]["image_url"] == "/static/images/test.png"
        assert result["result"]["provider"] == "dalle"

    @pytest.mark.asyncio
    async def test_image_failure(self, mock_db):
        """이미지 생성 실패 시 success=False"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        blog.image_mode = "openai"
        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module}, Blog={1: blog},
            ),
        )

        tester = _make_tester(mock_db)
        tester.image_generator.generate = AsyncMock(
            return_value=ImageResult(
                success=False, error="API 키 없음",
            ),
        )

        result = await tester.test_generate_image(
            module_id=1, blog_id=1, title="테스트",
        )

        assert result["success"] is False
        assert "API 키 없음" in result["error"]


class TestFullPipeline:
    """Step 6: 전체 파이프라인 테스트"""

    def _setup_tester(self, mock_db) -> PipelineTester:
        """전체 파이프라인용 Tester 준비"""
        module = create_mock_module(module_id=1)
        blog = create_mock_blog(blog_id=1)
        blog.image_mode = "template"

        titles = [create_mock_main_title(title_id=1)]

        mock_db.get = AsyncMock(
            side_effect=create_db_get_side_effect(
                Module={1: module},
                Blog={1: blog},
                MainTitle={1: titles[0]},
            ),
        )

        tester = _make_tester(mock_db)

        # Step 1: 제목 선택
        tester.inventory_trigger.find_available_titles = AsyncMock(
            return_value=titles,
        )
        # module.settings에 categories 없으므로 _get_blog_category_filter_ids 호출됨
        tester.inventory_trigger._get_blog_category_filter_ids = AsyncMock(
            return_value=(set(), set()),
        )

        # Step 2: 제목 재조합 (recombine_with_styles 사용)
        recombine_result = create_mock_recombine_result()
        tester.title_recombiner.recombine_with_styles = AsyncMock(
            return_value=[RecombineStyleResult(
                style="default", style_label="기본",
                original_title=recombine_result.original_title,
                recombined_title=recombine_result.recombined_title,
                ai_model=recombine_result.ai_model,
                ai_provider=recombine_result.ai_provider,
                is_modified=recombine_result.is_modified,
            )],
        )

        # Step 3: 참조자료 수집
        tester.reference_collector.collect_and_summarize = AsyncMock(
            return_value=create_mock_reference_result(count=2),
        )

        # Step 4: 글 생성
        tester.ai_service.generate = AsyncMock(
            return_value=SAMPLE_AI_RESPONSE,
        )

        # Step 5: 내부링크 삽입
        tester.internal_linker.insert_links = AsyncMock(
            return_value="## 서론\n테스트 콘텐츠\n[내부링크](http://test.com)",
        )

        # Step 6: 이미지 생성
        tester.image_generator.generate = AsyncMock(
            return_value=ImageResult(success=True),
        )

        # Step 7: 치환 처리
        tester.substitution_processor.process = AsyncMock(
            return_value=SAMPLE_HTML,
        )

        return tester

    @pytest.mark.asyncio
    async def test_full_pipeline_dry_run(self, mock_db):
        """dry_run=True: 모든 단계 실행, DB 저장 안 함"""
        tester = self._setup_tester(mock_db)

        result = await tester.test_full_pipeline(
            blog_id=1, module_id=1, dry_run=True,
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["saved"] is False
        assert "1_select_title" in result["steps"]
        assert "2_recombine" in result["steps"]
        assert "3_references" in result["steps"]
        assert "4_generate" in result["steps"]
        assert "5_internal_links" in result["steps"]
        assert "6_image" in result["steps"]
        assert "7_substitution" in result["steps"]

    @pytest.mark.asyncio
    async def test_all_steps_success(self, mock_db):
        """모든 단계 성공 시 success=True"""
        tester = self._setup_tester(mock_db)

        result = await tester.test_full_pipeline(
            blog_id=1, module_id=1, dry_run=True,
        )

        for step_key, step_val in result["steps"].items():
            assert step_val["success"] is True, f"{step_key} 실패"

    @pytest.mark.asyncio
    async def test_step1_failure_stops_pipeline(self, mock_db):
        """Step 1 실패 시 이후 단계 실행 안 함"""
        tester = self._setup_tester(mock_db)
        tester.inventory_trigger.find_available_titles = AsyncMock(
            return_value=[],
        )

        result = await tester.test_full_pipeline(
            blog_id=1, module_id=1, dry_run=True,
        )

        assert result["success"] is False
        assert "1_select_title" in result["steps"]
        assert "2_recombine" not in result["steps"]

    @pytest.mark.asyncio
    async def test_total_time_tracked(self, mock_db):
        """총 소요 시간이 기록됨"""
        tester = self._setup_tester(mock_db)

        result = await tester.test_full_pipeline(
            blog_id=1, module_id=1, dry_run=True,
        )

        assert "total_time_seconds" in result
        assert isinstance(result["total_time_seconds"], int)

    @pytest.mark.asyncio
    async def test_step_summaries_have_key_fields(self, mock_db):
        """각 step summary에 핵심 필드가 포함됨"""
        tester = self._setup_tester(mock_db)

        result = await tester.test_full_pipeline(
            blog_id=1, module_id=1, dry_run=True,
        )

        steps = result["steps"]

        # Step 1: title_id, title
        assert "title_id" in steps["1_select_title"]
        assert "title" in steps["1_select_title"]

        # Step 2: title, is_modified
        assert "title" in steps["2_recombine"]
        assert "is_modified" in steps["2_recombine"]

        # Step 3: count
        assert "count" in steps["3_references"]

        # Step 4: length, provider
        assert "length" in steps["4_generate"]
        assert "provider" in steps["4_generate"]

        # Step 5: internal_links length
        assert "length" in steps["5_internal_links"]

        # Step 6: image mode
        assert "mode" in steps["6_image"]

        # Step 7: html_length
        assert "html_length" in steps["7_substitution"]
