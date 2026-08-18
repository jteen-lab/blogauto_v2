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

import uuid as uuidlib
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from ..system_settings_service import SystemSettingsService

logger = get_logger("tally_forms_service", "app.log")

TALLY_API_BASE = "https://api.tally.so"
TALLY_PUBLIC_URL = "https://tally.so/r/{form_id}"

# Tally API 키 저장 키(system_settings, value는 암호화)
SETTING_TALLY_API_KEY = "tally_api_key"

# 문의 폼 질문 구성: (라벨, 입력 블록 타입)
_CONTACT_FIELDS = [
    ("이름", "INPUT_TEXT"),
    ("이메일", "INPUT_EMAIL"),
    ("문의 내용", "TEXTAREA"),
]


def _new_uuid() -> str:
    return str(uuidlib.uuid4())


def build_contact_blocks(title: str) -> List[Dict[str, Any]]:
    """문의 폼 블록 구성(Tally 실제 스키마).

    FORM_TITLE(groupType TEXT) + 필드마다 LABEL(groupType LABEL) + INPUT
    (groupType QUESTION). 라벨/입력은 같은 groupUuid로 묶는다.
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
    for label, input_type in _CONTACT_FIELDS:
        group = _new_uuid()
        blocks.append({
            "uuid": _new_uuid(),
            "type": "LABEL",
            "groupUuid": group,
            "groupType": "LABEL",
            "payload": {"safeHTMLSchema": [[label]]},
        })
        blocks.append({
            "uuid": _new_uuid(),
            "type": input_type,
            "groupUuid": group,
            "groupType": "QUESTION",
            "payload": {"isRequired": True},
        })
    return blocks


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


async def create_contact_form(api_key: str, title: str) -> Dict[str, str]:
    """Tally 폼을 생성하고 식별자/URL을 반환.

    Returns:
        {"form_id", "responder_uri", "embed_url"}

    Raises:
        httpx.HTTPStatusError: Tally API 오류(응답 본문을 로깅)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        workspace_id = await _get_workspace_id(client, headers)
        body: Dict[str, Any] = {
            "name": title,
            "status": "PUBLISHED",
            "blocks": build_contact_blocks(title),
        }
        if workspace_id:
            body["workspaceId"] = workspace_id
        else:
            logger.warning("[F10] Tally workspaceId 미확인 → 생략하고 생성 시도")
        resp = await client.post(f"{TALLY_API_BASE}/forms", headers=headers, json=body)
        if resp.status_code >= 400:
            # 400 등 오류 시 응답 본문을 남겨 원인 진단 가능하게
            logger.error(
                "[F10] Tally 폼 생성 오류 %s | body=%s", resp.status_code, resp.text[:1000]
            )
        resp.raise_for_status()
        data = resp.json()

    logger.info("[F10] Tally 폼 생성 응답 원시: %s", str(data)[:1000])
    form_id = data.get("id") or ""
    public = data.get("url") or (TALLY_PUBLIC_URL.format(form_id=form_id) if form_id else "")
    logger.info("[F10] Tally 폼 생성 | form_id=%s | url=%s | title=%s", form_id, public, title)
    return {"form_id": form_id, "responder_uri": public, "embed_url": public}
