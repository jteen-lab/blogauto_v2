"""
DB 저장 모듈

데이터를 데이터베이스에 저장합니다.
노드 체인에서 발행 결과를 autorun_logs에 저장하는 마지막 단계로 사용됩니다.
"""

from datetime import datetime
from typing import Any, Optional
from sqlalchemy import select
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class DBSaveModule(ModuleInterface):
    """DB 저장 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "db_save"

    @property
    def display_name(self) -> str:
        return "DB 저장"

    @property
    def description(self) -> str:
        return "데이터를 데이터베이스에 저장합니다."

    @property
    def icon(self) -> str:
        return "💾"

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
                description="저장할 테이블",
                options=[
                    {"value": "url_history", "label": "URL 히스토리"},
                    {"value": "autorun_logs", "label": "오토런 로그"},
                ]
            ),
            ModuleParam(
                name="mode",
                type="select",
                required=False,
                default="insert",
                description="저장 모드",
                options=[
                    {"value": "insert", "label": "새로 저장"},
                    {"value": "update", "label": "업데이트"},
                    {"value": "upsert", "label": "저장 또는 업데이트"}
                ]
            ),
            ModuleParam(
                name="key_field",
                type="string",
                required=False,
                default="id",
                description="업데이트 시 키 필드"
            ),
            ModuleParam(
                name="map_publish_result",
                type="boolean",
                required=False,
                default=True,
                description="Publish 결과를 autorun_logs 필드로 매핑"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """DB 저장 실행"""
        table = params.get("table")
        mode = params.get("mode", "insert")
        key_field = params.get("key_field", "id")
        map_publish = params.get("map_publish_result", True)

        context.log(f"[DB_SAVE] 시작 | table={table} | mode={mode} | items={len(items)}")

        try:
            # autorun_logs 특별 처리 (Publish 결과 매핑)
            if table == "autorun_logs" and map_publish:
                return await self._save_autorun_logs(context, items)

            model = self._get_model(table)
            if not model:
                return ModuleResult.fail(f"알 수 없는 테이블: {table}")

            saved_items = []
            for item in items:
                data = item.json.copy()

                if mode == "insert":
                    obj = model(**self._filter_model_fields(model, data))
                    context.db_session.add(obj)

                elif mode == "update":
                    key_value = data.get(key_field)
                    if not key_value:
                        continue
                    result = await context.db_session.execute(
                        select(model).where(getattr(model, key_field) == key_value)
                    )
                    obj = result.scalar_one_or_none()
                    if obj:
                        for k, v in self._filter_model_fields(model, data).items():
                            if k != key_field:
                                setattr(obj, k, v)

                elif mode == "upsert":
                    key_value = data.get(key_field)
                    obj = None
                    if key_value:
                        result = await context.db_session.execute(
                            select(model).where(getattr(model, key_field) == key_value)
                        )
                        obj = result.scalar_one_or_none()
                    if obj:
                        for k, v in self._filter_model_fields(model, data).items():
                            if k != key_field:
                                setattr(obj, k, v)
                    else:
                        obj = model(**self._filter_model_fields(model, data))
                        context.db_session.add(obj)

                saved_item = BlogAutoItem(
                    json={**item.json, "saved": True},
                    meta=ItemMeta(source_module=self.name)
                )
                saved_items.append(saved_item)

            await context.db_session.commit()
            context.log(f"[DB_SAVE] 완료 | {len(saved_items)}건")
            return ModuleResult.ok(saved_items)

        except Exception as e:
            await context.db_session.rollback()
            context.log(f"[DB_SAVE] 실패 | error={e}", level="error")
            return ModuleResult.fail(str(e))

    async def _save_autorun_logs(
        self,
        context: ExecutionContext,
        items: ItemList
    ) -> ModuleResult:
        """
        Publish 결과를 autorun_logs 테이블에 저장

        입력 (Publish 출력):
        - blog_id, blog_name, platform
        - post_id, post_title, post_url
        - publish_result: {success, message, ...}
        - published_at

        저장 필드:
        - flow_id, blog_id, blog_name
        - action_type, status, message
        - executed_at, post_id, post_url
        """
        from app.models.autorun_log import AutorunLog

        saved_items = []

        for item in items:
            data = item.json
            publish_result = data.get("publish_result", {})

            log_entry = AutorunLog(
                flow_id=context.flow_id,
                blog_id=data.get("blog_id"),
                blog_name=data.get("blog_name"),
                action_type="republish",
                status="success" if publish_result.get("success") else "failed",
                message=publish_result.get("message", ""),
                executed_at=datetime.now(),
                post_id=str(data.get("post_id", "")),
                post_url=data.get("post_url") or publish_result.get("url", "")
            )

            context.db_session.add(log_entry)

            saved_item = BlogAutoItem(
                json={**item.json, "saved": True, "log_id": None},
                meta=ItemMeta(source_module=self.name)
            )
            saved_items.append(saved_item)

        await context.db_session.commit()

        # 저장된 log_id 업데이트 (flush 후 id 접근)
        context.log(
            f"[DB_SAVE] autorun_logs 저장 완료 | flow_id={context.flow_id} | "
            f"{len(saved_items)}건"
        )
        return ModuleResult.ok(saved_items)

    def _get_model(self, table: str):
        """테이블명으로 모델 반환"""
        from app.models.url_history import URLHistory
        from app.models.autorun_log import AutorunLog

        models = {
            "url_history": URLHistory,
            "autorun_logs": AutorunLog,
        }
        return models.get(table)

    def _filter_model_fields(self, model, data: dict) -> dict:
        """모델에 존재하는 필드만 필터링"""
        if hasattr(model, "__table__"):
            valid_columns = {c.name for c in model.__table__.columns}
            return {k: v for k, v in data.items() if k in valid_columns}
        return data
