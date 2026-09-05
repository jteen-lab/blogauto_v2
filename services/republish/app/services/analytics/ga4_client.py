"""GA4 Data API — 우리 글에 **실제로 들어온 사람** 수.

서치콘솔은 검색에 몇 번 보였는지를 알려 준다. 그 다음이 비어 있었다.
보인 것과 읽힌 것은 다르다. 노출이 유지돼도 사람이 안 들어오면 그 글은
죽어 가는 중이고, 반대로 노출이 줄어도 들어온 사람이 오래 머물면 급하지 않다.

**추가 인증 체계를 만들지 않는다.** 서치콘솔이 쓰는 refresh token 저장·갱신
구조를 그대로 쓴다. 범위만 analytics.readonly 로 다르다.

전제: 블로그마다 GA4 속성이 따로 있고, Blogger 설정에 측정 ID(G-...)가
    들어가 있어야 한다. 미연결 블로그는 조용히 빈 결과를 돌려준다.

계획서: docs/plans/analytics_integration_plan.md §3
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from ...core.logger import get_logger

logger = get_logger("ga4_client", "app.log")

SETTING_GA4_REFRESH_TOKEN = "ga4_refresh_token"

REQUIRED_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
ADMIN_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
DATA_URL = ("https://analyticsdata.googleapis.com/v1beta/"
            "properties/{property_id}:runReport")
TIMEOUT = 30.0

# GA4 는 당일치가 확정 전이다. 어제 것을 읽으면 값이 계속 흔들린다.
LAG_DAYS = 3

# 한 번에 받을 행 수. 블로그 하나의 하루치 방문 페이지가 이보다 많기는 어렵다.
DEFAULT_ROW_LIMIT = 5000


class Ga4Error(Exception):
    """GA4 API 오류. status_code 로 원인을 구분한다."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def granted_scopes(access_token: str) -> List[str]:
    """토큰에 실제로 부여된 범위.

    403 은 원인을 알려주지 않는다. 서치콘솔 토큰을 잘못 넣는 일이 흔해,
    무엇이 들어 있는지 보여줘야 사용자가 스스로 고친다.
    """
    from ..search_visibility.index_check_service import granted_scopes as gs

    return await gs(access_token)


async def list_properties(access_token: str) -> List[Dict[str, str]]:
    """이 토큰으로 볼 수 있는 GA4 속성 목록.

    Returns:
        [{"property_id": "123456789", "display_name": "카인포노트",
          "account": "..."}]
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            ADMIN_URL, headers={"Authorization": f"Bearer {access_token}"},
            params={"pageSize": 200},
        )
    if response.status_code >= 400:
        raise Ga4Error(
            f"속성 목록 조회 실패 {response.status_code}: "
            f"{response.text[:200]}", response.status_code)

    out: List[Dict[str, str]] = []
    for account in (response.json() or {}).get("accountSummaries") or []:
        account_name = account.get("displayName") or ""
        for prop in account.get("propertySummaries") or []:
            # "properties/123456789" 에서 숫자만 쓴다
            raw = prop.get("property") or ""
            pid = raw.split("/")[-1]
            if pid:
                out.append({
                    "property_id": pid,
                    "display_name": prop.get("displayName") or pid,
                    "account": account_name,
                })
    return out


async def fetch_landing_pages(
    access_token: str, property_id: str, days: int = 28,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> List[Dict[str, Any]]:
    """날짜·방문 페이지별 세션 지표.

    `landingPage` 는 **경로만** 준다(`/2026/09/foo.html`). 전체 URL 로 맞추는
    일은 부르는 쪽(url_match)이 한다 — 여기서 호스트를 붙이면 도메인 속성과
    URL 속성의 차이를 이 모듈이 알아야 한다.

    Args:
        access_token: analytics.readonly 범위 토큰
        property_id: GA4 속성 번호(숫자만)
        days: 조회 기간(일)
        row_limit: 최대 행 수

    Returns:
        [{"date": "2026-09-01", "path": "/2026/09/foo.html",
          "sessions": 12, "engaged_sessions": 8, "avg_duration": 74.2}]
    """
    end = date.today() - timedelta(days=LAG_DAYS)
    body = {
        "dateRanges": [{
            "startDate": (end - timedelta(days=days)).isoformat(),
            "endDate": end.isoformat(),
        }],
        "dimensions": [{"name": "date"}, {"name": "landingPage"}],
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                    {"name": "averageSessionDuration"}],
        "limit": row_limit,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            DATA_URL.format(property_id=property_id),
            headers={"Authorization": f"Bearer {access_token}"}, json=body,
        )
    if response.status_code >= 400:
        raise Ga4Error(
            f"GA4 조회 실패 {response.status_code}: {response.text[:200]}",
            response.status_code)

    return _parse_rows((response.json() or {}).get("rows") or [])


def _parse_rows(rows: List[dict]) -> List[Dict[str, Any]]:
    """runReport 응답을 평평한 dict 로.

    지표가 비면 0 으로 둔다. GA4 는 값이 없는 칸을 빈 문자열로 준다.
    """
    out: List[Dict[str, Any]] = []
    for row in rows:
        dims = [d.get("value") or "" for d in row.get("dimensionValues") or []]
        vals = [m.get("value") or "" for m in row.get("metricValues") or []]
        if len(dims) < 2 or len(vals) < 3:
            continue
        raw_date, path = dims[0], dims[1]
        # GA4 는 날짜를 YYYYMMDD 로 준다
        if len(raw_date) == 8 and raw_date.isdigit():
            raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        out.append({
            "date": raw_date,
            "path": path,
            "sessions": _int(vals[0]),
            "engaged_sessions": _int(vals[1]),
            "avg_duration": _float(vals[2]),
        })
    return out


def _int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: str) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


async def resolve_token(db) -> Optional[str]:
    """저장된 refresh token 으로 access token 을 얻는다.

    서치콘솔과 **같은 방식**이다. 다른 방식을 쓰면 한쪽만 만료되는 일이 생긴다.
    """
    from ...core.encryption import decrypt_api_key
    from ..publishing.google_oauth_helper import refresh_access_token
    from ..system_settings_service import SystemSettingsService

    encrypted = await SystemSettingsService.get(SETTING_GA4_REFRESH_TOKEN, db)
    if not encrypted:
        return None
    try:
        refresh_token = decrypt_api_key(encrypted)
    except Exception:  # noqa: BLE001
        logger.error("[GA4] refresh token 복호화 실패")
        return None
    return await refresh_access_token(refresh_token)
