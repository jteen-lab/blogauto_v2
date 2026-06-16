"""리뉴얼 소스 조회 (P2a) — 라이브 글 fetch + 양식 판별 (read-only).

플랫폼 API로 라이브 글을 가져와 제목/본문/대표이미지 URL을 추출하고,
대표이미지가 blogauto(현재 양식)인지 레거시인지 판별한다. 이미지 재사용
여부 결정에 사용한다(제목 keep + blogauto글 + blogauto이미지 → 재사용).
"""
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from ...core.logger import get_logger
from ...models.blog import Blog, BlogPlatform

logger = get_logger("renewal_source", "app.log")

BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
HTTP_TIMEOUT = 30.0

# blogauto 이미지 판별 패턴
_WP_BLOGAUTO_FILENAME = re.compile(r"/blogauto_[^/\"']+\.(webp|jpg|jpeg|png)", re.IGNORECASE)
_IMGBB_HOSTS = ("i.ibb.co", "ibb.co")
_IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


@dataclass
class LivePost:
    """라이브 글 조회 결과."""

    platform_post_id: str
    title: str
    content_html: str
    featured_image_url: Optional[str]
    image_origin: str  # "blogauto" | "legacy" | "none"


def extract_featured_image(content_html: str) -> Optional[str]:
    """본문에서 대표(첫) 이미지 src 추출."""
    if not content_html:
        return None
    m = _IMG_SRC.search(content_html)
    return m.group(1).strip() if m else None


def detect_image_origin(platform: str, image_url: Optional[str]) -> str:
    """대표이미지 출처 판별: blogauto | legacy | none.

    - WordPress: 파일명 `blogauto_*.webp` 등 → blogauto.
    - Blogger: imgbb 호스팅(i.ibb.co) → blogauto.
    - 그 외(구글 호스팅 등) → legacy. 이미지 없으면 none.
    """
    if not image_url:
        return "none"
    url = image_url.lower()
    if platform == "wordpress" or platform == "WORDPRESS":
        return "blogauto" if _WP_BLOGAUTO_FILENAME.search(image_url) else "legacy"
    if platform == "blogger" or platform == "BLOGGER":
        return "blogauto" if any(h in url for h in _IMGBB_HOSTS) else "legacy"
    return "legacy"


class RenewalSource:
    """라이브 글 조회 서비스."""

    async def fetch(
        self, blog: Blog, platform_post_id: Optional[str], url: Optional[str],
    ) -> Optional[LivePost]:
        """플랫폼에서 라이브 글을 가져온다. 실패 시 None."""
        try:
            if blog.platform == BlogPlatform.WORDPRESS:
                return await self._fetch_wp(blog, platform_post_id, url)
            if blog.platform == BlogPlatform.BLOGGER:
                return await self._fetch_blogger(blog, platform_post_id, url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RENEWAL_SRC] 라이브 글 조회 실패 | blog=%s | %s",
                blog.name, exc,
            )
        return None

    async def _fetch_wp(
        self, blog: Blog, post_id: Optional[str], url: Optional[str],
    ) -> Optional[LivePost]:
        """WordPress REST로 글 조회 (id 우선, 없으면 slug)."""
        from ...services.wordpress_service import WordPressRepublishService

        svc = WordPressRepublishService()
        headers = svc.api._get_auth_headers(blog)
        if post_id:
            path = f"posts/{post_id}?_fields=id,title,content,link"
        else:
            slug = (url or "").rstrip("/").rsplit("/", 1)[-1]
            path = f"posts?slug={slug}&_fields=id,title,content,link"
        api_url = svc.api._get_api_url(blog, path)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(api_url, headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json()
        post = data[0] if isinstance(data, list) else data
        if not post:
            return None
        content = (post.get("content") or {}).get("rendered", "")
        title = (post.get("title") or {}).get("rendered", "")
        img = extract_featured_image(content)
        return LivePost(
            platform_post_id=str(post.get("id", post_id or "")),
            title=title,
            content_html=content,
            featured_image_url=img,
            image_origin=detect_image_origin("wordpress", img),
        )

    async def _fetch_blogger(
        self, blog: Blog, post_id: Optional[str], url: Optional[str],
    ) -> Optional[LivePost]:
        """Blogger API로 글 조회 (id 우선, 없으면 bypath)."""
        from ...services.publishing.google_oauth_helper import (
            resolve_blogger_access_token,
        )

        # credential(google_credential_id) 주입은 P2 통합 시 호출측에서 처리.
        # 여기서는 blog.oauth_token_encrypted(레거시 oauth) 경로를 사용한다.
        token = await resolve_blogger_access_token(blog, None)
        if not token:
            return None
        blogger_id = (blog.placeholders or {}).get("blogger_id")
        headers = {"Authorization": f"Bearer {token}"}
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
                return None
            if post_id:
                api = f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts/{post_id}"
                resp = await client.get(api, headers=headers)
            else:
                path = "/" + (url or "").split(blog.url.rstrip("/"), 1)[-1].lstrip("/")
                resp = await client.get(
                    f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts/bypath",
                    params={"path": path}, headers=headers,
                )
        if resp.status_code != 200:
            return None
        post = resp.json()
        content = post.get("content", "")
        img = extract_featured_image(content)
        return LivePost(
            platform_post_id=str(post.get("id", post_id or "")),
            title=post.get("title", ""),
            content_html=content,
            featured_image_url=img,
            image_origin=detect_image_origin("blogger", img),
        )
