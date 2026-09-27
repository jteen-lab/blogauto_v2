"""복사용 HTML — 본문 이미지를 올려 절대주소로 바꾼다.

미리보기 HTML 의 이미지는 로컬 경로(`/static/generated/images/…`)다. 그대로
복사해 블로그에 붙이면 주소가 그 블로그 도메인으로 해석되어 이미지가 깨진다.
그래서 **복사할 때** 그 파일들을 블로그 플랫폼에 올려(블로거→imgbb,
워드프레스→미디어 라이브러리) 절대주소로 바꿔 돌려준다.

**저장된 본문은 건드리지 않는다.** 발행 경로는 지금처럼 로컬 경로를 보고
표지 중복을 가려내므로(`html_injector.has_image`), 저장분까지 원격 주소로
바꾸면 표지가 두 번 들어가던 문제가 되살아난다.

순서도: docs/flowcharts/workbench_copy_html.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ..publishing.image_path_utils import resolve_image_path
from ..publishing.image_uploader import ImageUploader

logger = get_logger("workbench_copy_html", "app.log")

#: 본문에 박힌 우리 서버 이미지. 발행 파이프라인과 같은 형태를 찾는다.
LOCAL_IMAGE = re.compile(
    r'(?:src|href)=["\'](/static/generated/images/[^"\']+)["\']')


def local_images(html: str) -> List[str]:
    """본문에 든 로컬 이미지 주소(중복 제거, 나온 순서)."""
    out: List[str] = []
    for url in LOCAL_IMAGE.findall(html or ""):
        if url not in out:
            out.append(url)
    return out


async def _blog_of(db: AsyncSession, user_id: int,
                   blog_id: int) -> Blog | None:
    """내 블로그만. 남의 블로그 id 로는 올리지 않는다."""
    return (await db.execute(
        select(Blog).where(
            Blog.id == blog_id,
            Blog.user_id == user_id,
            Blog.is_deleted.is_(False),
        )
    )).scalar_one_or_none()


async def absolutize(db: AsyncSession, user_id: int, blog_id: int | None,
                     html: str, title: str = "") -> Dict[str, Any]:
    """복사용 HTML 을 만든다.

    Args:
        db: 세션
        user_id: 요청자
        blog_id: 어느 블로그로 올릴지 — 이미지 저장소가 블로그 설정에 있다
        html: 미리보기 HTML
        title: 이미지 alt·파일명에 쓴다

    Returns:
        {"html": 복사용 HTML, "uploaded": 올린 수, "total": 찾은 수,
         "error": 문구 또는 None}

        올리다 하나라도 실패하면 **바꾸지 않은 HTML 과 사유**를 돌려준다.
        반쪽만 바뀐 본문을 붙이면 어느 이미지가 깨졌는지 알기 어렵다.
    """
    body = html or ""
    found = local_images(body)
    if not found:
        return {"html": body, "uploaded": 0, "total": 0, "error": None}

    if not blog_id:
        return {"html": body, "uploaded": 0, "total": len(found),
                "error": "블로그를 담아야 이미지를 올릴 수 있습니다 — "
                         "이미지 저장소가 블로그 설정에 있습니다"}

    blog = await _blog_of(db, user_id, blog_id)
    if blog is None:
        return {"html": body, "uploaded": 0, "total": len(found),
                "error": "블로그를 찾을 수 없습니다"}

    uploader = ImageUploader()
    swapped = body
    done = 0
    for local in found:
        path = resolve_image_path(local)
        if not path:
            return {"html": body, "uploaded": 0, "total": len(found),
                    "error": f"이미지 파일을 찾을 수 없습니다: {local}"}
        try:
            result = await uploader.upload_image(
                blog, path, title=title or blog.name)
        except Exception as e:  # noqa: BLE001
            logger.warning("[WB_COPY] 업로드 예외 | %s | %s", local, e)
            return {"html": body, "uploaded": 0, "total": len(found),
                    "error": f"이미지 업로드 실패: {e}"}
        if not result.success or not result.platform_url:
            return {"html": body, "uploaded": 0, "total": len(found),
                    "error": f"이미지 업로드 실패: {result.error}"}
        swapped = swapped.replace(local, result.platform_url)
        done += 1
        logger.info("[WB_COPY] 이미지 치환 | %s → %s",
                    local[-40:], result.platform_url[:60])

    return {"html": swapped, "uploaded": done, "total": len(found),
            "error": None}
