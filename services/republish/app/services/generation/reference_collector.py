"""
참조자료 수집 통합 서비스 (파사드)

기존 ReferenceSearchService, ReferenceCrawlingService, ReferenceSummaryService를
통합 조율하는 파사드 서비스입니다.

설계 문서: generation_module_workplan.md - Phase 2 - 2.2.2
"""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..reference_search_service import ReferenceSearchService
from ..reference_crawling_service import ReferenceCrawlingService
from ..reference_summary_service import ReferenceSummaryService
from ...models.user_settings import UserSettings
from ...models.module import Module
from ...models.collected_reference import CollectedReference
from ...schemas.reference_collection import DocumentSummary

logger = logging.getLogger(__name__)


@dataclass
class ReferenceCollectionResult:
    """참조자료 수집 결과"""
    count: int
    summaries: List[DocumentSummary] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    reference_id: Optional[int] = None

    def to_prompt_injection(self) -> str:
        """프롬프트에 주입할 형태로 변환"""
        if not self.summaries:
            return ""

        parts = []
        for i, summary in enumerate(self.summaries, 1):
            parts.append(
                f"참조 {i}:\n{summary.summary}\n출처: {summary.url}"
            )

        return (
            "[참조자료]\n"
            + "\n\n".join(parts)
            + "\n\n[출처]\n"
            + "\n".join(f"- {url}" for url in self.sources)
        )


class ReferenceCollector:
    """
    참조자료 수집 통합 서비스

    워크플로우:
    1. 검색어로 네이버 웹문서 검색
    2. 검색 결과 URL 크롤링
    3. AI 또는 알고리즘으로 요약
    4. 프롬프트 주입용 형태로 반환
    """

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id

    async def collect_and_summarize(
        self,
        search_query: str,
        module_id: Optional[int] = None,
        ref_settings: Optional[dict] = None,
    ) -> ReferenceCollectionResult:
        """
        참조자료 수집 및 요약 실행

        Args:
            search_query: 검색어 (재조합된 제목)
            module_id: 모듈 ID (설정 로드용, ref_settings와 택일)
            ref_settings: 직접 전달하는 참조자료 설정

        Returns:
            ReferenceCollectionResult: 수집 결과
        """
        logger.info(
            f"[REF_COLLECT] 시작 | query='{search_query[:30]}...' "
            f"| module_id={module_id}"
        )

        # 1. 설정 로드
        settings = await self._resolve_settings(module_id, ref_settings)

        # 2. 사용자 설정 확인 (네이버 API 키)
        user_settings = await self._get_user_settings()
        if not user_settings:
            logger.warning("[REF_COLLECT] 사용자 설정 없음")
            return ReferenceCollectionResult(count=0)

        # 3. 수집 레코드 생성
        ref = CollectedReference(
            search_query=search_query, status="collecting"
        )
        self.db.add(ref)
        await self.db.flush()

        try:
            return await self._execute_collection(
                search_query, settings, user_settings, ref
            )
        except Exception as e:
            logger.warning(
                f"[REF_COLLECT] 첫 수집 실패, "
                f"단순화 검색어로 재시도: {e}"
            )
            try:
                simple_query = search_query[:20].strip()
                retry_result = await self._execute_collection(
                    simple_query, settings, user_settings, ref
                )
                if retry_result.count > 0:
                    logger.info(
                        f"[REF_COLLECT] 재시도 성공 | "
                        f"count={retry_result.count}"
                    )
                    return retry_result
            except Exception as retry_e:
                logger.error(
                    f"[REF_COLLECT] 재시도도 실패: {retry_e}"
                )

            ref.status = "failed"
            ref.completed_at = datetime.now()
            await self.db.commit()
            return ReferenceCollectionResult(count=0, reference_id=ref.id)

    async def _execute_collection(
        self,
        query: str,
        settings: dict,
        user_settings: UserSettings,
        ref: CollectedReference,
    ) -> ReferenceCollectionResult:
        """수집 파이프라인 실행"""
        max_search = settings.get("max_search", 30)
        crawl_target = settings.get("crawl_target", 10)
        summary_count = settings.get("summary_count", 3)
        summary_method = settings.get("summary_method", "ai")
        ai_provider = settings.get("ai_provider", "openai")
        ai_model = settings.get("ai_model", "gpt-4o-mini")
        summary_style = settings.get("summary_style", "concise")
        algorithm_type = settings.get("algorithm_type", "textrank")
        max_length = settings.get("max_length", 500)

        # 검색
        search_results = await ReferenceSearchService(
            user_settings
        ).search_webdoc(query, max_search)
        ref.total_searched = len(search_results)

        if not search_results:
            ref.status = "failed"
            ref.completed_at = datetime.now()
            await self.db.commit()
            return ReferenceCollectionResult(count=0, reference_id=ref.id)

        # 크롤링
        crawl_service = ReferenceCrawlingService(
            self.db, target_count=crawl_target
        )
        crawl_result = await crawl_service.crawl_documents(
            [r.link for r in search_results], ref.id
        )
        ref.total_crawled = crawl_result.total_success
        ref.total_failed = crawl_result.total_failed

        if not crawl_result.documents:
            ref.status = "failed"
            ref.completed_at = datetime.now()
            await self.db.commit()
            return ReferenceCollectionResult(count=0, reference_id=ref.id)

        # 요약
        summary_service = ReferenceSummaryService(
            self.db,
            self.user_id,
            select_count=summary_count,
            summary_method=summary_method,
            ai_provider=ai_provider,
            ai_model=ai_model,
            summary_style=summary_style,
            algorithm_type=algorithm_type,
            max_length=max_length,
        )
        summaries = await summary_service.summarize_documents(
            crawl_result.documents
        )

        # 결과 저장
        ref.selected_references = [
            {
                "url": s.url,
                "title": s.title,
                "summary": s.summary,
                "original_length": s.original_length,
                "is_ai_summary": s.is_ai_summary,
            }
            for s in summaries
        ]
        ref.status = "completed"
        ref.completed_at = datetime.now()
        await self.db.commit()

        logger.info(
            f"[REF_COLLECT] 완료 | 검색={ref.total_searched} "
            f"| 크롤링={ref.total_crawled} | 요약={len(summaries)}"
        )

        return ReferenceCollectionResult(
            count=len(summaries),
            summaries=summaries,
            sources=[s.url for s in summaries],
            reference_id=ref.id,
        )

    async def _resolve_settings(
        self,
        module_id: Optional[int],
        ref_settings: Optional[dict],
    ) -> dict:
        """참조자료 설정 해석"""
        if ref_settings:
            return ref_settings

        if module_id:
            module = await self.db.get(Module, module_id)
            if module and module.settings:
                settings = module.settings

                # 새 형식 우선 (settings.reference 구조 - 프롬프트 모듈)
                if "reference" in settings:
                    ref = settings["reference"]
                    return {**ref, "enabled": True}

                # 구 형식 호환 (enable_reference_collection 플래그)
                if not settings.get("enable_reference_collection", False):
                    return {"enabled": False}

                return {
                    "enabled": True,
                    "max_search": 30,
                    "crawl_target": 10,
                    "summary_count": settings.get("reference_count", 3),
                    "summary_method": "ai",
                    "ai_provider": "openai",
                    "ai_model": "gpt-4o-mini",
                    "summary_style": "concise",
                    "algorithm_type": "textrank",
                    "max_length": 500,
                }

        # 기본 설정
        return {
            "enabled": True,
            "max_search": 30,
            "crawl_target": 10,
            "summary_count": 3,
            "summary_method": "ai",
            "ai_provider": "openai",
            "ai_model": "gpt-4o-mini",
            "summary_style": "concise",
            "algorithm_type": "textrank",
            "max_length": 500,
        }

    async def _get_user_settings(self) -> Optional[UserSettings]:
        """사용자 설정 조회"""
        result = await self.db.execute(
            select(UserSettings).where(
                UserSettings.user_id == self.user_id
            )
        )
        return result.scalar_one_or_none()
