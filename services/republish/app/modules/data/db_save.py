"""
DB 저장 모듈

데이터를 데이터베이스에 저장합니다.
"""

from typing import Any
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

        context.log(f"DB 저장: {table}, mode={mode}, items={len(items)}")

        try:
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
            context.log(f"DB 저장 완료: {len(saved_items)}건")
            return ModuleResult.ok(saved_items)

        except Exception as e:
            await context.db_session.rollback()
            context.log(f"DB 저장 실패: {e}", level="error")
            return ModuleResult.fail(str(e))

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
