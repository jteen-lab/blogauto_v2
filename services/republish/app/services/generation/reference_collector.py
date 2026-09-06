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
    # 여러 문서를 한 번에 정리한 글(④ 통합 요약). 있으면 이걸 쓴다.
    digest: str = ""
    # 공식 API 에서 얻은 값(③ 1차 출처). 웹문서보다 **앞에** 놓는다.
    official: str = ""
    # 관문·소스 통과 현황. 0건일 때 어디서 막혔는지 화면이 말해야 한다.
    trace: dict = field(default_factory=dict)

    def to_prompt_injection(self) -> str:
        """프롬프트에 주입할 형태로 변환.

        딱지(무엇을 하라는 말)를 함께 준다. 예전에는 자료만 던져,
        AI 가 참고할지 베낄지 출처를 출력할지 스스로 정했다.
        """
        blocks: List[str] = []
        if self.official:
            blocks.append(self.official)

        if self.digest:
            from ..reference.digest import to_prompt_injection as _inject

            blocks.append(_inject(self.digest, self.sources))
        elif self.summaries:
            parts = [f"참조 {i}:\n{s.summary}"
                     for i, s in enumerate(self.summaries, 1)]
            blocks.append(
                "[참고 자료]\n"
                "아래는 이 제목으로 검색해 모은 자료입니다. 사실·수치·최신 "
                "정보는 여기서 가져오되 문장을 그대로 옮기지 마세요.\n"
                "여기에 없는 수치를 지어내지 말고, 출처 URL 은 본문에 쓰지 "
                "마세요.\n\n" + "\n\n".join(parts))

        return "\n\n".join(b for b in blocks if b)


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
        self._ai_service = None

    @property
    def ai_service(self):
        """통합 요약이 쓰는 AI. 필요할 때 만든다 — 참조 수집을 끈
        모듈에서 쓸데없이 초기화하지 않는다."""
        if self._ai_service is None:
            from ..ai.ai_service import AIService

            self._ai_service = AIService(self.db)
        return self._ai_service

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

        # ① 질의 재작성 — 제목 문장을 그대로 넣지 않는다.
        #    예전에는 실패하면 search_query[:20] 으로 잘라 재시도했다.
        #    낱말 중간에서 끊겨 엉뚱한 검색어가 됐다.
        from ..reference.query_builder import build as build_plan

        plan = build_plan(search_query)
        logger.info("[REF_COLLECT] 질의 계획 | %s | 개체=%s",
                    plan.queries(), plan.entities)

        last_error = ""
        for attempt, query in enumerate(plan.queries(), 1):
            try:
                result = await self._execute_collection(
                    query, settings, user_settings, ref,
                    entities=plan.entities, title=search_query,
                )
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
                logger.warning("[REF_COLLECT] %d차 실패 | '%s' | %s",
                               attempt, query, e)
                continue
            if result.count > 0:
                if attempt > 1:
                    logger.info("[REF_COLLECT] %d차 질의로 성공 | '%s'",
                                attempt, query)
                return result

        logger.warning("[REF_COLLECT] 모든 질의 실패 | title='%s' | %s",
                       search_query[:40], last_error)
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
        entities: Optional[List[str]] = None,
        title: str = "",
    ) -> ReferenceCollectionResult:
        """수집 파이프라인 실행.

        Args:
            query: 재작성된 검색 질의
            entities: 제목 개체 — 관련성 관문이 쓴다
            title: 원본 제목 — 통합 요약이 쓴다(질의가 아니라 제목을 묻는다)
        """
        from ..reference import relevance
        max_search = settings.get("max_search", 30)
        crawl_target = settings.get("crawl_target", 10)
        summary_count = settings.get("summary_count", 3)
        summary_method = settings.get("summary_method", "ai")
        ai_provider = settings.get("ai_provider", "openai")
        ai_model = settings.get("ai_model", "gpt-4o-mini")
        summary_style = settings.get("summary_style", "concise")
        algorithm_type = settings.get("algorithm_type", "textrank")
        max_length = settings.get("max_length", 500)

        entities = list(entities or [])
        trace: dict = {}

        # 검색
        search_results = await ReferenceSearchService(
            user_settings
        ).search_webdoc(query, max_search)
        ref.total_searched = len(search_results)

        # ② 관문 1 — 제목·설명에 개체가 없는 결과를 뺀다(크롤링 전이라 공짜)
        before = len(search_results)
        search_results = relevance.filter_search_results(
            search_results, entities)
        # ⑤ 최신성 — 새 문서를 앞으로. 금리·제도는 오래된 값이 틀린 값이다
        search_results = relevance.sort_by_freshness(search_results)
        trace["gate1"] = relevance.report(before, len(search_results), "관문1")

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

        # ② 관문 2 — 본문에 개체가 없는 문서를 뺀다
        docs_before = len(crawl_result.documents)
        documents = relevance.filter_documents(
            crawl_result.documents, entities)
        trace["gate2"] = relevance.report(docs_before, len(documents), "관문2")

        if not documents:
            ref.status = "failed"
            ref.completed_at = datetime.now()
            await self.db.commit()
            return ReferenceCollectionResult(count=0, reference_id=ref.id)

        # ④ 통합 요약 — 제목과 함께 한 번에 읽는다. 문서별로 따로 물으면
        #    문서의 주된 내용이 요약되고 우리가 필요한 부분은 빠진다.
        #    (AI 호출도 3회 → 1회로 준다)
        picked = documents[:max(1, summary_count)]
        digest_text, digest_sources = "", []
        if summary_method == "ai":
            from ..reference.digest import summarize as digest_summarize

            digest = await digest_summarize(
                self.ai_service, title or query, picked,
                ai_provider, ai_model, max_length=max(600, max_length))
            digest_text = digest.get("text") or ""
            digest_sources = digest.get("sources") or []
            trace["digest"] = {"used": digest.get("used"),
                               "no_match": digest.get("no_match")}

        # 정리에 실패했거나 규칙 요약을 쓰는 모듈은 예전 경로로 간다
        summaries = []
        if not digest_text:
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
            summaries = await summary_service.summarize_documents(picked)
            # ② 관문 3 — "관련 없음" 이라 답한 요약을 뺀다
            sum_before = len(summaries)
            summaries = relevance.filter_summaries(summaries)
            trace["gate3"] = relevance.report(
                sum_before, len(summaries), "관문3")

        # ③ 1차 출처 — 등록된 공식 API 에서 값을 받아 온다(있으면)
        official = await self._official_facts(title or query, query, entities)
        if official:
            trace["official"] = True

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

        count = (1 if digest_text else 0) + len(summaries) + (
            1 if official else 0)
        logger.info(
            "[REF_COLLECT] 완료 | 검색=%s | 크롤링=%s | 정리=%s | 요약=%s "
            "| 공식=%s | 관문=%s",
            ref.total_searched, ref.total_crawled, bool(digest_text),
            len(summaries), bool(official), trace,
        )

        return ReferenceCollectionResult(
            count=count,
            summaries=summaries,
            sources=digest_sources or [s.url for s in summaries],
            reference_id=ref.id,
            digest=digest_text,
            official=official,
            trace=trace,
        )

    async def _official_facts(self, title: str, query: str,
                              entities: List[str]) -> str:
        """③ 등록된 공식 API 중 이 주제에 맞는 것을 부른다.

        등록이 없으면 빈 문자열이다 — 이 단계는 있으면 좋고 없어도 된다.
        """
        try:
            from ..reference.sources.registry import gather

            topics = await self._topics_of(title)
            found = await gather(self.db, title, topics, query, entities)
            return found.get("prompt") or ""
        except Exception as e:  # noqa: BLE001 — 소스 실패로 글을 막지 않는다
            logger.warning(f"[REF_COLLECT] 공식 자료 조회 실패: {e}")
            return ""

    async def _topics_of(self, title: str) -> List[str]:
        """이 제목이 속한 주제·하위주제 이름.

        정식제목에 분류가 붙어 있으면 그것을 쓴다. 없으면 빈 목록이라
        `match_keywords` 만으로 소스를 고른다.
        """
        from sqlalchemy import select as _select

        from ...models.category import SubTopic, Topic
        from ...models.title import MainTitle

        row = (await self.db.execute(
            _select(Topic.name, SubTopic.name)
            .select_from(MainTitle)
            .outerjoin(Topic, Topic.id == MainTitle.topic_id)
            .outerjoin(SubTopic, SubTopic.id == MainTitle.subtopic_id)
            .where(MainTitle.title == title).limit(1)
        )).first()
        return [name for name in (row or ()) if name]

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
