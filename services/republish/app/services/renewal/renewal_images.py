"""이미지만 바꾸기 — 제목·본문 글자는 그대로, 그림만 지금 양식으로 (2026-10-25).

10/14 손으로 갱신한 인생꿀팁 4편(/555·/416·/3345·/1686)은 본문만 바뀌고 그림은
2022~2024 업로드 그대로였다. 형 지적(10/25): 제목·글을 고치면 이미지도 같이.

- 워드프레스 '편집용 원문'(context=edit)을 읽는다. 화면용(rendered)을 다시 저장하면
  플러그인이 붙인 목차·광고가 본문에 굳는다.
- 그림 블록(<!-- wp:image -->·figure·img)만 빼고 모듈 이미지 설정으로 새로 만든다.
- 백업 먼저(renewal_record.backup). 실패하면 갱신하지 않는다. 옛 이미지 파일은 지우지 않는다.
- 주소·발행일 그대로(수정일만 바뀜).

순서도: docs/flowcharts/renewal_performance_pick.md (3. 이미지만 바꾸기)
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Any, Optional, Tuple

import httpx

from ...core.logger import get_logger
from . import renewal_record

logger = get_logger("renewal_images", "app.log")

_WP_IMAGE_BLOCK = re.compile(r"<!--\s*wp:image.*?<!--\s*/wp:image\s*-->", re.S | re.I)
_FIGURE_IMG = re.compile(r"<figure[^>]*>(?:(?!</figure>).)*?<img.*?</figure>", re.S | re.I)
_IMG = re.compile(r"<img[^>]*>", re.I)
_EMPTY_P = re.compile(r"<p[^>]*>\s*(?:<a[^>]*>\s*</a>)?\s*</p>", re.I)


def strip_images(content: str) -> str:
    """본문에서 그림만 뺀다(글자는 그대로). 순수 함수."""
    out = _WP_IMAGE_BLOCK.sub("", content or "")
    out = _FIGURE_IMG.sub("", out)
    out = _IMG.sub("", out)
    return _EMPTY_P.sub("", out)


async def fetch_raw(blog: Any, post_id: str) -> Optional[Tuple[str, str]]:
    """(편집용 제목, 편집용 본문). 실패하면 None."""
    from ...services.wordpress_service import WordPressRepublishService

    svc = WordPressRepublishService()
    url = svc.api._get_api_url(blog, f"posts/{post_id}?context=edit&_fields=title,content")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=svc.api._get_auth_headers(blog))
    if resp.status_code != 200:
        logger.warning("[RENEWAL_IMG] 원문 조회 실패 | blog=%s | post=%s | %s",
                       blog.name, post_id, resp.status_code)
        return None
    d = resp.json()
    return (html_lib.unescape((d.get("title") or {}).get("raw", "")),
            (d.get("content") or {}).get("raw", ""))


async def replace_images(db: Any, blog: Any, module: Any, post_id: str,
                         dry_run: bool = True) -> dict:
    """그림만 새로 만든 결과. dry_run 이면 갱신하지 않는다."""
    from ..generation.generator import ContentGenerator

    raw = await fetch_raw(blog, post_id)
    if not raw:
        return {"success": False, "error": "원문 조회 실패"}
    title, content = raw
    stripped = strip_images(content)
    gen = ContentGenerator(db, blog.user_id)
    img = await gen._generate_image_with_retry(
        blog=blog, working_title=title, settings=module.settings or {},
        final_html=stripped, keywords_text="")
    if not (img and img.success and img.image_url):
        return {"success": False, "error": "이미지 생성 실패"}
    from .renewal_generator import inject_featured
    new_html = img.final_html or stripped   # 템플릿 모드는 그림 파일만 돌려준다
    if img.image_url not in new_html:
        new_html = inject_featured(blog, new_html, img.image_url, title)
    result = {"success": True, "dry_run": dry_run, "post_id": post_id, "title": title,
              "old_images": renewal_record.image_urls(content),
              "new_images": renewal_record.image_urls(new_html),
              "image_file": img.image_url, "text_len_before": len(_text(content)),
              "text_len_after": len(_text(new_html)), "new_html": new_html}
    if dry_run:
        return result
    return await _apply(db, blog, post_id, title, content, new_html, result)


async def _apply(db: Any, blog: Any, post_id: str, title: str, content: str,
                 new_html: str, result: dict) -> dict:
    """백업 → 갱신(수정일만) → 기록."""
    from .renewal_updater import RenewalUpdater

    if not renewal_record.backup(blog, post_id, title, content):
        return {"success": False, "error": "원본 백업 실패 — 갱신 안 함"}
    upd = await RenewalUpdater(db).update(blog, post_id, title, new_html, bump_date=False)
    if not upd.get("success"):
        return {"success": False, "error": "갱신 실패: " + upd.get("error", "")}
    renewal_record.journal(blog, {"post_id": post_id, "action": "images_only",
                                  "old_title": title, "new_title": title,
                                  "image_changed": True,
                                  "old_images": result["old_images"]})
    return {**result, "dry_run": False, "url": upd.get("link")}


def _text(h: str) -> str:
    """글자만(그림만 바뀌었는지 비교용)."""
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>|<!--.*?-->", "", h or "", flags=re.S))
