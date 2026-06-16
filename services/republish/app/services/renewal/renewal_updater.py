"""리뉴얼 라이브 글 갱신 (P2c) — 데이터 변경.

재생성된 제목/본문으로 플랫폼의 같은 글을 갱신한다. "new" 이미지는 본문에
로컬 /static 경로로 들어있으므로 갱신 전 플랫폼에 업로드 후 URL 치환한다
(PublisherPipeline._upload_inline_images 재사용). "reuse"는 외부 URL이라 no-op.
SEO 신선도를 위해 발행일을 now로 갱신한다.
"""
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog, BlogPlatform

logger = get_logger("renewal_updater", "app.log")

BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
KST = timezone(timedelta(hours=9))
HTTP_TIMEOUT = 30.0


class RenewalUpdater:
    """리뉴얼 결과를 라이브 글에 반영."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def update(
        self,
        blog: Blog,
        post_id: str,
        new_title: str,
        content_html: str,
        bump_date: bool = True,
    ) -> dict:
        """라이브 글 갱신. {success, link|error}."""
        # 본문 내 로컬 이미지 업로드+치환 (new 케이스; reuse는 외부URL이라 no-op)
        try:
            from ..publishing.publisher_pipeline import PublisherPipeline

            pp = PublisherPipeline(self.db)
            content_html = await pp._upload_inline_images(
                blog, content_html, post_title=new_title,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RENEWAL_UPD] 인라인 이미지 처리 오류: %s", exc)

        if blog.platform == BlogPlatform.WORDPRESS:
            return await self._update_wp(
                blog, post_id, new_title, content_html, bump_date,
            )
        if blog.platform == BlogPlatform.BLOGGER:
            return await self._update_blogger(
                blog, post_id, new_title, content_html, bump_date,
            )
        return {"success": False, "error": f"지원하지 않는 플랫폼: {blog.platform}"}

    async def _update_wp(
        self, blog, post_id, title, content, bump_date,
    ) -> dict:
        """WordPress REST POST /posts/{id} 로 갱신."""
        from ...services.wordpress_service import WordPressRepublishService

        svc = WordPressRepublishService()
        url = svc.api._get_api_url(blog, f"posts/{post_id}")
        headers = svc.api._get_auth_headers(blog)
        data: dict = {"title": title, "content": content}
        if bump_date:
            d = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")
            data["date"] = d
            data["date_gmt"] = d
        try:
            res = await svc.api._make_request("POST", url, headers, data)
            return {"success": True, "link": res["data"].get("link", "")}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    async def _update_blogger(
        self, blog, post_id, title, content, bump_date,
    ) -> dict:
        """Blogger PATCH /posts/{id} 로 갱신."""
        from ...services.publishing.google_oauth_helper import (
            resolve_blogger_access_token,
        )

        token = await resolve_blogger_access_token(blog, None)
        if not token:
            return {"success": False, "error": "Blogger 인증 실패"}
        blogger_id = (blog.placeholders or {}).get("blogger_id")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            if not blogger_id:
                r = await client.get(
                    f"{BLOGGER_API_BASE}/blogs/byurl",
                    params={"url": (blog.url or "").rstrip("/")},
                    headers=headers,
                )
                if r.status_code == 200:
                    blogger_id = r.json().get("id")
            if not blogger_id:
                return {"success": False, "error": "Blogger ID 확인 실패"}
            body: dict = {"title": title, "content": content}
            if bump_date:
                body["published"] = datetime.now(KST).isoformat()
            resp = await client.patch(
                f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts/{post_id}",
                json=body, headers=headers,
            )
        if resp.status_code in (200, 201):
            return {"success": True, "link": resp.json().get("url", "")}
        return {
            "success": False,
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
        }
