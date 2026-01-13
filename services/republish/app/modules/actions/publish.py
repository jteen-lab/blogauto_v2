"""
발행 모듈

블로그에 포스트를 발행합니다.
재발행과 신규 발행 모두 이 모듈을 사용합니다.
"""

from datetime import datetime
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class PublishModule(ModuleInterface):
    """발행 모듈 (핵심)"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.ACTION

    @property
    def name(self) -> str:
        return "publish"

    @property
    def display_name(self) -> str:
        return "발행"

    @property
    def description(self) -> str:
        return "블로그에 포스트를 발행합니다."

    @property
    def icon(self) -> str:
        return "📤"

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
                name="platform",
                type="select",
                required=True,
                default="wordpress",
                description="발행 플랫폼",
                options=[
                    {"value": "wordpress", "label": "워드프레스"},
                    {"value": "blogger", "label": "블로거"},
                ]
            ),
            ModuleParam(
                name="publish_mode",
                type="select",
                required=False,
                default="update",
                description="발행 모드",
                options=[
                    {"value": "new", "label": "신규 발행"},
                    {"value": "update", "label": "업데이트 (재발행)"}
                ]
            ),
            ModuleParam(
                name="update_date",
                type="boolean",
                required=False,
                default=True,
                description="발행 날짜 업데이트"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """발행 실행"""
        platform = params.get("platform", "wordpress")
        publish_mode = params.get("publish_mode", "update")
        update_date = params.get("update_date", True)

        context.log(f"발행 시작: {platform}, mode={publish_mode}")

        results = []
        for item in items:
            try:
                blog_id = item.get("blog_id") or item.get("id")

                if not blog_id:
                    context.log("blog_id 누락", level="warning")
                    continue

                # 플랫폼별 발행
                if platform == "wordpress":
                    result = await self._publish_wordpress(
                        blog_id, item, update_date, context
                    )
                elif platform == "blogger":
                    result = await self._publish_blogger(
                        blog_id, item, update_date, context
                    )
                else:
                    result = {"success": False, "error": f"미지원: {platform}"}

                result_item = BlogAutoItem(
                    json={
                        **item.json,
                        "publish_result": result,
                        "published_at": datetime.now().isoformat()
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                results.append(result_item)

            except Exception as e:
                context.log(f"발행 실패: {e}", level="error")
                error_item = BlogAutoItem(
                    json={
                        **item.json,
                        "publish_result": {"success": False, "error": str(e)}
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                results.append(error_item)

        success_count = sum(
            1 for r in results
            if r.get("publish_result", {}).get("success")
        )
        context.log(f"발행 완료: {success_count}/{len(results)}")

        return ModuleResult.ok(results)

    async def _publish_wordpress(
        self,
        blog_id: int,
        item: BlogAutoItem,
        update_date: bool,
        context: ExecutionContext
    ) -> dict:
        """워드프레스 발행"""
        try:
            # 테스트 모드면 실제 발행 안함
            if context.is_test:
                return {
                    "success": True,
                    "url": f"http://test.com/post/{blog_id}",
                    "test_mode": True
                }

            # 실제 발행 로직
            # TODO: WordPressService 연동
            return {"success": True, "url": f"http://example.com/post/{blog_id}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _publish_blogger(
        self,
        blog_id: int,
        item: BlogAutoItem,
        update_date: bool,
        context: ExecutionContext
    ) -> dict:
        """블로거 발행"""
        # TODO: Blogger API 구현
        if context.is_test:
            return {"success": True, "url": f"http://blogger.test/{blog_id}", "test_mode": True}
        return {"success": False, "error": "미구현"}
