"""
DB 조회 모듈

데이터베이스에서 데이터를 조회합니다.
노드 체인에서 블로그 목록 조회의 첫 번째 단계로 사용됩니다.
"""

from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class DBQueryModule(ModuleInterface):
    """DB 조회 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "db_query"

    @property
    def display_name(self) -> str:
        return "DB 조회"

    @property
    def description(self) -> str:
        return "데이터베이스에서 데이터를 조회합니다."

    @property
    def icon(self) -> str:
        return "🗄️"

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
                name="table",
                type="select",
                required=True,
                description="조회할 테이블",
                options=[
                    {"value": "blogs", "label": "블로그"},
                    {"value": "url_history", "label": "URL 히스토리"},
                    {"value": "autorun_logs", "label": "오토런 로그"},
                    {"value": "flow_blogs", "label": "플로우-블로그 연결"},
                ]
            ),
            ModuleParam(
                name="filter",
                type="json",
                required=False,
                default={},
                description="필터 조건"
            ),
            ModuleParam(
                name="limit",
                type="number",
                required=False,
                default=100,
                description="최대 조회 개수"
            ),
            ModuleParam(
                name="order_by",
                type="string",
                required=False,
                default="id",
                description="정렬 기준"
            ),
            ModuleParam(
                name="order_desc",
                type="boolean",
                required=False,
                default=False,
                description="내림차순"
            ),
            ModuleParam(
                name="use_flow_id",
                type="boolean",
                required=False,
                default=True,
                description="context.flow_id로 필터링 (flow_blogs 전용)"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """DB 조회 실행"""
        table = params.get("table")
        filter_cond = params.get("filter", {})
        limit = params.get("limit", 100)
        use_flow_id = params.get("use_flow_id", True)

        context.log(f"[DB_QUERY] 시작 | table={table} | limit={limit}")

        try:
            # flow_blogs 테이블은 특별 처리 (Blog 정보 포함)
            if table == "flow_blogs":
                return await self._query_flow_blogs(
                    context, filter_cond, limit, use_flow_id
                )

            # 일반 테이블 조회
            model = self._get_model(table)
            if not model:
                return ModuleResult.fail(f"알 수 없는 테이블: {table}")

            query = select(model)

            # 필터 적용
            for key, value in filter_cond.items():
                if hasattr(model, key):
                    query = query.where(getattr(model, key) == value)

            # 정렬 및 제한
            order_by = params.get("order_by", "id")
            order_desc = params.get("order_desc", False)
            if hasattr(model, order_by):
                col = getattr(model, order_by)
                query = query.order_by(col.desc() if order_desc else col)

            query = query.limit(limit)

            result = await context.db_session.execute(query)
            rows = result.scalars().all()

            # 아이템 변환
            output_items = []
            for row in rows:
                item = BlogAutoItem(
                    json=self._row_to_dict(row),
                    meta=ItemMeta(source_module=self.name)
                )
                output_items.append(item)

            context.log(f"[DB_QUERY] 완료 | {len(output_items)}건")
            return ModuleResult.ok(output_items)

        except Exception as e:
            context.log(f"[DB_QUERY] 실패 | error={e}", level="error")
            return ModuleResult.fail(str(e))

    async def _query_flow_blogs(
        self,
        context: ExecutionContext,
        filter_cond: dict,
        limit: int,
        use_flow_id: bool
    ) -> ModuleResult:
        """
        Flow에 연결된 블로그 목록 조회 (Blog 정보 포함)

        출력 형식:
        - blog_id: 블로그 ID
        - blog_name: 블로그 이름
        - blog_url: 블로그 URL
        - platform: 플랫폼 (wordpress/blogger)
        - is_active: 활성화 상태
        """
        from app.models.flow_blog import FlowBlog
        from app.models.blog import Blog

        query = (
            select(FlowBlog)
            .options(
                selectinload(FlowBlog.blog)
                .selectinload(Blog.google_credential)
            )
        )

        # flow_id 필터링
        if use_flow_id and context.flow_id:
            query = query.where(FlowBlog.flow_id == context.flow_id)
        elif "flow_id" in filter_cond:
            query = query.where(FlowBlog.flow_id == filter_cond["flow_id"])

        # is_active 필터링
        if "is_active" in filter_cond:
            query = query.where(FlowBlog.is_active == filter_cond["is_active"])

        query = query.limit(limit)

        result = await context.db_session.execute(query)
        flow_blogs = result.scalars().all()

        # Blog 정보를 포함한 아이템 생성
        output_items = []
        for fb in flow_blogs:
            if fb.blog:
                item = BlogAutoItem(
                    json={
                        "flow_blog_id": fb.id,
                        "blog_id": fb.blog.id,
                        "blog_name": fb.blog.name,
                        "blog_url": fb.blog.url,
                        "platform": fb.blog.platform.value,
                        "is_active": fb.is_active,
                        "flow_id": fb.flow_id
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                output_items.append(item)

        context.log(
            f"[DB_QUERY] flow_blogs 조회 완료 | flow_id={context.flow_id} | "
            f"블로그 {len(output_items)}개"
        )
        return ModuleResult.ok(output_items)

    def _get_model(self, table: str):
        """테이블명으로 모델 반환"""
        from app.models.blog import Blog
        from app.models.url_history import URLHistory
        from app.models.autorun_log import AutorunLog
        from app.models.flow_blog import FlowBlog

        models = {
            "blogs": Blog,
            "url_history": URLHistory,
            "autorun_logs": AutorunLog,
            "flow_blogs": FlowBlog,
        }
        return models.get(table)

    def _row_to_dict(self, row) -> dict:
        """ORM 객체를 딕셔너리로"""
        if hasattr(row, "__table__"):
            result = {}
            for c in row.__table__.columns:
                value = getattr(row, c.name)
                # datetime 직렬화
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                result[c.name] = value
            return result
        return {}
