"""
발행 모듈 (순수화)

블로그에 포스트를 발행합니다.
노드 체인에서 PostSelector에서 전달받은 포스트 정보를 사용하여 발행합니다.

입력: PostSelector에서 전달받은 포스트 정보
      {blog_id, blog_name, platform, post_id, post_title, ...}
출력: 발행 결과
      {blog_id, blog_name, platform, post_id, publish_result, published_at}
"""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta
from app.models.blog import Blog, BlogPlatform
from app.services.wordpress_service import WordPressRepublishService
from app.services.blogger_service import BloggerRepublishService


class PublishModule(ModuleInterface):
    """발행 모듈 (순수 발행만)"""

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
                name="publish_mode",
                type="select",
                required=False,
                default="republish",
                description="발행 모드",
                options=[
                    {"value": "republish", "label": "재발행 (날짜 업데이트)"},
                    {"value": "new", "label": "신규 발행"}
                ]
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """
        발행/재발행 실행 (순수 발행만)

        입력: PostSelector에서 전달받은 포스트 정보
        처리: WordPress/Blogger API 호출
        출력: 발행 결과
        """
        publish_mode = params.get("publish_mode", "republish")

        context.log(
            f"[PUBLISH] 시작 | flow_id={context.flow_id} | "
            f"mode={publish_mode} | input_items={len(items)}"
        )

        if not items:
            context.log("[PUBLISH] 입력 아이템이 없습니다", level="warning")
            return ModuleResult.ok([])

        results = []

        for item in items:
            result = await self._process_item(item, context)
            if result:
                results.append(result)

        # 결과 집계
        success_count = sum(
            1 for r in results
            if r.json.get("publish_result", {}).get("success")
        )
        context.log(
            f"[PUBLISH] 완료 | 성공: {success_count}/{len(results)}"
        )

        return ModuleResult.ok(results)

    async def _process_item(
        self,
        item: BlogAutoItem,
        context: ExecutionContext
    ) -> Optional[BlogAutoItem]:
        """입력 아이템(PostSelector 결과) 처리"""
        data = item.json
        blog_id = data.get("blog_id")
        post_id = data.get("post_id")
        platform = data.get("platform")
        blog_name = data.get("blog_name")

        if not blog_id:
            context.log(
                f"[PUBLISH] blog_id 누락 | data={data}",
                level="warning"
            )
            return None

        if not post_id:
            context.log(
                f"[PUBLISH] post_id 누락 | blog_id={blog_id}",
                level="warning"
            )
            return None

        try:
            # 블로그 조회 (API 호출을 위한 credential 필요)
            blog = await self._get_blog(context, blog_id)
            if not blog:
                return self._create_error_result(
                    blog_id, blog_name, platform,
                    "블로그를 찾을 수 없습니다"
                )

            # 포스트 재발행
            result = await self._republish_post(blog, post_id, context)

            return BlogAutoItem(
                json={
                    "blog_id": blog.id,
                    "blog_name": blog.name,
                    "platform": blog.platform.value,
                    "post_id": post_id,
                    "post_title": data.get("post_title"),
                    "post_url": data.get("post_url"),
                    "publish_result": result,
                    "published_at": datetime.now().isoformat()
                },
                meta=ItemMeta(source_module=self.name)
            )

        except Exception as e:
            context.log(
                f"[PUBLISH] 처리 오류 | blog_id={blog_id} | error={e}",
                level="error"
            )
            return self._create_error_result(
                blog_id, blog_name, platform, str(e)
            )

    async def _get_blog(
        self,
        context: ExecutionContext,
        blog_id: int
    ) -> Optional[Blog]:
        """블로그 조회 (credential 포함)"""
        result = await context.db_session.execute(
            select(Blog)
            .where(Blog.id == blog_id)
            .options(selectinload(Blog.google_credential))
        )
        return result.scalar_one_or_none()

    async def _republish_post(
        self,
        blog: Blog,
        post_id: str,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """포스트 재발행 (API 호출만)"""
        context.log(
            f"[PUBLISH] 재발행 시작 | blog={blog.name} | post_id={post_id}"
        )

        if blog.platform == BlogPlatform.WORDPRESS:
            service = WordPressRepublishService()
            result = await service.update_post_date(blog, post_id)

            if result.get("success"):
                context.log(
                    f"[PUBLISH] WordPress 성공 | blog={blog.name} | "
                    f"post_id={post_id}"
                )
            return result

        elif blog.platform == BlogPlatform.BLOGGER:
            if not blog.google_credential:
                return {
                    "success": False,
                    "message": "Google 인증 정보가 없습니다"
                }

            service = BloggerRepublishService()
            blogger_id = await service.get_blog_id(blog, blog.google_credential)

            # revert → publish
            await service.revert_to_draft(
                blog.google_credential, blogger_id, post_id
            )
            import asyncio
            await asyncio.sleep(0.5)
            result = await service.publish_post(
                blog.google_credential, blogger_id, post_id
            )

            context.log(
                f"[PUBLISH] Blogger 성공 | blog={blog.name} | "
                f"post_id={post_id}"
            )

            return {
                "success": True,
                "message": "재발행 성공",
                "blog_id": blog.id,
                "blog_name": blog.name,
                "post_id": post_id,
                "new_published": result.get("published", ""),
                "url": result.get("url", "")
            }

        else:
            return {
                "success": False,
                "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
            }

    def _create_error_result(
        self,
        blog_id: int,
        blog_name: Optional[str],
        platform: Optional[str],
        error_msg: str
    ) -> BlogAutoItem:
        """에러 결과 아이템 생성"""
        return BlogAutoItem(
            json={
                "blog_id": blog_id,
                "blog_name": blog_name or "Unknown",
                "platform": platform or "unknown",
                "publish_result": {"success": False, "message": error_msg},
                "published_at": datetime.now().isoformat()
            },
            meta=ItemMeta(source_module=self.name)
        )
