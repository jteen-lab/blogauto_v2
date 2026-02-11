"""
콘텐츠 생성 통합 서비스

참조자료 수집 모듈을 프롬프트 모듈과 글 생성 워크플로우에 연동합니다.
워크플로우: 원본 제목 → 참조자료 수집(필수) → 글 생성
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
        working_title = title.title

        # 참조자료 수집 (필수)
        ref_settings = self._resolve_ref_settings(settings)
        references, ref_id = await self._collect_references(
            working_title, ref_settings
        )
        logger.info(f"[CONTENT_GEN] 참조자료 | count={len(references)}")

        # 글 생성
        final_prompt = self._build_generation_prompt(
            working_title, references
        )
        content = await self._call_ai(final_prompt, max_tokens=4000) or ""

        duration_ms = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )
        logger.info(f"[CONTENT_GEN] 완료 | duration={duration_ms}ms")

        return GeneratedContent(
            title=working_title,
            content=content,
            references=references,
            is_title_modified=False,
            generation_time_ms=duration_ms,
            reference_collection_id=ref_id
        )

    def _resolve_ref_settings(self, settings: Dict) -> Dict:
        """
        참조자료 설정 해석 (하위 호환 포함)

        새 형식: settings.reference = { max_search, crawl_target, ... }
        구 형식: settings.enable_reference_collection + reference_count
        """
        if "reference" in settings:
            return settings["reference"]

        # 구 형식 호환
        return {
            "max_search": 30,
            "crawl_target": 10,
            "summary_count": settings.get("reference_count", 3),
            "summary_method": "ai",
            "ai_provider": "openai",
            "ai_model": "gpt-4.1-mini",
            "summary_style": "concise",
            "algorithm_type": "textrank",
            "max_length": 500,
        }

    async def _collect_references(
        self, query: str, ref_settings: Dict
    ) -> tuple:
        """참조자료 수집 (설정 기반)"""
        from .reference_search_service import ReferenceSearchService
        from .reference_crawling_service import ReferenceCrawlingService
        from .reference_summary_service import ReferenceSummaryService

        max_search = ref_settings.get("max_search", 30)
        crawl_target = ref_settings.get("crawl_target", 10)
        summary_count = ref_settings.get("summary_count", 3)
        summary_method = ref_settings.get("summary_method", "ai")
        ai_provider = ref_settings.get("ai_provider", "openai")
        ai_model = ref_settings.get("ai_model", "gpt-4.1-mini")
        summary_style = ref_settings.get("summary_style", "concise")
        algorithm_type = ref_settings.get("algorithm_type", "textrank")
        max_length = ref_settings.get("max_length", 500)

        try:
            user_settings = (await self.db.execute(
                select(UserSettings).where(
                    UserSettings.user_id == self.user_id
                )
            )).scalar_one_or_none()
            if not user_settings:
                return [], None

            ref = CollectedReference(
                search_query=query, status="collecting"
            )
            self.db.add(ref)
            await self.db.flush()

            # 검색 (사용자 설정 수량)
            results = await ReferenceSearchService(
                user_settings
            ).search_webdoc(query, max_search)
            ref.total_searched = len(results)
            if not results:
                ref.status = "failed"
                ref.completed_at = datetime.now()
                await self.db.commit()
                return [], ref.id

            # 크롤링 (사용자 설정 목표)
            crawl_service = ReferenceCrawlingService(
                self.db, target_count=crawl_target
            )
            crawl = await crawl_service.crawl_documents(
                [r.link for r in results], ref.id
            )
            ref.total_crawled = crawl.total_success
            ref.total_failed = crawl.total_failed
            if not crawl.documents:
                ref.status = "failed"
                ref.completed_at = datetime.now()
                await self.db.commit()
                return [], ref.id

            # 요약 (사용자 설정)
            summary_service = ReferenceSummaryService(
                self.db,
                self.user_id,
                select_count=summary_count,
                summary_method=summary_method,
                ai_provider=ai_provider,
                ai_model=ai_model,
                summary_style=summary_style,
                algorithm_type=algorithm_type,
                max_length=max_length
            )
            summaries = await summary_service.summarize_documents(
                crawl.documents
            )
            ref.selected_references = [
                {
                    "url": s.url, "title": s.title,
                    "summary": s.summary,
                    "original_length": s.original_length,
                    "is_ai_summary": s.is_ai_summary
                }
                for s in summaries
            ]
            ref.status = "completed"
            ref.completed_at = datetime.now()
            await self.db.commit()
            return summaries, ref.id

        except Exception as e:
            logger.error(f"[CONTENT_GEN] 참조자료 수집 실패: {e}")
            return [], None

    def _build_generation_prompt(
        self,
        title: str,
        refs: List[DocumentSummary]
    ) -> str:
        """글 생성 프롬프트 구성"""
        base_prompt = "블로그 글을 작성해주세요."
        if not refs:
            return f"{base_prompt}\n\n제목: {title}"

        ref_texts = [
            f"참조 {i}:\n{r.summary}\n출처: {r.url}"
            for i, r in enumerate(refs, 1)
        ]
        return base_prompt + self.REFERENCE_TEMPLATE.format(
            references_text="\n\n".join(ref_texts), title=title
        )

    async def _call_ai(
        self, prompt: str, max_tokens: int = 2000
    ) -> Optional[str]:
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
                result = await self._anthropic(
                    key.api_key, prompt, max_tokens
                )
                if result:
                    await mgr.mark_key_used(key.id)
                    return result

            return None
        except Exception as e:
            logger.error(f"[CONTENT_GEN] AI 호출 실패: {e}")
            return None

    async def _openai(
        self, api_key: str, prompt: str, max_tokens: int
    ) -> Optional[str]:
        """OpenAI API 호출"""
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[CONTENT_GEN] OpenAI 실패: {e}")
            return None

    async def _anthropic(
        self, api_key: str, prompt: str, max_tokens: int
    ) -> Optional[str]:
        """Anthropic API 호출"""
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[CONTENT_GEN] Anthropic 실패: {e}")
            return None
