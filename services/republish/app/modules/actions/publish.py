"""
발행 모듈

블로그에 포스트를 발행합니다.
재발행과 신규 발행 모두 이 모듈을 사용합니다.

동작 모드:
1. 입력 아이템에 post_id가 있으면 → 해당 포스트 재발행
2. 입력 아이템에 post_id가 없으면 → Flow 블로그 조회 후 가장 오래된 포스트 재발행
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
from app.models.flow_blog import FlowBlog
from app.models.blog import Blog, BlogPlatform
from app.services.wordpress_service import WordPressRepublishService
from app.services.blogger_service import BloggerRepublishService


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
                name="publish_mode",
                type="select",
                required=False,
                default="republish",
                description="발행 모드",
                options=[
                    {"value": "republish", "label": "재발행 (날짜 업데이트)"},
                    {"value": "new", "label": "신규 발행"}
                ]
            ),
            ModuleParam(
                name="use_input_post",
                type="boolean",
                required=False,
                default=True,
                description="입력 아이템의 포스트 사용 (PostSelector 연결 시)"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """
        발행/재발행 실행

        1. 입력 아이템에 post_id가 있으면 해당 포스트 재발행
        2. 없으면 Flow 블로그를 조회하여 가장 오래된 포스트 재발행
        """
        publish_mode = params.get("publish_mode", "republish")
        use_input_post = params.get("use_input_post", True)

        context.log(
            f"[PUBLISH_MODULE] 시작 | flow_id={context.flow_id} | "
            f"mode={publish_mode} | use_input={use_input_post} | "
            f"input_items={len(items)}"
        )

        results = []

        try:
            # 모드 1: 입력 아이템에서 포스트 정보 사용 (PostSelector 연결)
            if use_input_post and items:
                for item in items:
                    result = await self._process_input_item(item, context)
                    if result:
                        results.append(result)

            # 모드 2: Flow 블로그 직접 조회 (입력 없거나 use_input_post=False)
            else:
                blogs = await self._get_flow_blogs(context)
                if not blogs:
                    context.log(
                        "[PUBLISH_MODULE] 연결된 블로그가 없습니다",
                        level="warning"
                    )
                    return ModuleResult.fail("플로우에 연결된 블로그가 없습니다")

                context.log(f"[PUBLISH_MODULE] 블로그 {len(blogs)}개 대상 실행")

                for blog in blogs:
                    result = await self._execute_republish_blog(blog, context)
                    if result:
                        results.append(result)

            # 결과 집계
            success_count = sum(
                1 for r in results
                if r.json.get("publish_result", {}).get("success")
            )
            context.log(
                f"[PUBLISH_MODULE] 완료 | 성공: {success_count}/{len(results)}"
            )

            return ModuleResult.ok(results)

        except Exception as e:
            context.log(f"[PUBLISH_MODULE] 전체 오류: {e}", level="error")
            return ModuleResult.fail(str(e))

    async def _process_input_item(
        self,
        item: BlogAutoItem,
        context: ExecutionContext
    ) -> Optional[BlogAutoItem]:
        """입력 아이템(PostSelector 결과) 처리"""
        data = item.json
        blog_id = data.get("blog_id")
        post_id = data.get("post_id")
        platform = data.get("platform")

        if not blog_id:
            context.log(
                f"[PUBLISH_MODULE] blog_id 누락 | data={data}",
                level="warning"
            )
            return None

        try:
            # 블로그 조회
            blog = await self._get_blog(context, blog_id)
            if not blog:
                return self._create_error_result(
                    blog_id, data.get("blog_name"), platform,
                    "블로그를 찾을 수 없습니다"
                )

            # 포스트 ID가 있으면 특정 포스트 재발행
            if post_id:
                result = await self._republish_specific_post(blog, post_id, context)
            else:
                # 없으면 가장 오래된 포스트 재발행
                result = await self._execute_republish(blog, context)

            return BlogAutoItem(
                json={
                    "blog_id": blog.id,
                    "blog_name": blog.name,
                    "platform": blog.platform.value,
                    "post_id": post_id or result.get("post_id"),
                    "publish_result": result,
                    "published_at": datetime.now().isoformat()
                },
                meta=ItemMeta(source_module=self.name)
            )

        except Exception as e:
            context.log(
                f"[PUBLISH_MODULE] 처리 오류 | blog_id={blog_id} | error={e}",
                level="error"
            )
            return self._create_error_result(
                blog_id, data.get("blog_name"), platform, str(e)
            )

    async def _execute_republish_blog(
        self,
        blog: Blog,
        context: ExecutionContext
    ) -> Optional[BlogAutoItem]:
        """블로그의 가장 오래된 포스트 재발행"""
        try:
            result = await self._execute_republish(blog, context)

            if result.get("success"):
                context.log(
                    f"[PUBLISH_MODULE] 성공 | blog={blog.name} | "
                    f"post={result.get('post_title', '')[:30]}"
                )
            else:
                context.log(
                    f"[PUBLISH_MODULE] 실패 | blog={blog.name} | "
                    f"error={result.get('message', '')}",
                    level="warning"
                )

            return BlogAutoItem(
                json={
                    "blog_id": blog.id,
                    "blog_name": blog.name,
                    "platform": blog.platform.value,
                    "publish_result": result,
                    "published_at": datetime.now().isoformat()
                },
                meta=ItemMeta(source_module=self.name)
            )

        except Exception as e:
            context.log(
                f"[PUBLISH_MODULE] 블로그 처리 오류 | blog={blog.name} | error={e}",
                level="error"
            )
            return self._create_error_result(
                blog.id, blog.name, blog.platform.value, str(e)
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

    async def _get_flow_blogs(self, context: ExecutionContext) -> list[Blog]:
        """Flow에 연결된 블로그 목록 조회 (credential 포함)"""
        result = await context.db_session.execute(
            select(FlowBlog)
            .where(FlowBlog.flow_id == context.flow_id)
            .options(
                selectinload(FlowBlog.blog)
                .selectinload(Blog.google_credential)
            )
        )
        flow_blogs = result.scalars().all()
        return [fb.blog for fb in flow_blogs if fb.blog]

    async def _execute_republish(
        self,
        blog: Blog,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """블로그의 가장 오래된 포스트 재발행"""
        if blog.platform == BlogPlatform.WORDPRESS:
            service = WordPressRepublishService()
            return await service.republish(blog)

        elif blog.platform == BlogPlatform.BLOGGER:
            if not blog.google_credential:
                return {
                    "success": False,
                    "message": "Google 인증 정보가 없습니다"
                }
            service = BloggerRepublishService()
            return await service.republish(blog, blog.google_credential)

        else:
            return {
                "success": False,
                "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
            }

    async def _republish_specific_post(
        self,
        blog: Blog,
        post_id: str,
        context: ExecutionContext
    ) -> Dict[str, Any]:
        """특정 포스트 재발행 (PostSelector에서 선택된 포스트)"""
        context.log(
            f"[PUBLISH_MODULE] 특정 포스트 재발행 | blog={blog.name} | post_id={post_id}"
        )

        if blog.platform == BlogPlatform.WORDPRESS:
            service = WordPressRepublishService()
            return await service.update_post_date(blog, post_id)

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
