"""F10 — 문의 폼 프로비저닝(멱등).

블로그에 문의 폼을 보장한다. 폼 구성(제목·필드)을 인자로 받아:
- 폼 없음 → Tally 폼 생성
- 폼 있음 + 구성 변경(해시 불일치) → Tally PATCH로 수정
- 폼 있음 + 구성 동일 → no-op(Tally 호출 없음)
→ 반복 실행(수동/오토런)해도 안전하고 저부하. contact_form 모듈이 이 함수를
블로그마다 호출한다. 미설정/실패 시 None → 호출측이 기존 mailto로 폴백.
계획서 docs/plans/adsense_contact_form_module_plan.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from .contact_form_templates import DEFAULT_FIELDS
from .tally_forms_service import (
    config_hash,
    create_contact_form,
    get_tally_api_key,
    update_contact_form,
)

logger = get_logger("contact_form_provisioner", "app.log")

DEFAULT_TITLE_TEMPLATE = "{blog} 문의"


def _resolve_config(template: Optional[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """적용할 (title_template, fields) 결정. 없으면 기본 3필드."""
    if template:
        return (
            template.get("title_template") or DEFAULT_TITLE_TEMPLATE,
            template.get("fields") or DEFAULT_FIELDS,
        )
    return DEFAULT_TITLE_TEMPLATE, DEFAULT_FIELDS


async def ensure_contact_form(
    blog: Blog,
    db: AsyncSession,
    template: Optional[Dict[str, Any]] = None,
    design: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """블로그에 문의 폼 URL을 보장(멱등).

    Args:
        template: {"title_template","fields"} — 미지정 시 기본 3필드.
        design: {"styles": {...}} — 미지정/None styles면 Tally 기본 외형.

    Returns:
        보장된 contact_form_url 또는 None(미설정/실패 → mailto 폴백)
    """
    profile = dict(blog.author_profile or {})
    existing_url = profile.get("contact_form_url") or ""
    existing_id = profile.get("contact_form_id")
    existing_hash = profile.get("contact_form_config_hash")
    is_legacy_google = "docs.google.com/forms" in existing_url

    # 운영자 수동 외부 URL(비구글·id 없음)은 존중
    if existing_url and not existing_id and not is_legacy_google:
        return existing_url

    title_template, fields = _resolve_config(template)
    styles = (design or {}).get("styles")
    desired_hash = config_hash(title_template, fields, styles)
    title = title_template.replace("{blog}", blog.name)

    api_key = await get_tally_api_key(db)
    if not api_key:
        logger.info("[F10] Tally API 키 미설정 → 자동 생성 건너뜀 | blog=%s", blog.name)
        return existing_url if (existing_url and not is_legacy_google) else None

    # 폼 없음 or 옛 구글폼 → 생성
    if is_legacy_google or not existing_id or not existing_url:
        try:
            result = await create_contact_form(api_key, title, fields, styles)
        except Exception as exc:  # noqa: BLE001
            logger.error("[F10] 문의 폼 생성 실패 | blog=%s | %s", blog.name, exc)
            return None
        profile["contact_form_id"] = result["form_id"]
        profile["contact_form_url"] = result["embed_url"]
        profile["contact_form_config_hash"] = desired_hash
        blog.author_profile = profile
        await db.commit()
        logger.info("[F10] 문의 폼 생성 | blog=%s | url=%s", blog.name, result["embed_url"])
        return result["embed_url"]

    # 폼 있음 + 구성 동일 → 스킵(멱등, Tally 호출 없음)
    if existing_hash == desired_hash:
        return existing_url

    # 폼 있음 + 구성 변경 → PATCH
    try:
        await update_contact_form(api_key, existing_id, title, fields, styles)
    except Exception as exc:  # noqa: BLE001
        logger.error("[F10] 문의 폼 수정 실패 | blog=%s | %s", blog.name, exc)
        return existing_url  # 실패 시 기존 유지
    profile["contact_form_config_hash"] = desired_hash
    blog.author_profile = profile
    await db.commit()
    logger.info("[F10] 문의 폼 수정 | blog=%s | url=%s", blog.name, existing_url)
    return existing_url
