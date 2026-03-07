"""
FlowGenerateExecutor 통합 테스트

플로우 실행 시 prompt 타입 모듈의 전체 파이프라인을 검증합니다.
- 재고 확인 -> 제목 선택 -> ContentGenerator 호출 -> 결과 반환
- 다중 블로그 순차 실행 및 결과 집계

테스트 대상: app/services/generation/flow_generate_executor.py
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.generation.flow_generate_executor import FlowGenerateExecutor
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_blog,
    create_mock_module,
    create_mock_inventory_result,
    create_mock_generation_result,
    create_module_settings_all_enabled,
)


# ============================================================
# 클래스: TestExecuteForBlog - 단일 블로그 실행 테스트
# ============================================================


class TestExecuteForBlog:
    """단일 블로그에 대한 execute_for_blog() 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_generate_when_inventory_low(
        self, mock_db, prompt_module, sample_blog
    ):
        """재고 부족 시 ContentGenerator를 호출하여 글을 생성한다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_result = create_mock_inventory_result(
            blog_id=1,
            current_inventory=0,
            threshold=10,
            needs_generation=True,
            growth_stage="rapid_growth",
            title_id=1,
            title_text="포항 이삿짐센터 추천 가이드",
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result
        )

        gen_result = create_mock_generation_result(
            success=True,
            title="SEO 최적화 포항 이사업체 비교",
            html="<h2>서론</h2><p>테스트 내용</p>",
            reference_count=3,
        )

        gen_patch_path = (
            "app.services.generation.flow_generate_executor.ContentGenerator"
        )
        with patch(gen_patch_path) as MockGenClass:
            mock_gen_instance = AsyncMock()
            mock_gen_instance.generate = AsyncMock(return_value=gen_result)
            MockGenClass.return_value = mock_gen_instance

            # Act
            result = await executor.execute_for_blog(prompt_module, sample_blog)

        # Assert
        assert result["success"] is True
        assert result["skipped"] is False
        assert result["crawling_post_id"] is not None
        assert result["generation_history_id"] is not None
        assert result["reference_count"] == 3
        assert "post_title" in result
        mock_gen_instance.generate.assert_awaited_once_with(
            blog_id=1, prompt_module_id=1, source_title_id=1,
            text_replace_enabled=True,
        )

    @pytest.mark.asyncio
    async def test_skip_when_inventory_sufficient(
        self, mock_db, prompt_module, sample_blog
    ):
        """재고가 충분하면 생성을 스킵하고 success=True, skipped=True를 반환한다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_result = create_mock_inventory_result(
            blog_id=1,
            current_inventory=15,
            threshold=10,
            needs_generation=False,
            growth_stage="rapid_growth",
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result
        )

        # Act
        result = await executor.execute_for_blog(prompt_module, sample_blog)

        # Assert
        assert result["success"] is True
        assert result["skipped"] is True
        assert result["inventory"] == 15
        assert result["threshold"] == 10
        assert "crawling_post_id" not in result

    @pytest.mark.asyncio
    async def test_no_title_available_skips(
        self, mock_db, prompt_module, sample_blog
    ):
        """재고 부족이지만 사용 가능한 제목이 없으면 스킵한다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_result = create_mock_inventory_result(
            blog_id=1,
            current_inventory=0,
            threshold=10,
            needs_generation=True,
            growth_stage="rapid_growth",
            title_id=None,
            title_text=None,
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result
        )

        # Act
        result = await executor.execute_for_blog(prompt_module, sample_blog)

        # Assert
        assert result["success"] is True
        assert result["skipped"] is True
        assert "사용 가능한 제목" in result["message"]

    @pytest.mark.asyncio
    async def test_generation_failure_error(
        self, mock_db, prompt_module, sample_blog
    ):
        """ContentGenerator 실패 시 success=False와 에러 메시지를 반환한다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_result = create_mock_inventory_result(
            blog_id=1,
            current_inventory=0,
            threshold=10,
            needs_generation=True,
            growth_stage="rapid_growth",
            title_id=1,
            title_text="포항 이삿짐센터 추천 가이드",
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result
        )

        gen_result = create_mock_generation_result(
            success=False,
            error="AI 오류: 모델 응답 없음",
        )

        gen_patch_path = (
            "app.services.generation.flow_generate_executor.ContentGenerator"
        )
        with patch(gen_patch_path) as MockGenClass:
            mock_gen_instance = AsyncMock()
            mock_gen_instance.generate = AsyncMock(return_value=gen_result)
            MockGenClass.return_value = mock_gen_instance

            # Act
            result = await executor.execute_for_blog(prompt_module, sample_blog)

        # Assert
        assert result["success"] is False
        assert result["skipped"] is False
        assert "error" in result
        assert "AI 오류" in result["error"]

    @pytest.mark.asyncio
    async def test_exception_safe_return(
        self, mock_db, prompt_module, sample_blog
    ):
        """예외 발생 시 success=False와 오류 메시지를 안전하게 반환한다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        executor.inventory_trigger.check_inventory = AsyncMock(
            side_effect=RuntimeError("DB 연결 실패")
        )

        # Act
        result = await executor.execute_for_blog(prompt_module, sample_blog)

        # Assert
        assert result["success"] is False
        assert "오류" in result["message"]
        assert "DB 연결 실패" in result["error"]


# ============================================================
# 클래스: TestExecuteForBlogs - 다중 블로그 실행 테스트
# ============================================================


class TestExecuteForBlogs:
    """여러 블로그에 대한 execute_for_blogs() 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_two_blogs_independent(
        self, mock_db, prompt_module
    ):
        """블로그 2개가 각각 독립적으로 생성을 실행한다."""
        # Arrange
        blog_a = create_mock_blog(blog_id=1, name="블로그A", total_post_count=5)
        blog_b = create_mock_blog(blog_id=2, name="블로그B", total_post_count=8)

        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_a = create_mock_inventory_result(
            blog_id=1, needs_generation=True, title_id=10,
            title_text="제목A 테스트",
        )
        inventory_b = create_mock_inventory_result(
            blog_id=2, needs_generation=True, title_id=20,
            title_text="제목B 테스트",
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            side_effect=[inventory_a, inventory_b]
        )

        gen_result_a = create_mock_generation_result(success=True, title="제목A 변환")
        gen_result_b = create_mock_generation_result(success=True, title="제목B 변환")

        gen_patch_path = (
            "app.services.generation.flow_generate_executor.ContentGenerator"
        )
        with patch(gen_patch_path) as MockGenClass:
            mock_gen = AsyncMock()
            mock_gen.generate = AsyncMock(
                side_effect=[gen_result_a, gen_result_b]
            )
            MockGenClass.return_value = mock_gen

            # Act
            results = await executor.execute_for_blogs(
                prompt_module, [blog_a, blog_b]
            )

        # Assert
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is True
        assert mock_gen.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_for_blogs_summary(
        self, mock_db, prompt_module, sample_blog
    ):
        """결과에 blog_id와 blog_name 필드가 포함된다."""
        # Arrange
        executor = FlowGenerateExecutor(mock_db, user_id=1)

        inventory_result = create_mock_inventory_result(
            blog_id=1, needs_generation=True, title_id=1,
            title_text="테스트 제목",
        )
        executor.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result
        )

        gen_result = create_mock_generation_result(success=True)

        gen_patch_path = (
            "app.services.generation.flow_generate_executor.ContentGenerator"
        )
        with patch(gen_patch_path) as MockGenClass:
            mock_gen = AsyncMock()
            mock_gen.generate = AsyncMock(return_value=gen_result)
            MockGenClass.return_value = mock_gen

            # Act
            results = await executor.execute_for_blogs(
                prompt_module, [sample_blog]
            )

        # Assert
        assert len(results) == 1
        assert results[0]["blog_id"] == sample_blog.id
        assert results[0]["blog_name"] == sample_blog.name

    @pytest.mark.asyncio
    async def test_execute_for_blogs_mixed(
        self, mock_db, prompt_module
    ):
        """성공/스킵/실패가 혼합된 결과를 올바르게 집계한다."""
        # Arrange
        blog_a = create_mock_blog(blog_id=1, name="성공블로그")
        blog_b = create_mock_blog(blog_id=2, name="스킵블로그")
        blog_c = create_mock_blog(blog_id=3, name="실패블로그")
        blogs = [blog_a, blog_b, blog_c]

        executor = FlowGenerateExecutor(mock_db, user_id=1)

        mock_results = [
            # 블로그A: 성공
            {
                "success": True, "skipped": False,
                "message": "글 생성 완료",
                "crawling_post_id": 1,
            },
            # 블로그B: 스킵
            {
                "success": True, "skipped": True,
                "message": "재고 충분",
                "inventory": 15, "threshold": 10,
            },
            # 블로그C: 실패
            {
                "success": False, "skipped": False,
                "message": "생성 실패", "error": "AI 오류",
            },
        ]

        with patch.object(
            executor, "execute_for_blog", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.side_effect = mock_results

            # Act
            results = await executor.execute_for_blogs(prompt_module, blogs)

        # Assert
        assert len(results) == 3

        success_count = sum(
            1 for r in results
            if r.get("success") and not r.get("skipped")
        )
        skipped_count = sum(1 for r in results if r.get("skipped"))
        failed_count = sum(1 for r in results if not r.get("success"))

        assert success_count == 1
        assert skipped_count == 1
        assert failed_count == 1
        assert success_count + skipped_count + failed_count == 3

        # blog_id, blog_name이 각 결과에 추가되었는지 확인
        assert results[0]["blog_id"] == 1
        assert results[0]["blog_name"] == "성공블로그"
        assert results[2]["blog_id"] == 3
        assert results[2]["blog_name"] == "실패블로그"
