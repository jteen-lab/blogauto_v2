"""platform_post_id 백필 (재발행 리뉴얼 P1).

과거 발행분 중 platform_post_id가 비어있는 CrawledPost에 대해, 블로그
플랫폼의 라이브 글 목록(URL→ID)을 조회해 매칭으로 채운다.
- WordPress: 공개 REST(/wp-json/wp/v2/posts) 페이지네이션, link↔url 매칭.
- Blogger: posts.list 페이지네이션(인증), url↔url 매칭.

신규 발행분은 발행 시점에 자동 저장되므로(mark_published), 이 스크립트는
1회성 과거분 보정용이다. 매칭 실패분은 url 기반 조회로 대체 가능(비차단).

실행: docker compose exec app python -m app.scripts.backfill_platform_post_id
"""
import asyncio
import os
from typing import Dict

import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://blogauto:blogauto123@db:5432/blogauto_v2",
)
WP_PAGE_SIZE = 100
BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"


def _norm(url: str) -> str:
    """URL 정규화(끝 슬래시 제거 + 소문자) — 매칭 키."""
    return (url or "").strip().rstrip("/").lower()


async def _wp_url_map(blog) -> Dict[str, str]:
    """WordPress 공개 REST에서 link→post_id 맵 구성."""
    from app.services.wordpress_service import WordPressRepublishService

    svc = WordPressRepublishService()
    result: Dict[str, str] = {}
    page = 1
    while True:
        path = (
            f"posts?per_page={WP_PAGE_SIZE}&page={page}"
            "&_fields=id,link&status=publish"
        )
        url = svc.api._get_api_url(blog, path)
        headers = svc.api._get_auth_headers(blog)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
        except Exception as exc:  # noqa: BLE001
            print(f"  WP 조회 오류(page={page}): {exc}")
            break
        if resp.status_code != 200:
            break
        items = resp.json()
        if not items:
            break
        for it in items:
            link = _norm(it.get("link", ""))
            if link and it.get("id"):
                result[link] = str(it["id"])
        if len(items) < WP_PAGE_SIZE:
            break
        page += 1
    return result


async def _blogger_url_map(db: AsyncSession, blog) -> Dict[str, str]:
    """Blogger posts.list에서 url→post_id 맵 구성(인증)."""
    from app.models.google_credential import GoogleCredential
    from app.services.publishing.google_oauth_helper import (
        resolve_blogger_access_token,
    )

    credential = None
    if blog.google_credential_id:
        credential = await db.get(GoogleCredential, blog.google_credential_id)
    token = await resolve_blogger_access_token(blog, credential)
    if not token:
        print(f"  Blogger 토큰 해석 실패 → 스킵")
        return {}

    blogger_id = (blog.placeholders or {}).get("blogger_id")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        if not blogger_id:
            r = await client.get(
                f"{BLOGGER_API_BASE}/blogs/byurl",
                params={"url": (blog.url or "").rstrip("/")},
                headers=headers,
            )
            if r.status_code == 200:
                blogger_id = r.json().get("id")
        if not blogger_id:
            print(f"  Blogger ID 확인 실패 → 스킵")
            return {}

        result: Dict[str, str] = {}
        page_token = None
        while True:
            params = {
                "fetchBodies": "false", "fetchImages": "false",
                "maxResults": 500, "fields": "items(id,url),nextPageToken",
            }
            if page_token:
                params["pageToken"] = page_token
            r = await client.get(
                f"{BLOGGER_API_BASE}/blogs/{blogger_id}/posts",
                params=params, headers=headers,
            )
            if r.status_code != 200:
                break
            data = r.json()
            for it in data.get("items", []) or []:
                u = _norm(it.get("url", ""))
                if u and it.get("id"):
                    result[u] = str(it["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return result


async def backfill() -> None:
    """블로그별로 platform_post_id 백필 실행."""
    from app.models.blog import Blog, BlogPlatform
    from app.models.crawled_post import CrawledPost

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    total_filled = 0
    async with async_session() as db:
        blogs = (await db.execute(
            select(Blog).where(Blog.is_active.is_(True))
        )).scalars().all()
        for blog in blogs:
            posts = (await db.execute(
                select(CrawledPost).where(
                    CrawledPost.blog_id == blog.id,
                    CrawledPost.published_at.isnot(None),
                    CrawledPost.platform_post_id.is_(None),
                    CrawledPost.url.isnot(None),
                )
            )).scalars().all()
            if not posts:
                continue
            print(f"[{blog.name}] 대상 {len(posts)}개 | 플랫폼 목록 조회…")
            try:
                if blog.platform == BlogPlatform.WORDPRESS:
                    url_map = await _wp_url_map(blog)
                elif blog.platform == BlogPlatform.BLOGGER:
                    url_map = await _blogger_url_map(db, blog)
                else:
                    continue
            except Exception as exc:  # noqa: BLE001
                print(f"  목록 조회 실패: {exc} → 스킵")
                continue

            filled = 0
            for p in posts:
                pid = url_map.get(_norm(p.url))
                if pid:
                    p.platform_post_id = pid
                    filled += 1
            await db.commit()
            total_filled += filled
            print(f"  채움 {filled}/{len(posts)} (라이브 글 {len(url_map)}개)")
    await engine.dispose()
    print(f"\n완료: platform_post_id {total_filled}개 백필")


if __name__ == "__main__":
    asyncio.run(backfill())
