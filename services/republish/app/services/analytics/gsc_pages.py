"""서치콘솔 — **글 단위** 노출·클릭·순위.

기존 `keyword_lab/sources/gsc.py` 는 사이트 전체의 검색어를 모은다(키워드 발굴).
여기는 URL 하나하나가 어떤 성적을 냈는지를 본다(재발행 판정).
호출 대상 API 는 같고 dimensions 만 다르다.

**추가 인증이 필요 없다.** 색인 점검이 이미 webmasters.readonly 토큰을 갖고 있다.

계획서: docs/plans/analytics_integration_plan.md §4
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List
from urllib.parse import quote

import httpx

from ...core.logger import get_logger

logger = get_logger("gsc_pages", "app.log")

QUERY_URL = ("https://www.googleapis.com/webmasters/v3/sites/"
             "{site}/searchAnalytics/query")
TIMEOUT = 30.0

# 서치콘솔 데이터는 2~3일 지연된다
LAG_DAYS = 3
DEFAULT_ROW_LIMIT = 5000


async def fetch_pages(access_token: str, site_url: str, days: int = 28,
                      row_limit: int = DEFAULT_ROW_LIMIT,
                      ) -> List[Dict[str, Any]]:
    """날짜·페이지별 클릭·노출·평균순위.

    Returns:
        [{"date": "2026-09-01", "url": "https://...",
          "clicks": 3, "impressions": 120, "position": 12.4}]
    """
    rows = await _query(access_token, site_url, ["date", "page"], days,
                        row_limit)
    out: List[Dict[str, Any]] = []
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        out.append({
            "date": keys[0],
            "url": keys[1],
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "position": round(float(row.get("position") or 0), 1),
        })
    return out


async def fetch_queries_for_page(access_token: str, site_url: str,
                                 page_url: str, days: int = 28,
                                 row_limit: int = 100,
                                 ) -> List[Dict[str, Any]]:
    """**이 글이 실제로 노출된 검색어.**

    니즈 갭의 재료다. 사람들이 이 질문을 갖고 우리 글에 왔다는 증거이므로,
    본문이 그 답을 안 담고 있으면 그것이 채울 자리다. AlsoAsked 같은 도구가
    추정하는 것을 우리는 실측으로 갖고 있다.

    Returns:
        [{"query": "전기차 충전요금", "clicks": 0, "impressions": 40,
          "position": 14.2}]
    """
    rows = await _query(
        access_token, site_url, ["query"], days, row_limit,
        dimension_filter={
            "filters": [{
                "dimension": "page",
                "operator": "equals",
                "expression": page_url,
            }],
        })
    out: List[Dict[str, Any]] = []
    for row in rows:
        keys = row.get("keys") or []
        if not keys:
            continue
        out.append({
            "query": keys[0],
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "position": round(float(row.get("position") or 0), 1),
        })
    return out


async def _query(access_token: str, site_url: str, dimensions: List[str],
                 days: int, row_limit: int,
                 dimension_filter: Dict[str, Any] = None) -> List[dict]:
    """공통 호출. 실패는 빈 목록이다 — 한 블로그 때문에 회차가 멈추면 안 된다."""
    end = date.today() - timedelta(days=LAG_DAYS)
    body: Dict[str, Any] = {
        "startDate": (end - timedelta(days=days)).isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    if dimension_filter:
        body["dimensionFilterGroups"] = [dimension_filter]

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                QUERY_URL.format(site=quote(site_url, safe="")),
                headers={"Authorization": f"Bearer {access_token}"},
                json=body)
    except Exception as e:  # noqa: BLE001
        logger.warning("[GSC_PAGES] 호출 실패 | %s | %s", site_url, e)
        return []

    if response.status_code != 200:
        logger.warning("[GSC_PAGES] HTTP %s | %s | %s", response.status_code,
                       site_url, response.text[:160])
        return []
    return (response.json() or {}).get("rows") or []
