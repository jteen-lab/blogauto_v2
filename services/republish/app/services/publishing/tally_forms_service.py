"""F10 — Tally 문의 폼 생성 서비스.

단일 Tally 계정(API 키)으로 블로그별 문의 폼(이름·이메일·메시지)을 생성한다.
모든 폼이 한 계정에 모여 통합 수신(한 대시보드 + 계정 소유자 이메일 알림 +
webhook)이 네이티브로 가능하다. Google Forms(폼별 응답 분리·알림 없음)의
한계를 해소하기 위해 채택(사용자 확정 2026-08-18).

Tally API: POST https://api.tally.so/forms  (Authorization: Bearer tly-...)
- 생성 요청 필수: name, workspaceId, status, blocks
- 블록 필수: uuid, type, groupUuid, groupType, payload
- FORM_TITLE(groupType TEXT) + 필드마다 LABEL(groupType LABEL) + INPUT(groupType QUESTION)
순서도 ``docs/flowcharts/adsense_f10_contact_form.md``.
"""
from __future__ import annotations

import hashlib
import json
import uuid as uuidlib
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from ..system_settings_service import SystemSettingsService
from .contact_form_templates import DEFAULT_FIELDS

logger = get_logger("tally_forms_service", "app.log")

TALLY_API_BASE = "https://api.tally.so"
TALLY_PUBLIC_URL = "https://tally.so/r/{form_id}"

# Tally API 키 저장 키(system_settings, value는 암호화)
SETTING_TALLY_API_KEY = "tally_api_key"


def _new_uuid() -> str:
    return str(uuidlib.uuid4())


def build_blocks_from_fields(
    title: str, fields: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """필드 구성 → Tally 블록 배열(실호출 검증된 스키마).

    FORM_TITLE(groupType TEXT) + 필드마다 LABEL(groupType LABEL) + INPUT
    (groupType=자기 타입). **모든 블록은 각자 고유한 groupUuid**(Tally는 LABEL/TITLE이
    입력과 groupUuid 공유 시 400). 라벨-입력 연결은 순서 기반.

    Args:
        title: 폼 제목
        fields: [{"label","type","required"}] — type은 INPUT_TEXT/INPUT_EMAIL/
            INPUT_PHONE_NUMBER/INPUT_NUMBER/TEXTAREA(확정 타입)
    """
    blocks: List[Dict[str, Any]] = [
        {
            "uuid": _new_uuid(),
            "type": "FORM_TITLE",
            "groupUuid": _new_uuid(),
            "groupType": "TEXT",
            "payload": {"title": title, "safeHTMLSchema": [[title]]},
        }
    ]
    for field in fields:
        label = field["label"]
        input_type = field["type"]
        required = bool(field.get("required", True))
        blocks.append({
            "uuid": _new_uuid(),
            "type": "LABEL",
            "groupUuid": _new_uuid(),
            "groupType": "LABEL",
            "payload": {"safeHTMLSchema": [[label]]},
        })
        blocks.append({
            "uuid": _new_uuid(),
            "type": input_type,
            "groupUuid": _new_uuid(),
            "groupType": input_type,  # 입력 블록 groupType은 자기 타입
            "payload": {"isRequired": required},
        })
    return blocks


def build_contact_blocks(title: str) -> List[Dict[str, Any]]:
    """기본 3필드 문의 폼 블록(하위호환 · 모듈 미배정 폴백)."""
    return build_blocks_from_fields(title, DEFAULT_FIELDS)


def config_hash(
    title_template: str,
    fields: List[Dict[str, Any]],
    styles: Optional[Dict[str, Any]] = None,
    apply_styles: bool = False,
) -> str:
    """폼 구성(제목 템플릿+필드+디자인)의 안정적 해시 — 변경 감지(멱등)용.

    ``styles``가 None이고 ``apply_styles``도 False면 키를 넣지 않아 기존(디자인
    도입 전) 해시와 동일하다 → 이미 생성된 폼이 불필요하게 재수정되지 않는다.
    디자인 '기본'을 명시 선택한 경우(apply_styles=True, styles=None)는 "색을
    지운 상태"가 별도 구성이므로 해시에 반영해야 되돌리기가 감지된다.
    """
    data: Dict[str, Any] = {"title": title_template or "", "fields": fields or []}
    if styles:
        data["styles"] = styles
    elif apply_styles:
        data["styles"] = None
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def get_tally_api_key(db: AsyncSession) -> Optional[str]:
    """저장된 Tally API 키(복호화) 반환. 미설정/실패 시 None."""
    enc = await SystemSettingsService.get(SETTING_TALLY_API_KEY, db)
    if not enc:
        return None
    try:
        return decrypt_api_key(enc)
    except Exception as exc:  # noqa: BLE001
        logger.error("[F10] Tally API 키 복호화 실패: %s", exc)
        return None


async def _get_workspace_id(
    client: httpx.AsyncClient, headers: Dict[str, str]
) -> Optional[str]:
    """첫 번째 워크스페이스 id 반환(없으면 None → 생성 시 생략).

    응답 형식이 계정/버전마다 다를 수 있어 방어적으로 파싱하고 원시 응답을
    로깅한다({items}/{workspaces}/bare list 모두 대응).
    """
    resp = await client.get(f"{TALLY_API_BASE}/workspaces", headers=headers)
    if resp.status_code >= 400:
        logger.error(
            "[F10] Tally workspaces 오류 %s | %s", resp.status_code, resp.text[:500]
        )
        return None
    data = resp.json()
    logger.info("[F10] Tally workspaces 응답 원시: %s", str(data)[:500])

    items: Any = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("items", "workspaces", "data"):
            if isinstance(data.get(key), list) and data[key]:
                items = data[key]
                break
    if not items:
        return None
    first = items[0]
    return first.get("id") if isinstance(first, dict) else None


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def create_contact_form(
    api_key: str,
    title: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    styles: Optional[Dict[str, Any]] = None,
    apply_styles: bool = False,
) -> Dict[str, str]:
    """Tally 폼을 생성하고 식별자/URL을 반환.

    Args:
        fields: 필드 구성(None이면 기본 3필드)
        styles: Tally settings.styles(디자인). None이면 기본 외형.
        apply_styles: True면 styles가 None이어도 ``settings.styles``를 전송해
            Tally 기본 외형으로 **초기화**한다(디자인 '기본' 선택 시 필요).

    Returns:
        {"form_id", "responder_uri", "embed_url"}

    Raises:
        httpx.HTTPStatusError: Tally API 오류(응답 본문을 로깅)
    """
    headers = _headers(api_key)
    blocks = build_blocks_from_fields(title, fields or DEFAULT_FIELDS)
    async with httpx.AsyncClient(timeout=30.0) as client:
        workspace_id = await _get_workspace_id(client, headers)
        body: Dict[str, Any] = {
            "name": title, "status": "PUBLISHED", "blocks": blocks,
        }
        if styles or apply_styles:
            body["settings"] = {"styles": styles}
        if workspace_id:
            body["workspaceId"] = workspace_id
        else:
            logger.warning("[F10] Tally workspaceId 미확인 → 생략하고 생성 시도")
        resp = await client.post(f"{TALLY_API_BASE}/forms", headers=headers, json=body)
        if resp.status_code >= 400:
            logger.error(
                "[F10] Tally 폼 생성 오류 %s | body=%s", resp.status_code, resp.text[:1000]
            )
        resp.raise_for_status()
        data = resp.json()

    form_id = data.get("id") or ""
    public = data.get("url") or (TALLY_PUBLIC_URL.format(form_id=form_id) if form_id else "")
    logger.info("[F10] Tally 폼 생성 | form_id=%s | url=%s | title=%s", form_id, public, title)
    return {"form_id": form_id, "responder_uri": public, "embed_url": public}


async def update_contact_form(
    api_key: str,
    form_id: str,
    title: str,
    fields: List[Dict[str, Any]],
    styles: Optional[Dict[str, Any]] = None,
    apply_styles: bool = False,
) -> Dict[str, str]:
    """기존 Tally 폼의 필드/디자인 구성을 PATCH로 수정(멱등 갱신).

    Tally는 업데이트 시 전체 블록을 전송해야 한다.

    Args:
        styles: Tally settings.styles(디자인). None이면 미전송(기존 외형 유지).
        apply_styles: True면 styles가 None이어도 ``settings.styles: null``을
            전송해 이전 디자인을 지운다 — 이게 없으면 색을 넣었던 폼을 디자인
            '기본'으로 되돌려도 Tally에는 옛 색이 그대로 남는다.

    Returns:
        {"form_id", "responder_uri", "embed_url"}
    """
    headers = _headers(api_key)
    blocks = build_blocks_from_fields(title, fields)
    body: Dict[str, Any] = {"name": title, "status": "PUBLISHED", "blocks": blocks}
    if styles or apply_styles:
        body["settings"] = {"styles": styles}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(
            f"{TALLY_API_BASE}/forms/{form_id}", headers=headers, json=body
        )
        if resp.status_code >= 400:
            logger.error(
                "[F10] Tally 폼 수정 오류 %s | body=%s", resp.status_code, resp.text[:1000]
            )
        resp.raise_for_status()
    public = TALLY_PUBLIC_URL.format(form_id=form_id)
    logger.info("[F10] Tally 폼 수정 | form_id=%s | title=%s", form_id, title)
    return {"form_id": form_id, "responder_uri": public, "embed_url": public}
