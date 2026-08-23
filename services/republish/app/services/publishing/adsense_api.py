"""AdSense Management API v2 조회 (읽기 전용).

사이트 목록과 그 상태만 가져온다. 계정이 여러 개일 수 있으므로 계정별로 호출한
뒤 병합한다(병합 규칙은 adsense_status_resolver.build_sites_index).

필요 권한: https://www.googleapis.com/auth/adsense.readonly
→ 기존 Blogger 토큰에는 이 범위가 없으므로 **애드센스용 토큰을 따로 발급**해야 한다.

주의: Indexing API와 달리 조회만 하므로 정책 제약이 없다.
"""
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ...core.logger import get_logger
from .google_oauth_helper import refresh_access_token

logger = get_logger("adsense_api", "app.log")

ADSENSE_API_BASE = "https://adsense.googleapis.com/v2"
TIMEOUT = 30.0


class AdsenseApiError(Exception):
    """애드센스 API 호출 실패."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def _get(client: httpx.AsyncClient, url: str, token: str) -> Dict[str, Any]:
    resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        detail = resp.text[:300]
        logger.error("[ADSENSE_API] %s → %s | %s", url, resp.status_code, detail)
        raise AdsenseApiError(
            f"애드센스 API 오류 {resp.status_code}: {detail}", resp.status_code
        )
    return resp.json()


async def list_accounts(access_token: str) -> List[Dict[str, Any]]:
    """이 토큰으로 접근 가능한 애드센스 계정 목록."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        data = await _get(client, f"{ADSENSE_API_BASE}/accounts", access_token)
    return data.get("accounts") or []


async def list_sites(access_token: str, account_resource: str) -> List[Dict[str, Any]]:
    """계정의 사이트 목록(페이지 끝까지 이어받는다)."""
    sites: List[Dict[str, Any]] = []
    page_token = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            url = f"{ADSENSE_API_BASE}/{account_resource}/sites?pageSize=100"
            if page_token:
                url += f"&pageToken={page_token}"
            data = await _get(client, url, access_token)
            sites.extend(data.get("sites") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return sites


async def fetch_account_sites(
    refresh_token: str, account_resource: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """토큰으로 계정을 확인하고 사이트 목록을 가져온다.

    Args:
        account_resource: 이미 알고 있으면 계정 조회를 건너뛴다.

    Returns:
        (account_resource, sites)

    Raises:
        AdsenseApiError: 토큰 교환 실패 또는 계정 없음
    """
    token = await refresh_access_token(refresh_token)
    if not token:
        raise AdsenseApiError(
            "액세스 토큰 발급 실패 — refresh token 또는 구글 OAuth 설정을 확인하세요"
        )

    resource = account_resource
    if not resource:
        accounts = await list_accounts(token)
        if not accounts:
            raise AdsenseApiError(
                "이 토큰으로 접근 가능한 애드센스 계정이 없습니다"
                " (adsense.readonly 범위로 발급했는지 확인하세요)"
            )
        resource = accounts[0].get("name")
        if len(accounts) > 1:
            logger.info(
                "[ADSENSE_API] 계정 %d개 발견 — 첫 계정 사용: %s",
                len(accounts), resource,
            )

    sites = await list_sites(token, resource)
    logger.info("[ADSENSE_API] 사이트 %d건 조회 | account=%s", len(sites), resource)
    return resource, sites
