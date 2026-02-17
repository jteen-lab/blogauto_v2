"""
콘텐츠 생성 통합 서비스 (간소화 버전)

참조자료 수집 모듈을 프롬프트 모듈과 글 생성 워크플로우에 연동합니다.
워크플로우: 원본 제목 → (제목 재조합) → 참조자료 수집 → 글 생성

전체 파이프라인(내부링크, 치환, 저장 포함)은
generation.generator.ContentGenerator를 사용하세요.

Phase 2: AIService, ReferenceCollector, TitleRecombiner 통합
Phase 3: ContentGenerator로 전체 파이프라인 이관
"""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.title import MainTitle
from ..models.module import Module
from ..schemas.reference_collection import DocumentSummary
from .ai.ai_service import AIService
from .generation.reference_collector import ReferenceCollector
from .generation.title_recombiner import TitleRecombiner

logger = logging.getLogger(__name__)


@dataclass
class GeneratedContent:
    """생성된 콘텐츠 결과"""
    title: str
    content: str
    references: List[DocumentSummary]
    is_title_modified: bool
    generation_time_ms: int
    reference_collection_id: Optional[int] = None
    ai_model: Optional[str] = None
    ai_provider: Optional[str] = None


class ContentGenerationService:
    """콘텐츠 생성 통합 서비스"""

    REFERENCE_TEMPLATE = """
---
[참조자료]
{references_text}
---
위 참조자료를 바탕으로 "{title}" 주제의 블로그 글을 작성해주세요."""

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.ai_service = AIService(db, user_id)
        self.reference_collector = ReferenceCollector(db, user_id)
        self.title_recombiner = TitleRecombiner(db, user_id)

    async def generate_content(
        self, title_id: int, module_id: int
    ) -> GeneratedContent:
        """전체 글 생성 워크플로우 실행"""
        start_time = datetime.now()
        logger.info(
            f"[CONTENT_GEN] 시작 | title_id={title_id} | module_id={module_id}"
        )

        title = await self.db.get(MainTitle, title_id)
        module = await self.db.get(Module, module_id)
        if not title or not module:
            raise ValueError("제목 또는 모듈을 찾을 수 없습니다")

        settings = module.settings or {}

        # 1. 제목 재조합 (선택적)
        recombine_result = await self.title_recombiner.recombine(
            original_title=title.title,
            module_id=module_id,
        )
        working_title = recombine_result.recombined_title

        # 2. 참조자료 수집
        ref_result = await self.reference_collector.collect_and_summarize(
            search_query=working_title,
            module_id=module_id,
        )
        logger.info(f"[CONTENT_GEN] 참조자료 | count={ref_result.count}")

        # 3. 글 생성
        final_prompt = self._build_generation_prompt(
            working_title, ref_result.summaries, settings
        )
        ai_result = await self.ai_service.generate(
            prompt=final_prompt,
            max_tokens=4000,
        )
        content = ai_result["content"] if ai_result else ""

        duration_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )
        logger.info(f"[CONTENT_GEN] 완료 | duration={duration_ms}ms")

        return GeneratedContent(
            title=working_title,
            content=content,
            references=ref_result.summaries,
            is_title_modified=recombine_result.is_modified,
            generation_time_ms=duration_ms,
            reference_collection_id=ref_result.reference_id,
            ai_model=ai_result["model"] if ai_result else None,
            ai_provider=ai_result["provider"] if ai_result else None,
        )

    def _build_generation_prompt(
        self,
        title: str,
        refs: List[DocumentSummary],
        settings: dict,
    ) -> str:
        """글 생성 프롬프트 구성"""
        # 모듈에 커스텀 프롬프트가 있으면 사용
        base_prompt = settings.get(
            "generation_prompt",
            "블로그 글을 작성해주세요."
        )

        if not refs:
            return f"{base_prompt}\n\n제목: {title}"

        ref_texts = [
            f"참조 {i}:\n{r.summary}\n출처: {r.url}"
            for i, r in enumerate(refs, 1)
        ]
        return base_prompt + self.REFERENCE_TEMPLATE.format(
            references_text="\n\n".join(ref_texts), title=title
        )
