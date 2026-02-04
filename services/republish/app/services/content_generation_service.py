"""
콘텐츠 생성 통합 서비스

참조자료 수집 모듈을 프롬프트 모듈과 글 생성 워크플로우에 연동합니다.
워크플로우: 원본 제목 → 제목 재조합(선택) → 참조자료 수집(선택) → 글 생성
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.title import MainTitle
from ..models.module import Module
from ..models.user_settings import UserSettings
from ..models.collected_reference import CollectedReference
from ..schemas.reference_collection import DocumentSummary

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

    async def generate_content(self, title_id: int, module_id: int) -> GeneratedContent:
        """전체 글 생성 워크플로우 실행"""
        start_time = datetime.now()
        logger.info(f"[CONTENT_GEN] 시작 | title_id={title_id} | module_id={module_id}")

        title = await self.db.get(MainTitle, title_id)
        module = await self.db.get(Module, module_id)
        if not title or not module:
            raise ValueError("제목 또는 모듈을 찾을 수 없습니다")

        settings = module.settings or {}
        working_title, is_modified = title.title, False

        # 제목 재조합
        if settings.get("enable_title_prompt") and settings.get("title_prompt_config"):
            new_title = await self._run_title_prompt(title.title, settings["title_prompt_config"])
            if new_title:
                working_title, is_modified = new_title, True
                logger.info(f"[CONTENT_GEN] 제목 재조합 완료")

        # 참조자료 수집
        references, ref_id = [], None
        if settings.get("enable_reference_collection", False):
            ref_count = settings.get("reference_count", 3)
            references, ref_id = await self._collect_references(working_title, ref_count)
            logger.info(f"[CONTENT_GEN] 참조자료 | count={len(references)}")

        # 글 생성
        prompt_config = settings.get("generation_prompt_config", {})
        final_prompt = self._build_generation_prompt(working_title, references, prompt_config)
        content = await self._call_ai(final_prompt, max_tokens=4000) or ""

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.info(f"[CONTENT_GEN] 완료 | duration={duration_ms}ms")

        return GeneratedContent(
            title=working_title, content=content, references=references,
            is_title_modified=is_modified, generation_time_ms=duration_ms,
            reference_collection_id=ref_id
        )

    async def _run_title_prompt(self, original_title: str, config: Dict) -> Optional[str]:
        """제목 재조합 프롬프트 실행"""
        prompt = config.get("prompt", "").replace("{title}", original_title)
        if not prompt:
            return None
        result = await self._call_ai(prompt, max_tokens=200)
        return result.strip() if result else None

    async def _collect_references(self, query: str, count: int = 3) -> tuple:
        """참조자료 수집"""
        from .reference_search_service import ReferenceSearchService
        from .reference_crawling_service import ReferenceCrawlingService
        from .reference_summary_service import ReferenceSummaryService

        try:
            user_settings = (await self.db.execute(
                select(UserSettings).where(UserSettings.user_id == self.user_id)
            )).scalar_one_or_none()
            if not user_settings:
                return [], None

            ref = CollectedReference(search_query=query, status="collecting")
            self.db.add(ref)
            await self.db.flush()

            # 검색
            results = await ReferenceSearchService(user_settings).search_webdoc(query, 30)
            ref.total_searched = len(results)
            if not results:
                ref.status, ref.completed_at = "failed", datetime.now()
                await self.db.commit()
                return [], ref.id

            # 크롤링
            crawl = await ReferenceCrawlingService(self.db).crawl_documents(
                [r.link for r in results], ref.id
            )
            ref.total_crawled, ref.total_failed = crawl.total_success, crawl.total_failed
            if not crawl.documents:
                ref.status, ref.completed_at = "failed", datetime.now()
                await self.db.commit()
                return [], ref.id

            # 요약
            summaries = await ReferenceSummaryService(self.db, self.user_id).summarize_documents(
                crawl.documents
            )
            summaries = summaries[:count]
            ref.selected_references = [
                {"url": s.url, "title": s.title, "summary": s.summary,
                 "original_length": s.original_length, "is_ai_summary": s.is_ai_summary}
                for s in summaries
            ]
            ref.status, ref.completed_at = "completed", datetime.now()
            await self.db.commit()
            return summaries, ref.id

        except Exception as e:
            logger.error(f"[CONTENT_GEN] 참조자료 수집 실패: {e}")
            return [], None

    def _build_generation_prompt(self, title: str, refs: List[DocumentSummary], config: Dict) -> str:
        """글 생성 프롬프트 구성"""
        user_prompt = config.get("prompt", "블로그 글을 작성해주세요.")
        if not refs:
            return f"{user_prompt}\n\n제목: {title}"

        ref_texts = [f"참조 {i}:\n{r.summary}\n출처: {r.url}" for i, r in enumerate(refs, 1)]
        return user_prompt + self.REFERENCE_TEMPLATE.format(
            references_text="\n\n".join(ref_texts), title=title
        )

    async def _call_ai(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """AI API 호출"""
        from .ai_key_manager import AIKeyManager
        from ..schemas.ai_api_key import AIProvider

        try:
            mgr = AIKeyManager(self.db, self.user_id)

            # OpenAI
            key = await mgr.get_available_key(AIProvider.OPENAI)
            if key:
                result = await self._openai(key.api_key, prompt, max_tokens)
                if result:
                    await mgr.mark_key_used(key.id)
                    return result

            # Anthropic
            key = await mgr.get_available_key(AIProvider.ANTHROPIC)
            if key:
                result = await self._anthropic(key.api_key, prompt, max_tokens)
                if result:
                    await mgr.mark_key_used(key.id)
                    return result

            return None
        except Exception as e:
            logger.error(f"[CONTENT_GEN] AI 호출 실패: {e}")
            return None

    async def _openai(self, api_key: str, prompt: str, max_tokens: int) -> Optional[str]:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0.7
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[CONTENT_GEN] OpenAI 실패: {e}")
            return None

    async def _anthropic(self, api_key: str, prompt: str, max_tokens: int) -> Optional[str]:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-3-haiku-20240307", max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[CONTENT_GEN] Anthropic 실패: {e}")
            return None
