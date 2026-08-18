"""F10 — 문의 폼 프로비저닝.

블로그에 문의 폼이 없으면 Google Form을 생성해 ``author_profile``의
``contact_form_url``/``contact_form_id``를 채운다(멱등). 폼 계정 미설정이거나
실패 시 None을 반환해 호출측이 기존 mailto로 폴백하도록 한다.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from .tally_forms_service import create_contact_form, get_tally_api_key

logger = get_logger("contact_form_provisioner", "app.log")


async def ensure_contact_form(blog: Blog, db: AsyncSession) -> Optional[str]:
    """블로그에 문의 폼 URL을 보장한다.

    - 이미 자동 생성된 폼(``contact_form_id``+``contact_form_url``)이 있으면 재사용.
    - 운영자가 수동 입력한 ``contact_form_url``이 있으면 존중(자동 생성 안 함).
    - **옛 Google Forms(docs.google.com) URL은 stale로 보고 Tally로 재생성**
      (Google Forms→Tally 전환 마이그레이션).
    - 폼 계정 미설정/생성 실패 시 None(호출측은 기존 mailto로 폴백).

    Returns:
        보장된 ``contact_form_url`` 또는 None
    """
    profile = dict(blog.author_profile or {})
    existing_url = profile.get("contact_form_url") or ""
    is_legacy_google = "docs.google.com/forms" in existing_url

    if not is_legacy_google:
        if profile.get("contact_form_id") and existing_url:
            return existing_url
        if existing_url:
            # 운영자 수동 입력값 존중
            return existing_url
    # 옛 구글폼이거나 폼 없음 → Tally로 (재)생성

    api_key = await get_tally_api_key(db)
    if not api_key:
        logger.info("[F10] Tally API 키 미설정 → 자동 생성 건너뜀 | blog=%s", blog.name)
        return None

    try:
        result = await create_contact_form(api_key, f"{blog.name} 문의")
    except Exception as exc:  # noqa: BLE001
        logger.error("[F10] 문의 폼 생성 실패 | blog=%s | %s", blog.name, exc)
        return None

    profile["contact_form_id"] = result["form_id"]
    profile["contact_form_url"] = result["embed_url"]
    blog.author_profile = profile
    await db.commit()
    logger.info(
        "[F10] 문의 폼 프로비저닝 완료 | blog=%s | url=%s",
        blog.name, result["embed_url"],
    )
    return result["embed_url"]
