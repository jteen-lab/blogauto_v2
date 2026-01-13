"""
수동 트리거 모듈

수동으로 플로우를 시작합니다. (1회 실행용)
"""

from datetime import datetime
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class ManualTriggerModule(ModuleInterface):
    """수동 트리거"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.TRIGGER

    @property
    def name(self) -> str:
        return "manual_trigger"

    @property
    def display_name(self) -> str:
        return "수동 트리거"

    @property
    def description(self) -> str:
        return "수동으로 플로우를 시작합니다."

    @property
    def icon(self) -> str:
        return "👆"

    @property
    def inputs(self) -> list[PortType]:
        return []  # 트리거는 입력 없음

    @property
    def outputs(self) -> list[PortType]:
        return [PortType.MAIN]

    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="input_data",
                type="json",
                required=False,
                default={},
                description="초기 입력 데이터"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """트리거 실행"""
        input_data = params.get("input_data", {})

        trigger_item = BlogAutoItem(
            json={
                "trigger_type": "manual",
                "triggered_at": datetime.now().isoformat(),
                "is_test": context.is_test,
                **input_data
            },
            meta=ItemMeta(source_module=self.name)
        )

        context.log("수동 트리거 실행")
        return ModuleResult.ok([trigger_item])
