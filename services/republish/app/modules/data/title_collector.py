"""
제목 수집 모듈

네이버 뉴스, 구글 뉴스, 네이버 웹문서에서 제목을 수집합니다.
키워드 로더의 출력을 받아 키워드 기반 또는 랜덤 수집을 수행합니다.
"""

from typing import Any, List
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class TitleCollectorModule(ModuleInterface):
    """제목 수집 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "title_collector"

    @property
    def display_name(self) -> str:
        return "제목 수집기"

    @property
    def description(self) -> str:
        return "네이버/구글 뉴스, 웹문서에서 제목을 수집합니다."

    @property
    def icon(self) -> str:
        return "📰"

    @property
    def inputs(self) -> list[PortType]:
        return [PortType.MAIN]

    @property
    def outputs(self) -> list[PortType]:
        return [PortType.MAIN]

    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="sources",
                type="json",
                required=False,
                default=["naver_news", "google_news", "naver_webdoc"],
                description="수집 소스 목록"
            ),
            ModuleParam(
                name="limit_per_source",
                type="number",
                required=False,
                default=100,
                description="소스당 최대 수집 개수"
            ),
            ModuleParam(
                name="delay_between_requests",
                type="number",
                required=False,
                default=0.5,
                description="요청 간 딜레이 (초)"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """제목 수집 실행"""
        sources = params.get("sources", ["naver_news", "google_news", "naver_webdoc"])
        limit_per_source = params.get("limit_per_source", 100)
        delay = params.get("delay_between_requests", 0.5)

        context.log(
            f"[TITLE_COLLECTOR] 시작 | sources={sources} | "
            f"limit={limit_per_source}"
        )

        try:
            # 입력에서 랜덤 모드 여부 확인
            use_random = False
            keywords = []

            for item in items:
                data = item.json
                if data.get("use_random"):
                    use_random = True
                    break
                if data.get("keyword"):
                    keywords.append(data.get("keyword"))

            # UserSettings 로드
            settings = await self._get_user_settings(context)
            if not settings:
                return ModuleResult.fail("사용자 설정을 찾을 수 없습니다")

            all_titles = []

            # 각 소스에서 수집
            for source in sources:
                try:
                    titles = await self._collect_from_source(
                        context, settings, source,
                        keywords, use_random, limit_per_source, delay
                    )
                    all_titles.extend(titles)
                    context.log(
                        f"[TITLE_COLLECTOR] {source} 수집 완료 | {len(titles)}개"
                    )
                except Exception as e:
                    context.log(
                        f"[TITLE_COLLECTOR] {source} 수집 실패 | {e}",
                        level="warning"
                    )

            # 결과를 아이템으로 변환
            output_items = []
            for title_data in all_titles:
                item = BlogAutoItem(
                    json=title_data,
                    meta=ItemMeta(source_module=self.name)
                )
                output_items.append(item)

            context.log(f"[TITLE_COLLECTOR] 완료 | 총 {len(output_items)}개 수집")
            return ModuleResult.ok(output_items)

        except Exception as e:
            context.log(f"[TITLE_COLLECTOR] 실패 | error={e}", level="error")
            return ModuleResult.fail(str(e))

    async def _get_user_settings(self, context: ExecutionContext):
        """사용자 설정 로드"""
        try:
            from sqlalchemy import select
            from app.models.user_settings import UserSettings
            from app.models.flow import Flow

            # Flow에서 user_id 가져오기
            result = await context.db_session.execute(
                select(Flow).where(Flow.id == context.flow_id)
            )
            flow = result.scalar_one_or_none()
            if not flow:
                return None

            # UserSettings 조회
            result = await context.db_session.execute(
                select(UserSettings).where(UserSettings.user_id == flow.user_id)
            )
            return result.scalar_one_or_none()

        except Exception as e:
            context.log(f"[TITLE_COLLECTOR] 설정 로드 실패: {e}", level="error")
            return None

    async def _collect_from_source(
        self,
        context: ExecutionContext,
        settings,
        source: str,
        keywords: List[str],
        use_random: bool,
        limit: int,
        delay: float
    ) -> List[dict]:
        """소스별 수집 실행"""
        titles = []

        if source == "naver_news":
            titles = await self._collect_naver_news(
                settings, keywords, use_random, limit, delay
            )
        elif source == "google_news":
            titles = await self._collect_google_news(
                settings, keywords, use_random, limit, delay
            )
        elif source == "naver_webdoc":
            titles = await self._collect_naver_webdoc(
                settings, keywords, use_random, limit, delay
            )

        return titles

    async def _collect_naver_news(
        self, settings, keywords, use_random, limit, delay
    ) -> List[dict]:
        """네이버 뉴스 수집"""
        try:
            from app.services.naver_news_service import NaverNewsService

            service = NaverNewsService(settings)
            if not service.is_configured():
                return []

            if use_random or not keywords:
                result = await service.collect_news_titles(
                    limit=limit,
                    delay_between_queries=delay,
                    use_random=True
                )
            else:
                # 키워드 기반 수집 (첫 번째 키워드로)
                result = await service.search_news(
                    query=keywords[0] if keywords else "정보",
                    display=min(limit, 100)
                )
                if result.get("success"):
                    return [
                        {
                            "title": self._clean_title(item.get("title", "")),
                            "source": "naver_news",
                            "keyword": keywords[0] if keywords else "",
                            "link": item.get("link", "")
                        }
                        for item in result.get("items", [])
                        if len(self._clean_title(item.get("title", ""))) >= 10
                    ][:limit]
                return []

            return result.get("titles", [])

        except Exception as e:
            return []

    async def _collect_google_news(
        self, settings, keywords, use_random, limit, delay
    ) -> List[dict]:
        """구글 뉴스 수집"""
        try:
            from app.services.google_news_rss_service import GoogleNewsRSSService

            service = GoogleNewsRSSService()

            if use_random or not keywords:
                result = await service.collect_news_titles(
                    limit=limit,
                    delay_between_queries=delay,
                    use_random=True
                )
            else:
                result = await service.collect_from_search(
                    query=keywords[0] if keywords else "정보",
                    limit=limit,
                    use_random=False
                )

            return result.get("titles", [])

        except Exception as e:
            return []

    async def _collect_naver_webdoc(
        self, settings, keywords, use_random, limit, delay
    ) -> List[dict]:
        """네이버 웹문서 수집"""
        try:
            from app.services.naver_webdoc_service import NaverWebdocService

            service = NaverWebdocService(settings)
            if not service.is_configured():
                return []

            if use_random or not keywords:
                result = await service.collect_webdoc_titles(
                    limit=limit,
                    delay_between_queries=delay,
                    use_random=True
                )
            else:
                result = await service.search_by_keyword(
                    keyword=keywords[0] if keywords else "정보",
                    limit=limit,
                    delay_between_requests=delay
                )

            return result.get("titles", [])

        except Exception as e:
            return []

    def _clean_title(self, title: str) -> str:
        """HTML 태그 제거"""
        import re
        title = re.sub(r'<[^>]+>', '', title)
        title = title.replace("&quot;", '"')
        title = title.replace("&amp;", "&")
        title = title.replace("&lt;", "<")
        title = title.replace("&gt;", ">")
        title = title.replace("&apos;", "'")
        title = re.sub(r'\s+', ' ', title)
        return title.strip()
