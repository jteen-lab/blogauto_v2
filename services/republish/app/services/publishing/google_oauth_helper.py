"""
Google OAuth 공통 헬퍼

Blogger/Google 관련 발행 서비스에서 공통으로 사용하는
OAuth access_token 갱신 유틸리티입니다.

- Google OAuth2 토큰 엔드포인트 호출
- Client ID/Secret 조회 (settings → 환경변수 → .env 순서)
- refresh_token / access_token 자동 판별
"""
import os
from pathlib import Path
from typing import Optional, Tuple

import httpx

from ...core.logger import get_logger

logger = get_logger("google_oauth_helper", "app.log")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_TIMEOUT = 30.0

_CID_KEYS = ("GOOGLE_CLIENT_ID", "BLOGGER_CLIENT_ID")
_CSE_KEYS = ("GOOGLE_CLIENT_SECRET", "BLOGGER_CLIENT_SECRET")


def _read_env_file(cid: str, cse: str) -> Tuple[str, str]:
    """프로젝트 .env 파일에서 OAuth 설정 읽기

    이 파일 기준: services/republish/app/services/publishing/google_oauth_helper.py
    → parents[3] = services/republish/
    """
    for p in (Path(__file__).parents[3] / ".env",):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if not cid and k in _CID_KEYS:
                cid = v
            if not cse and k in _CSE_KEYS:
                cse = v
    return cid, cse


def get_google_oauth_credentials() -> Tuple[str, str]:
    """Google OAuth Client ID/Secret 조회.

    우선순위: DB(user_settings) → 환경변수 → .env 파일

    Returns:
        (client_id, client_secret) 튜플. 미설정 시 빈 문자열.
    """
    cid, cse = _get_credentials_from_db()
    if cid and cse:
        return cid, cse

    cid = (
        os.environ.get("GOOGLE_CLIENT_ID", "")
        or os.environ.get("BLOGGER_CLIENT_ID", "")
    )
    cse = (
        os.environ.get("GOOGLE_CLIENT_SECRET", "")
        or os.environ.get("BLOGGER_CLIENT_SECRET", "")
    )
    if not cid or not cse:
        cid, cse = _read_env_file(cid, cse)
    return cid, cse


def _get_credentials_from_db() -> Tuple[str, str]:
    """DB(user_settings)에서 Blogger OAuth 자격증명 조회."""
    try:
        import asyncio
        from ...core.database import db_manager
        from ...models.user_settings import UserSettings
        from sqlalchemy import select

        async def _query():
            async with db_manager.get_session() as db:
                result = await db.execute(
                    select(UserSettings).limit(1)
                )
                s = result.scalar_one_or_none()
                if s and s.blogger_client_id and s.blogger_client_secret:
                    return s.blogger_client_id, s.blogger_client_secret
            return "", ""

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, _query()).result()
        except RuntimeError:
            return asyncio.run(_query())
    except Exception as e:
        logger.debug(f"[OAUTH_HELPER] DB 조회 실패 (폴백 사용): {e}")
        return "", ""


async def refresh_access_token(
    refresh_token: str,
) -> Optional[str]:
    """Refresh Token → Access Token 교환

    Args:
        refresh_token: Google refresh_token (보통 "1//" 시작).
            이미 access_token("ya29." 시작)이면 그대로 반환.

    Returns:
        새 access_token 또는 None (실패 시)
    """
    if not refresh_token:
        return None

    # 이미 access_token이면 그대로 반환
    if refresh_token.startswith("ya29."):
        return refresh_token

    cid, cse = get_google_oauth_credentials()
    if not cid or not cse:
        logger.error(
            "[OAUTH_HELPER] CLIENT_ID/SECRET 미설정 → "
            "토큰 갱신 불가"
        )
        return None

    try:
        async with httpx.AsyncClient(
            timeout=OAUTH_TIMEOUT,
        ) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": cid,
                    "client_secret": cse,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            logger.info(
                "[OAUTH_HELPER] Access Token 발급 성공 "
                "(refresh_token 사용)"
            )
            return token
        logger.error(
            "[OAUTH_HELPER] 토큰 교환 실패 | "
            "status=%d | %s",
            resp.status_code, resp.text[:200],
        )
    except Exception as e:
        logger.error(
            "[OAUTH_HELPER] 토큰 교환 오류: %s", e,
        )
    return None
