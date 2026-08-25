"""S6 — 색인 상태 점검 (Google Search Console URL Inspection API).

발행한 URL을 구글이 실제로 색인했는지 확인해 블로그별 색인율을 낸다.
IndexNow 도입 전후를 비교할 측정 수단이 없으면 "효과가 없어 보인다"는 판단이
반복되므로, 계획서는 S6을 S1보다 먼저 두었다.

필요 권한: https://www.googleapis.com/auth/webmasters.readonly
    → Blogger·애드센스 토큰에는 이 범위가 없다. **별도 refresh token**이 필요하며
      해당 사이트가 Search Console에 **속성으로 등록·소유 확인**되어 있어야 한다.

주의: 구글 Indexing API는 JobPosting/BroadcastEvent 전용이라 일반 글에 쓰면
      정책 위반이다. 여기서는 조회 전용 API만 쓴다.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import httpx

from ...core.logger import get_logger

logger = get_logger("index_check", "app.log")

INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
TIMEOUT = 30.0

# system_settings 키 — Tally·Blogger 자격증명과 같은 자리에 보관한다.
SETTING_GSC_REFRESH_TOKEN = "gsc_refresh_token"

# 판정 결과
VERDICT_PASS = "PASS"


class IndexCheckError(Exception):
    """색인 점검 호출 실패."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def property_url(blog: Any) -> Optional[str]:
    """Search Console 속성 주소를 만든다.

    도메인 속성(`sc-domain:`)이 아니라 URL 접두어 속성을 가정한다. 사용자가
    도메인 속성으로 등록했다면 설정에서 직접 지정할 수 있어야 하지만, 우선은
    블로그 URL의 origin 을 그대로 쓴다.
    """
    raw = (getattr(blog, "url", "") or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    if not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.hostname}/"


async def inspect_url(
    access_token: str, url: str, site_url: str,
) -> Dict[str, Any]:
    """URL 1건의 색인 상태를 조회한다.

    Args:
        access_token: webmasters.readonly 범위를 가진 access token
        url: 점검할 발행 URL
        site_url: Search Console 속성 주소

    Returns:
        API 응답의 `inspectionResult` 딕셔너리

    Raises:
        IndexCheckError: 4xx/5xx 응답
    """
    payload = {"inspectionUrl": url, "siteUrl": site_url, "languageCode": "ko"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            INSPECT_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.error("[INDEX_CHECK] %s → %s | %s", url, response.status_code, detail)
        raise IndexCheckError(
            f"색인 점검 오류 {response.status_code}: {detail}", response.status_code,
        )
    return (response.json() or {}).get("inspectionResult") or {}


def interpret(result: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """API 응답을 (색인됨 여부, 저장할 요약)으로 해석한다."""
    index_status = result.get("indexStatusResult") or {}
    verdict = index_status.get("verdict")
    detail = {
        "verdict": verdict,
        "coverageState": index_status.get("coverageState"),
        "lastCrawlTime": index_status.get("lastCrawlTime"),
        "robotsTxtState": index_status.get("robotsTxtState"),
        "indexingState": index_status.get("indexingState"),
        "pageFetchState": index_status.get("pageFetchState"),
    }
    return verdict == VERDICT_PASS, detail
