"""F10 — Google Forms 문의 폼 생성 서비스.

폼 전용 구글 계정(A)의 refresh token(system_settings에 암호화 저장)으로 access
token을 얻어, Forms API를 httpx로 직접 호출(Bearer)해 블로그별 문의 폼(이름·
이메일·메시지)을 생성한다. 코드베이스 관례(google-api-python-client 대신 httpx)를
따른다. 순서도 ``docs/flowcharts/adsense_f10_contact_form.md``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from ..system_settings_service import SystemSettingsService
from .google_oauth_helper import refresh_access_token

logger = get_logger("google_forms_service", "app.log")

FORMS_API_BASE = "https://forms.googleapis.com/v1/forms"

# 폼 전용 계정 A 자격 저장 키(system_settings, value는 암호화)
SETTING_FORMS_REFRESH_TOKEN = "forms_account_refresh_token"
SETTING_FORMS_EMAIL = "forms_account_email"


def build_contact_form_items() -> List[Dict[str, Any]]:
    """이름·이메일·메시지 3개 질문을 추가하는 batchUpdate requests.

    - 이름(단답, 필수), 이메일(단답, 필수), 문의 내용(장문, 필수).
    """
    def create_item(index: int, title: str, paragraph: bool) -> Dict[str, Any]:
        return {
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": True,
                            "textQuestion": {"paragraph": paragraph},
                        }
                    },
                },
                "location": {"index": index},
            }
        }

    return [
        create_item(0, "이름", False),
        create_item(1, "이메일", False),
        create_item(2, "문의 내용", True),
    ]


def to_embed_url(responder_uri: str) -> str:
    """응답 URL을 iframe 임베드용으로 변환(?embedded=true)."""
    if not responder_uri:
        return ""
    sep = "&" if "?" in responder_uri else "?"
    return f"{responder_uri}{sep}embedded=true"


async def get_forms_access_token(db: AsyncSession) -> Optional[str]:
    """폼 전용 계정 A의 access token 반환(미설정/실패 시 None).

    system_settings의 암호화된 refresh token을 복호화 → refresh_access_token으로
    access token 교환.
    """
    enc = await SystemSettingsService.get(SETTING_FORMS_REFRESH_TOKEN, db)
    if not enc:
        return None
    try:
        refresh_token = decrypt_api_key(enc)
    except Exception as exc:  # noqa: BLE001
        logger.error("[F10] 폼 계정 refresh token 복호화 실패: %s", exc)
        return None
    return await refresh_access_token(refresh_token)


async def create_contact_form(access_token: str, title: str) -> Dict[str, str]:
    """문의 폼을 생성하고 식별자/URL을 반환.

    Returns:
        {"form_id", "responder_uri", "embed_url"}

    Raises:
        httpx.HTTPStatusError: Forms API 오류
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1) 폼 생성 (info.title만 허용)
        resp = await client.post(
            FORMS_API_BASE,
            headers=headers,
            json={"info": {"title": title, "documentTitle": title}},
        )
        resp.raise_for_status()
        form = resp.json()
        form_id = form["formId"]
        responder_uri = form.get("responderUri", "")

        # 2) 질문 항목 추가
        resp2 = await client.post(
            f"{FORMS_API_BASE}/{form_id}:batchUpdate",
            headers=headers,
            json={"requests": build_contact_form_items()},
        )
        resp2.raise_for_status()

        # responderUri가 비어 있으면 재조회
        if not responder_uri:
            resp3 = await client.get(f"{FORMS_API_BASE}/{form_id}", headers=headers)
            resp3.raise_for_status()
            responder_uri = resp3.json().get("responderUri", "")

    logger.info("[F10] 문의 폼 생성 | form_id=%s | title=%s", form_id, title)
    return {
        "form_id": form_id,
        "responder_uri": responder_uri,
        "embed_url": to_embed_url(responder_uri),
    }
