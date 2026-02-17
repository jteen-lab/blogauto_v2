"""
ContentGenerator 8단계 파이프라인 통합 테스트

ContentGenerator.generate() 메서드의 전체 파이프라인을 테스트합니다.

파이프라인 단계:
1. 원본 제목 로드 (MainTitle)
2. 블로그 로드 (Blog)
3. 모듈 로드 (Module)
4. 제목 재조합 (TitleRecombiner)
5. 참조자료 수집 (ReferenceCollector)
6. AI 글 생성 (AIService)
7. 내부링크 삽입 (InternalLinker)
8. 치환 처리 (SubstitutionProcessor)
9. DB 저장 (GenerationHistory + CrawledPost)
10. 원본 제목 사용 처리 (mark_used)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call

from app.services.generation.generator import ContentGenerator, GenerationResult
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_blog,
    create_mock_main_title,
    create_mock_module,
    create_module_settings_all_enabled,
    create_module_settings_no_reference,
    create_mock_recombine_result,
    create_mock_reference_result,
    create_db_get_side_effect,
    create_auto_id_add,
)

# 테스트용 상수
SAMPLE_MARKDOWN = "## 서론\n테스트 내용입니다.\n## 본론\n본문 내용\n## 결론\n마무리"
SAMPLE_HTML = "<h2>서론</h2><p>테스트 내용입니다.</p><h2>본론</h2><p>본문 내용</p>"
AI_RESPONSE = {
    "content": SAMPLE_MARKDOWN,
    "model": "gpt-4o-mini",
    "provider": "openai",
}


def _build_generator(
    mock_db: MagicMock,
    sample_title: MagicMock,
    sample_blog: MagicMock,
    prompt_module: MagicMock,
    *,
    recombine_title: str = "SEO 최적화 포항 이사업체 비교",
    recombine_modified: bool = True,
    reference_count: int = 3,
    ai_response: dict = None,
    linker_output: str = SAMPLE_MARKDOWN,
    processor_output: str = SAMPLE_HTML,
) -> ContentGenerator:
    """
    테스트용 ContentGenerator를 생성하고 서브서비스를 Mock으로 설정합니다.

    Args:
        mock_db: Mock DB 세션
        sample_title: Mock MainTitle 인스턴스
        sample_blog: Mock Blog 인스턴스
        prompt_module: Mock Module 인스턴스
        recombine_title: 재조합된 제목
        recombine_modified: 제목 변경 여부
        reference_count: 참조자료 개수
        ai_response: AI 응답 딕셔너리
        linker_output: 내부링크 삽입 결과
        processor_output: 치환 처리 결과

    Returns:
        ContentGenerator: Mock이 설정된 생성기 인스턴스
    """
    if ai_response is None:
        ai_response = AI_RESPONSE

    # db.get() 모델별 매핑
    mock_db.get = AsyncMock(side_effect=create_db_get_side_effect(
        MainTitle={sample_title.id: sample_title},
        Blog={sample_blog.id: sample_blog},
        Module={prompt_module.id: prompt_module},
    ))

    # db.add() 호출 시 자동 id 할당
    mock_db.add = MagicMock(side_effect=create_auto_id_add(start_id=100))

    generator = ContentGenerator(mock_db, user_id=1)

    # 서브서비스 Mock
    generator.title_recombiner.recombine = AsyncMock(
        return_value=create_mock_recombine_result(
            original=sample_title.title,
            recombined=recombine_title,
            is_modified=recombine_modified,
        )
    )
    generator.reference_collector.collect_and_summarize = AsyncMock(
        return_value=create_mock_reference_result(count=reference_count)
    )
    generator.ai_service.generate = AsyncMock(return_value=ai_response)
    generator.internal_linker.insert_links = AsyncMock(
        return_value=linker_output
    )
    generator.substitution_processor.process = AsyncMock(
        return_value=processor_output
    )

    return generator


class TestContentGeneratorPipeline:
    """ContentGenerator 8단계 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """모든 단계가 성공하는 전체 파이프라인 테스트.

        검증 항목:
        - success=True
        - crawling_post_id 존재
        - final_html 존재
        - reference_count == 3
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
            reference_count=3,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        assert result.crawling_post_id is not None
        assert result.final_html is not None
        assert result.final_html == SAMPLE_HTML
        assert result.reference_count == 3

    @pytest.mark.asyncio
    async def test_pipeline_without_reference(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """참조자료 비활성화 시 reference_count == 0으로 성공.

        참조 수집이 count=0 결과를 반환해도 파이프라인은 정상 완료됩니다.
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
            reference_count=0,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        assert result.reference_count == 0

    @pytest.mark.asyncio
    async def test_title_recombine_disabled(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """제목 재조합이 비활성화되면 원본 제목이 유지됩니다.

        TitleRecombiner가 원본 제목을 그대로 반환하는 시나리오.
        recombined_title이 원본 제목과 동일한지 확인합니다.
        """
        original_title = sample_title.title
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
            recombine_title=original_title,
            recombine_modified=False,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        assert result.recombined_title == original_title

    @pytest.mark.asyncio
    async def test_ai_api_error_returns_failure(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """AI 호출이 None을 반환하면 RuntimeError로 실패합니다.

        ai_service.generate()가 None을 반환 -> RuntimeError 발생
        -> generate()의 try-except가 잡아서 GenerationResult(success=False)
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
        )
        # AI 응답을 None으로 오버라이드
        generator.ai_service.generate = AsyncMock(return_value=None)

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is False
        assert result.error is not None
        assert "AI" in result.error

    @pytest.mark.asyncio
    async def test_reference_failure_continues(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """참조자료 수집이 빈 결과를 반환해도 파이프라인은 계속 진행됩니다.

        reference_collector가 count=0의 빈 결과를 반환하는 경우,
        나머지 단계가 정상적으로 완료되는지 확인합니다.
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
            reference_count=0,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        assert result.reference_count == 0
        # AI 호출이 여전히 수행되었는지 확인
        generator.ai_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_save_error_rollback(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """db.commit()에서 예외 발생 시 실패 결과를 반환합니다.

        파이프라인 마지막 단계에서 DB 커밋 실패를 시뮬레이션합니다.
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
        )
        mock_db.commit = AsyncMock(
            side_effect=Exception("DB commit failed")
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_invalid_title_id(
        self, mock_db, sample_blog, prompt_module
    ):
        """존재하지 않는 title_id로 조회하면 실패합니다.

        db.get(MainTitle, 999) -> None -> ValueError 발생
        -> error 메시지에 '제목' 포함
        """
        # title 매핑에 999가 없으므로 None 반환
        mock_db.get = AsyncMock(side_effect=create_db_get_side_effect(
            MainTitle={},
            Blog={sample_blog.id: sample_blog},
            Module={prompt_module.id: prompt_module},
        ))

        generator = ContentGenerator(mock_db, user_id=1)

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=999,
        )

        assert result.success is False
        assert result.error is not None
        assert "제목" in result.error

    @pytest.mark.asyncio
    async def test_title_marked_used_on_success(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """성공 시 source_title.mark_used()가 호출됩니다.

        파이프라인이 성공적으로 완료되면 원본 제목의 상태가
        mark_used()를 통해 'used'로 변경되어야 합니다.
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        sample_title.mark_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_crawled_post_saved_as_generated(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """CrawledPost 저장 시 source='generated'로 설정됩니다.

        db.add() 호출 인자 중 CrawledPost 객체의 source 필드가
        'generated'인지 확인합니다.
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True

        # db.add 호출 인자에서 CrawledPost 찾기
        add_calls = mock_db.add.call_args_list
        crawled_posts = [
            c.args[0] for c in add_calls
            if hasattr(c.args[0], 'source')
        ]
        assert len(crawled_posts) >= 1
        assert crawled_posts[0].source == "generated"

    @pytest.mark.asyncio
    async def test_generation_history_saved(
        self, mock_db, sample_title, sample_blog, prompt_module
    ):
        """GenerationHistory와 CrawledPost 모두 db.add()로 저장됩니다.

        파이프라인 성공 시 db.add()가 최소 2회 호출되어야 합니다:
        1. GenerationHistory 저장
        2. CrawledPost 저장
        """
        generator = _build_generator(
            mock_db, sample_title, sample_blog, prompt_module,
        )

        result = await generator.generate(
            blog_id=sample_blog.id,
            prompt_module_id=prompt_module.id,
            source_title_id=sample_title.id,
        )

        assert result.success is True
        assert mock_db.add.call_count >= 2
