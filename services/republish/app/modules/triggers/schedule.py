"""
스케줄 트리거 모듈

지정된 시간에 플로우를 시작합니다.
"""

from datetime import datetime
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class ScheduleTriggerModule(ModuleInterface):
    """스케줄 트리거"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.TRIGGER

    @property
    def name(self) -> str:
        return "schedule_trigger"

    @property
    def display_name(self) -> str:
        return "스케줄 트리거"

    @property
    def description(self) -> str:
        return "지정된 시간에 플로우를 시작합니다."

    @property
    def icon(self) -> str:
        return "⏰"

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
                name="cron",
                type="string",
                required=False,
                default="0 9 * * *",
                description="Cron 표현식"
            ),
            ModuleParam(
                name="timezone",
                type="string",
                required=False,
                default="Asia/Seoul",
                description="시간대"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """트리거 실행"""
        trigger_item = BlogAutoItem(
            json={
                "trigger_type": "schedule",
                "triggered_at": datetime.now().isoformat(),
                "cron": params.get("cron", "0 9 * * *"),
                "timezone": params.get("timezone", "Asia/Seoul"),
                "is_test": context.is_test
            },
            meta=ItemMeta(source_module=self.name)
        )

        context.log("스케줄 트리거 실행")
        return ModuleResult.ok([trigger_item])
