"""
키워드 로더 모듈

키워드 탭에서 키워드를 로드하거나, 키워드가 없으면 랜덤 수집 모드로 전환합니다.
수집 모듈의 첫 번째 데이터 노드로 사용됩니다.
"""

from typing import Any
from sqlalchemy import select, func
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class KeywordLoaderModule(ModuleInterface):
    """키워드 로더 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "keyword_loader"

    @property
    def display_name(self) -> str:
        return "키워드 로더"

    @property
    def description(self) -> str:
        return "키워드 탭에서 키워드를 로드합니다. 키워드가 없으면 랜덤 수집 모드로 전환합니다."

    @property
    def icon(self) -> str:
        return "🔑"

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
                name="limit",
                type="number",
                required=False,
                default=50,
                description="최대 키워드 수"
            ),
            ModuleParam(
                name="random_if_empty",
                type="boolean",
                required=False,
                default=True,
                description="키워드가 없으면 랜덤 수집 모드"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """키워드 로드 실행"""
        limit = params.get("limit", 50)
        random_if_empty = params.get("random_if_empty", True)

        context.log(f"[KEYWORD_LOADER] 시작 | limit={limit}")

        try:
            # 키워드 테이블에서 로드 시도
            keywords = await self._load_keywords(context, limit)

            if keywords:
                context.log(f"[KEYWORD_LOADER] 키워드 로드 완료 | {len(keywords)}개")
                output_items = []
                for kw in keywords:
                    item = BlogAutoItem(
                        json={
                            "keyword": kw.get("keyword", ""),
                            "weight": kw.get("weight", 1),
                            "category": kw.get("category", ""),
                            "use_random": False
                        },
                        meta=ItemMeta(source_module=self.name)
                    )
                    output_items.append(item)
                return ModuleResult.ok(output_items)

            # 키워드가 없으면 랜덤 모드
            if random_if_empty:
                context.log("[KEYWORD_LOADER] 키워드 없음 → 랜덤 수집 모드")
                random_item = BlogAutoItem(
                    json={
                        "use_random": True,
                        "message": "키워드 없음, 랜덤 수집 모드"
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                return ModuleResult.ok([random_item])

            context.log("[KEYWORD_LOADER] 키워드 없음, 랜덤 모드 비활성화")
            return ModuleResult.ok([])

        except Exception as e:
            context.log(f"[KEYWORD_LOADER] 실패 | error={e}", level="error")
            return ModuleResult.fail(str(e))

    async def _load_keywords(
        self,
        context: ExecutionContext,
        limit: int
    ) -> list[dict]:
        """키워드 테이블에서 로드 (정본 keyword_candidates)"""
        try:
            from app.models.keyword_candidate import KeywordCandidate

            query = (
                select(KeywordCandidate)
                .where(KeywordCandidate.is_active == True)
                .order_by(KeywordCandidate.priority.desc(), KeywordCandidate.use_count.asc())
                .limit(limit)
            )

            result = await context.db_session.execute(query)
            rows = result.scalars().all()

            return [
                {
                    "keyword": row.keyword,
                    "weight": row.priority,
                    "category": ""
                }
                for row in rows
            ]

        except Exception as e:
            # KeywordCandidate 테이블이 없거나 에러 시 빈 목록 반환
            context.log(f"[KEYWORD_LOADER] 키워드 테이블 조회 실패: {e}")
            return []
