"""서치콘솔 실측 쿼리 — 우리 글이 **실제로 노출된** 검색어.

다른 소스는 전부 추정이다. 서치콘솔만 사실이다. 우리 블로그가 어떤 검색어에
노출됐고, 몇 번 보였고, 평균 몇 위였는지가 그대로 나온다. 프로그래매틱 SEO
문헌이 수식어 확장의 가장 신뢰할 수 있는 소스로 꼽는 것도 이것이다.

**추가 인증이 필요 없다.** 색인 점검이 이미 `webmasters.readonly` 범위의
refresh token 을 저장해 두었고, Search Analytics 는 같은 범위로 호출된다.

전제: 그 사이트가 Search Console 에 속성으로 등록·소유 확인되어 있어야 한다.
    미등록 블로그는 조용히 빈 목록을 돌려준다.

계획서: docs/plans/keyword_module_redesign_plan.md §4-2
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from ....core.logger import get_logger
from .base import SRC_GSC, KeywordIdea, normalize

logger = get_logger("keyword_gsc", "app.log")

QUERY_URL = ("https://www.googleapis.com/webmasters/v3/sites/"
             "{site}/searchAnalytics/query")
TIMEOUT = 30.0

# 조회 기간(일). 서치콘솔 데이터는 2~3일 지연된다.
DEFAULT_DAYS = 28

# 한 번에 받을 행 수
DEFAULT_ROW_LIMIT = 500

# 노출이 이보다 적은 쿼리는 잡음이다.
MIN_IMPRESSIONS = 3


async def fetch_queries(access_token: str, site_url: str,
                        days: int = DEFAULT_DAYS,
                        row_limit: int = DEFAULT_ROW_LIMIT,
                        ) -> List[Dict[str, Any]]:
    """사이트의 검색어별 노출·클릭·평균순위.

    Args:
        access_token: webmasters.readonly 범위 토큰
        site_url: Search Console 속성 URL
        days: 조회 기간(일)
        row_limit: 최대 행 수

    Returns:
        [{"query", "impressions", "clicks", "position"}, ...]
    """
    from urllib.parse import quote

    end = date.today() - timedelta(days=3)   # 데이터 지연 보정
    body = {
        "startDate": (end - timedelta(days=days)).isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": row_limit,
    }
    url = QUERY_URL.format(site=quote(site_url, safe=""))

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                url, headers={"Authorization": f"Bearer {access_token}"},
                json=body)
    except Exception as e:  # noqa: BLE001
        logger.warning("[GSC_QUERIES] 호출 실패 | %s | %s", site_url, e)
        return []

    if response.status_code != 200:
        logger.warning("[GSC_QUERIES] HTTP %s | %s | %s",
                       response.status_code, site_url, response.text[:160])
        return []

    rows = (response.json() or {}).get("rows") or []
    out = []
    for row in rows:
        keys = row.get("keys") or []
        if not keys:
            continue
        out.append({
            "query": keys[0],
            "impressions": int(row.get("impressions") or 0),
            "clicks": int(row.get("clicks") or 0),
            "position": round(float(row.get("position") or 0), 1),
        })
    logger.info("[GSC_QUERIES] %s | 쿼리 %d개", site_url, len(out))
    return out


def to_ideas(rows: List[Dict[str, Any]],
             min_impressions: int = MIN_IMPRESSIONS) -> List[KeywordIdea]:
    """실측 쿼리를 키워드 아이디어로.

    노출수는 검색량이 아니다(우리가 본 몫일 뿐이다). 그래서 검색량 칸을
    비워 두고 뒤의 보강 단계가 채우게 한다. 노출·순위는 되먹임에 쓰려고
    extra 에 남긴다.
    """
    out: List[KeywordIdea] = []
    for row in rows:
        if row.get("impressions", 0) < min_impressions:
            continue
        keyword = normalize(row.get("query", ""))
        if not keyword:
            continue
        out.append(KeywordIdea(
            keyword=keyword, source=SRC_GSC, engine="google",
            extra={"impressions": row["impressions"],
                   "clicks": row["clicks"],
                   "position": row["position"]},
        ))
    return out


async def collect_for_blog(db: Any, blog: Any, days: int = DEFAULT_DAYS,
                           limit: int = DEFAULT_ROW_LIMIT,
                           ) -> List[KeywordIdea]:
    """블로그 하나의 실측 쿼리를 모은다.

    토큰이 없거나 속성이 등록돼 있지 않으면 빈 목록이다. 그것은 오류가
    아니라 "이 블로그는 이 소스를 못 쓴다" 는 사실이다.
    """
    from ...search_visibility import index_check_service
    from ...search_visibility.runner import resolve_gsc_token

    token = await resolve_gsc_token(db)
    if not token:
        logger.info("[GSC_QUERIES] refresh token 없음 — 건너뜀")
        return []

    site_url = await _resolve_site(token, blog)
    if not site_url:
        logger.info("[GSC_QUERIES] 속성 미등록 — blog=%s",
                    getattr(blog, "id", None))
        return []

    rows = await fetch_queries(token, site_url, days, limit)
    return to_ideas(rows)


async def _resolve_site(token: str, blog: Any) -> Optional[str]:
    """블로그 도메인에 맞는 Search Console 속성을 찾는다."""
    from ...search_visibility import index_check_service

    try:
        sites = await index_check_service.list_sites(token)
    except Exception as e:  # noqa: BLE001
        logger.warning("[GSC_QUERIES] 속성 목록 실패 | %s", e)
        return None
    return index_check_service.resolve_property(sites, blog)
