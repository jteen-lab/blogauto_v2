"""
생성 모듈 메인 서비스

전체 생성 파이프라인을 오케스트레이션합니다.

워크플로우:
1. 원본 제목 로드
2. 제목 재조합 (TitleRecombiner)
3. 참조자료 수집 (ReferenceCollector)
4. 글 생성 (AIService)
5. 내부링크 삽입 (InternalLinker)
6. 치환 처리 (SubstitutionProcessor)
7. 저장 (CrawledPost + GenerationHistory)
8. 원본 제목 사용 처리 (mark_used)

설계 문서: generation_module_workplan.md - Phase 3 - 3.2.1
"""
import logging
import time
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.title import MainTitle
from ...models.module import Module
from ...models.crawled_post import CrawledPost
from ...models.generation_history import GenerationHistory
from ..ai.ai_service import AIService
from .title_recombiner import TitleRecombiner
from .reference_collector import ReferenceCollector
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor

logger = logging.getLogger(__name__)

# 기본 글 생성 프롬프트
DEFAULT_CONTENT_PROMPT = (
    "다음 주제로 블로그 글을 작성해주세요.\n\n"
    "제목: {title}\n\n"
    "{reference_materials}\n\n"
    "규칙:\n"
    "- 마크다운 형식으로 작성\n"
    "- ## 소제목을 사용하여 섹션 구분\n"
    "- 자연스러운 한국어 문장\n"
    "- 1500~3000자 분량"
)


@dataclass
class GenerationResult:
    """생성 파이프라인 결과"""
    success: bool
    crawling_post_id: Optional[int] = None
    generation_history_id: Optional[int] = None
    recombined_title: Optional[str] = None
    final_html: Optional[str] = None
    reference_count: int = 0
    generation_time_seconds: int = 0
    content_length: int = 0
    ai_model_title: Optional[str] = None
    ai_model_content: Optional[str] = None
    error: Optional[str] = None


class ContentGenerator:
    """
    생성 모듈 메인 서비스

    전체 생성 파이프라인을 오케스트레이션합니다.
    Phase 2에서 구현된 서비스들을 조합하여 동작합니다.
    """

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.ai_service = AIService(db, user_id)
        self.title_recombiner = TitleRecombiner(db, user_id)
        self.reference_collector = ReferenceCollector(db, user_id)
        self.internal_linker = InternalLinker(db)
        self.substitution_processor = SubstitutionProcessor(db)

    async def generate(
        self,
        blog_id: int,
        prompt_module_id: int,
        source_title_id: int,
    ) -> GenerationResult:
        """
        전체 생성 파이프라인 실행

        Args:
            blog_id: 블로그 ID
            prompt_module_id: 프롬프트 모듈 ID
            source_title_id: 원본 정식 제목 ID

        Returns:
            GenerationResult: 생성 결과
        """
        start_time = time.time()
        logger.info(
            f"[GENERATOR] 시작 | blog_id={blog_id} "
            f"| module_id={prompt_module_id} "
            f"| title_id={source_title_id}"
        )

        try:
            return await self._execute_pipeline(
                blog_id, prompt_module_id, source_title_id, start_time
            )
        except Exception as e:
            elapsed = int(time.time() - start_time)
            logger.error(f"[GENERATOR] 파이프라인 실패: {e}")
            return GenerationResult(
                success=False,
                generation_time_seconds=elapsed,
                error=str(e),
            )

    async def _execute_pipeline(
        self,
        blog_id: int,
        prompt_module_id: int,
        source_title_id: int,
        start_time: float,
    ) -> GenerationResult:
        """파이프라인 실행 로직"""
        # 1. 원본 제목 로드
        source_title = await self.db.get(MainTitle, source_title_id)
        if not source_title:
            raise ValueError(f"제목을 찾을 수 없습니다: id={source_title_id}")

        blog = await self.db.get(Blog, blog_id)
        if not blog:
            raise ValueError(f"블로그를 찾을 수 없습니다: id={blog_id}")

        module = await self.db.get(Module, prompt_module_id)
        if not module:
            raise ValueError(f"모듈을 찾을 수 없습니다: id={prompt_module_id}")

        settings = module.settings or {}
        logger.debug(
            f"[GENERATOR] 1단계 완료: 데이터 로드 | "
            f"title='{source_title.title[:30]}' | blog={blog.name}"
        )

        # 2. 제목 재조합
        recombine_result = await self.title_recombiner.recombine(
            original_title=source_title.title,
            module_id=prompt_module_id,
        )
        working_title = recombine_result.recombined_title
        logger.info(
            f"[GENERATOR] 제목 재조합 | "
            f"'{source_title.title[:30]}' → '{working_title[:30]}'"
        )

        # 3. 참조자료 수집
        ref_result = await self.reference_collector.collect_and_summarize(
            search_query=working_title,
            module_id=prompt_module_id,
        )
        logger.info(
            f"[GENERATOR] 참조자료 수집 | count={ref_result.count}"
        )

        # 4. 글 생성
        logger.debug(
            f"[GENERATOR] 4단계 시작: AI 글 생성 | "
            f"provider={blog.ai_config.get('writing_ai', {}).get('provider', 'auto')}"
        )
        content_result = await self._generate_content_with_meta(
            title=working_title,
            reference_injection=ref_result.to_prompt_injection(),
            settings=settings,
            blog=blog,
        )
        content_markdown = content_result["content"]
        ai_content_model = content_result.get("model")
        ai_content_provider = content_result.get("provider")

        # 5. 내부링크 삽입
        logger.debug("[GENERATOR] 5단계 시작: 내부링크 삽입")
        content_with_links = await self.internal_linker.insert_links(
            content=content_markdown,
            blog_id=blog_id,
            current_title=working_title,
            module_settings=settings,
        )

        # 6. 치환 처리 (마크다운 → HTML → 치환)
        logger.debug("[GENERATOR] 6단계 시작: 치환 처리")
        final_html = await self.substitution_processor.process(
            content=content_with_links,
            blog_id=blog_id,
        )

        # 7. GenerationHistory 저장
        elapsed = int(time.time() - start_time)
        history = GenerationHistory(
            blog_id=blog_id,
            source_title_id=source_title_id,
            prompt_module_id=prompt_module_id,
            recombined_title=working_title,
            ai_model_title=recombine_result.ai_model,
            ai_model_content=ai_content_model,
            reference_count=ref_result.count,
            generation_time_seconds=elapsed,
            content_length=len(final_html),
        )
        self.db.add(history)
        await self.db.flush()

        # 8. CrawledPost 저장 (source="generated")
        crawled_post = CrawledPost(
            blog_id=blog_id,
            title=working_title,
            source="generated",
            generation_history_id=history.id,
            match_status="unmatched",
        )
        self.db.add(crawled_post)
        await self.db.flush()

        # GenerationHistory에 crawling_post_id 연결
        history.crawling_post_id = crawled_post.id

        # 9. 원본 제목 사용 처리
        source_title.mark_used()
        logger.debug(
            f"[GENERATOR] 9단계 완료: 제목 사용 처리 (id={source_title_id})"
        )

        await self.db.commit()

        logger.info(
            f"[GENERATOR] 완료 | time={elapsed}s "
            f"| content_length={len(final_html)} "
            f"| refs={ref_result.count}"
        )

        return GenerationResult(
            success=True,
            crawling_post_id=crawled_post.id,
            generation_history_id=history.id,
            recombined_title=working_title,
            final_html=final_html,
            reference_count=ref_result.count,
            generation_time_seconds=elapsed,
            content_length=len(final_html),
            ai_model_title=recombine_result.ai_model,
            ai_model_content=ai_content_model,
        )

    async def _generate_content_with_meta(
        self,
        title: str,
        reference_injection: str,
        settings: dict,
        blog: Blog,
    ) -> dict:
        """
        AI로 글 생성 (메타데이터 포함)

        Args:
            title: 재조합된 제목
            reference_injection: 참조자료 프롬프트 텍스트
            settings: 모듈 설정
            blog: 블로그 객체

        Returns:
            dict: {"content": str, "model": str, "provider": str}
        """
        # 프롬프트 구성
        prompt_template = settings.get(
            "generation_prompt", DEFAULT_CONTENT_PROMPT
        )

        full_prompt = prompt_template.replace(
            "{title}", title
        ).replace(
            "{reference_materials}", reference_injection
        )

        # AI 설정 로드
        ai_config = blog.ai_config or {}
        writing_ai = ai_config.get("writing_ai", {})
        provider = writing_ai.get("provider")
        model = writing_ai.get("model")

        # AI 호출
        result = await self.ai_service.generate(
            prompt=full_prompt,
            provider=provider,
            model=model,
            max_tokens=4000,
            temperature=0.7,
        )

        if not result:
            raise RuntimeError("AI 글 생성 실패: 모든 제공자 호출 실패")

        return result

