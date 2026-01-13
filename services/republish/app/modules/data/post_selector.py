"""
포스트 선택 모듈

재발행할 포스트를 선택합니다.
WordPress/Blogger API를 통해 포스트를 조회하고 조건에 맞는 포스트를 선택합니다.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta
from app.models.blog import Blog, BlogPlatform
from app.services.wordpress_service import WordPressRepublishService
from app.services.blogger_service import BloggerRepublishService


class PostSelectorModule(ModuleInterface):
    """포스트 선택 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "post_selector"

    @property
    def display_name(self) -> str:
        return "포스트 선택"

    @property
    def description(self) -> str:
        return "재발행할 포스트를 선택합니다."

    @property
    def icon(self) -> str:
        return "🎯"

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
                name="selection_mode",
                type="select",
                required=False,
                default="oldest",
                description="선택 방식",
                options=[
                    {"value": "oldest", "label": "가장 오래된 것"},
                    {"value": "random", "label": "랜덤"},
                    {"value": "sequential", "label": "순차"}
                ]
            ),
            ModuleParam(
                name="min_age_days",
                type="number",
                required=False,
                default=0,
                description="최소 경과 일수 (0=제한 없음)"
            ),
            ModuleParam(
                name="max_posts_to_scan",
                type="number",
                required=False,
                default=100,
                description="스캔할 최대 포스트 수"
            ),
            ModuleParam(
                name="exclude_recent_hours",
                type="number",
                required=False,
                default=0,
                description="최근 N시간 이내 발행된 글 제외"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """
        포스트 선택 실행

        입력 아이템에서 블로그 정보를 읽고, 해당 블로그에서 포스트를 선택합니다.
        """
        selection_mode = params.get("selection_mode", "oldest")
        min_age_days = params.get("min_age_days", 0)
        max_posts = params.get("max_posts_to_scan", 100)

        context.log(
            f"[POST_SELECTOR] 시작 | mode={selection_mode} | "
            f"min_age={min_age_days}일 | max_scan={max_posts}"
        )

        results = []

        for item in items:
            blog_data = item.json
            blog_id = blog_data.get("blog_id") or blog_data.get("id")
            platform = blog_data.get("platform")

            if not blog_id or not platform:
                context.log(
                    f"[POST_SELECTOR] 블로그 정보 누락 | data={blog_data}",
                    level="warning"
                )
                continue

            try:
                # 블로그 객체 조회
                blog = await self._get_blog(context, blog_id)
                if not blog:
                    context.log(
                        f"[POST_SELECTOR] 블로그 없음 | id={blog_id}",
                        level="warning"
                    )
                    continue

                # 포스트 선택
                selected_post = await self._select_post(
                    context, blog, selection_mode, min_age_days, max_posts
                )

                if selected_post:
                    result_item = BlogAutoItem(
                        json={
                            "blog_id": blog.id,
                            "blog_name": blog.name,
                            "platform": blog.platform.value,
                            "post_id": selected_post.get("id"),
                            "post_title": selected_post.get("title"),
                            "post_date": selected_post.get("date"),
                            "post_url": selected_post.get("url") or selected_post.get("link"),
                            "selection_mode": selection_mode
                        },
                        meta=ItemMeta(source_module=self.name)
                    )
                    results.append(result_item)
                    context.log(
                        f"[POST_SELECTOR] 선택 완료 | blog={blog.name} | "
                        f"post={selected_post.get('title', '')[:30]}"
                    )
                else:
                    context.log(
                        f"[POST_SELECTOR] 조건에 맞는 포스트 없음 | blog={blog.name}",
                        level="warning"
                    )

            except Exception as e:
                context.log(
                    f"[POST_SELECTOR] 포스트 선택 오류 | blog_id={blog_id} | error={e}",
                    level="error"
                )

        context.log(f"[POST_SELECTOR] 완료 | 선택된 포스트: {len(results)}개")
        return ModuleResult.ok(results)

    async def _get_blog(self, context: ExecutionContext, blog_id: int) -> Optional[Blog]:
        """블로그 조회"""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        query = (
            select(Blog)
            .where(Blog.id == blog_id)
            .options(selectinload(Blog.google_credential))
        )
        result = await context.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _select_post(
        self,
        context: ExecutionContext,
        blog: Blog,
        mode: str,
        min_age_days: int,
        max_posts: int
    ) -> Optional[Dict[str, Any]]:
        """포스트 선택 로직"""
        if blog.platform == BlogPlatform.WORDPRESS:
            return await self._select_wordpress_post(
                blog, mode, min_age_days, max_posts
            )
        elif blog.platform == BlogPlatform.BLOGGER:
            return await self._select_blogger_post(
                context, blog, mode, min_age_days, max_posts
            )
        return None

    async def _select_wordpress_post(
        self,
        blog: Blog,
        mode: str,
        min_age_days: int,
        max_posts: int
    ) -> Optional[Dict[str, Any]]:
        """WordPress 포스트 선택"""
        service = WordPressRepublishService()

        if mode == "oldest":
            # 가장 오래된 포스트 선택 (기존 로직)
            post = await service.get_oldest_post(blog)
            if post and self._check_age(post.get("date"), min_age_days):
                return post
            return None

        elif mode == "random":
            # 랜덤 선택: 여러 포스트 조회 후 랜덤 선택
            posts = await self._get_wordpress_posts(blog, max_posts)
            eligible = [p for p in posts if self._check_age(p.get("date"), min_age_days)]
            return random.choice(eligible) if eligible else None

        elif mode == "sequential":
            # 순차 선택: oldest와 동일 (가장 오래된 것부터)
            post = await service.get_oldest_post(blog)
            if post and self._check_age(post.get("date"), min_age_days):
                return post
            return None

        return None

    async def _get_wordpress_posts(
        self, blog: Blog, limit: int
    ) -> List[Dict[str, Any]]:
        """WordPress 포스트 목록 조회"""
        from app.services.wordpress_api import WordPressAPI

        api = WordPressAPI()
        url = api._get_api_url(
            blog,
            f"posts?per_page={min(limit, 100)}&orderby=date&order=asc&status=publish"
        )
        headers = api._get_auth_headers(blog)

        try:
            result = await api._make_request("GET", url, headers)
            posts = result.get("data", [])
            return [
                {
                    "id": str(p["id"]),
                    "title": p.get("title", {}).get("rendered", ""),
                    "date": p.get("date", ""),
                    "link": p.get("link", "")
                }
                for p in posts
            ]
        except Exception:
            return []

    async def _select_blogger_post(
        self,
        context: ExecutionContext,
        blog: Blog,
        mode: str,
        min_age_days: int,
        max_posts: int
    ) -> Optional[Dict[str, Any]]:
        """Blogger 포스트 선택"""
        if not blog.google_credential:
            return None

        service = BloggerRepublishService()

        try:
            blogger_id = await service.get_blog_id(blog, blog.google_credential)

            if mode == "oldest":
                post = await service.get_oldest_post(
                    blog, blog.google_credential, blogger_id
                )
                if post and self._check_age(post.get("published"), min_age_days):
                    return {
                        "id": post["id"],
                        "title": post.get("title", ""),
                        "date": post.get("published", ""),
                        "url": post.get("url", "")
                    }
                return None

            elif mode == "random":
                posts = await self._get_blogger_posts(
                    blog, blog.google_credential, blogger_id, max_posts
                )
                eligible = [
                    p for p in posts
                    if self._check_age(p.get("date"), min_age_days)
                ]
                return random.choice(eligible) if eligible else None

            elif mode == "sequential":
                post = await service.get_oldest_post(
                    blog, blog.google_credential, blogger_id
                )
                if post and self._check_age(post.get("published"), min_age_days):
                    return {
                        "id": post["id"],
                        "title": post.get("title", ""),
                        "date": post.get("published", ""),
                        "url": post.get("url", "")
                    }
                return None

        except Exception:
            return None

        return None

    async def _get_blogger_posts(
        self,
        blog: Blog,
        credential,
        blogger_id: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Blogger 포스트 목록 조회"""
        import httpx

        BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
        access_token = credential.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        url = (
            f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts?"
            f"maxResults={min(limit, 100)}&orderBy=published"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get("items", [])
                    return [
                        {
                            "id": p["id"],
                            "title": p.get("title", ""),
                            "date": p.get("published", ""),
                            "url": p.get("url", "")
                        }
                        for p in posts
                    ]
        except Exception:
            pass

        return []

    def _check_age(self, date_str: Optional[str], min_age_days: int) -> bool:
        """포스트 경과 일수 확인"""
        if min_age_days <= 0:
            return True

        if not date_str:
            return True

        try:
            # ISO 8601 형식 파싱
            if "T" in date_str:
                post_date = datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                )
            else:
                post_date = datetime.fromisoformat(date_str)

            # timezone naive로 변환
            if post_date.tzinfo:
                post_date = post_date.replace(tzinfo=None)

            age = datetime.now() - post_date
            return age.days >= min_age_days

        except Exception:
            return True
