"""소스 디스패치와 검색량 보강.

두 가지 일을 한다.

1. **모으기** — 모듈이 켠 소스에서 키워드를 모은다. 소스 하나가 실패해도
   회차를 죽이지 않는다. 실패는 사유와 함께 올려 화면이 말해 줄 수 있게 한다.
2. **보강** — 자동완성·트렌드·서치콘솔은 키워드만 주고 검색량이 없다.
   검색량 없는 후보는 판정이 영원히 pending 이므로, 네이버 검색광고로
   검색량을 채운다(한 번에 5개씩이라 호출이 크게 늘지 않는다).

계획서: docs/plans/keyword_module_redesign_plan.md §4-3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....core.logger import get_logger
from .base import (
    SRC_GOOGLE_PLANNER, SRC_GOOGLE_SUGGEST, SRC_GOOGLE_TRENDS, SRC_GSC,
    SRC_NAVER_SUGGEST, KeywordIdea, dedupe,
)

logger = get_logger("keyword_sources", "app.log")

# 검색광고는 한 번에 5개까지 받는다.
ADS_CHUNK = 5

# 한 회차에 보강할 최대 키워드 수. 호출 한도를 지킨다.
DEFAULT_ENRICH_LIMIT = 100


async def gather(
    db: Any, user_settings: Any, blog: Any, seeds: List[str],
    enabled: List[str], per_source_limit: int = 200,
) -> Dict[str, Any]:
    """켜진 소스에서 키워드를 모은다(검색광고 제외 — 그쪽은 본 서비스가 맡는다).

    Args:
        db: DB 세션(서치콘솔이 쓴다)
        user_settings: 사용자 설정(플래너 자격증명)
        blog: 대상 블로그(서치콘솔 속성 해석용). 없으면 서치콘솔은 건너뛴다.
        seeds: 확장된 시드 목록
        enabled: 켜진 소스 코드 목록
        per_source_limit: 소스당 최대 결과 수

    Returns:
        {"ideas": [KeywordIdea], "by_source": {코드: 개수}, "errors": [str]}
    """
    ideas: List[KeywordIdea] = []
    by_source: Dict[str, int] = {}
    errors: List[str] = []

    for code in enabled:
        try:
            found = await _run_source(
                code, db, user_settings, blog, seeds, per_source_limit)
        except Exception as e:  # noqa: BLE001
            # 소스 하나가 죽어도 나머지는 돈다.
            logger.warning("[KEYWORD_SOURCES] %s 실패 | %s", code, e)
            errors.append(f"{code}: {str(e)[:100]}")
            continue
        if found:
            ideas.extend(found)
        by_source[code] = len(found)

    merged = dedupe(ideas)
    logger.info("[KEYWORD_SOURCES] 소스 %d개 → %d개(중복 제거 %d)",
                len(enabled), len(merged), len(ideas) - len(merged))
    return {"ideas": merged, "by_source": by_source, "errors": errors}


async def _run_source(code: str, db: Any, user_settings: Any, blog: Any,
                      seeds: List[str], limit: int) -> List[KeywordIdea]:
    """소스 하나를 돌린다."""
    if code == SRC_NAVER_SUGGEST:
        from . import suggest

        return await suggest.collect(seeds, "naver")

    if code == SRC_GOOGLE_SUGGEST:
        from . import suggest

        return await suggest.collect(seeds, "google")

    if code == SRC_GOOGLE_PLANNER:
        from . import google_ads

        return await google_ads.planner_ideas(user_settings, seeds, limit)

    if code == SRC_GOOGLE_TRENDS:
        from . import google_ads

        return await google_ads.trends_related(seeds, limit)

    if code == SRC_GSC:
        if blog is None:
            return []
        from . import gsc

        return await gsc.collect_for_blog(db, blog, limit=limit)

    return []


async def enrich_volumes(user_settings: Any, ideas: List[KeywordIdea],
                         limit: int = DEFAULT_ENRICH_LIMIT,
                         ) -> Dict[str, Any]:
    """검색량 없는 아이디어에 네이버 검색광고 검색량을 채운다.

    자동완성·트렌드·서치콘솔은 키워드만 준다. 검색량이 없으면 판정이
    영원히 pending 이라 재고로 이어지지 않는다.

    Returns:
        {"filled": 채운 수, "api_calls": 호출 수, "errors": [...]}
    """
    from ...naver_ads_service import NaverAdsService

    targets = [i for i in ideas if i.search_volume is None][:limit]
    if not targets:
        return {"filled": 0, "api_calls": 0, "errors": []}

    service = NaverAdsService(user_settings)
    if not service.is_configured():
        return {"filled": 0, "api_calls": 0,
                "errors": ["검색광고 API 미설정 — 검색량 보강 못 함"]}

    index = {i.keyword.replace(" ", "").lower(): i for i in targets}
    filled, calls = 0, 0
    errors: List[str] = []

    for start in range(0, len(targets), ADS_CHUNK):
        chunk = [i.keyword for i in targets[start:start + ADS_CHUNK]]
        result = await service.get_keyword_stats(chunk, include_related=False)
        calls += 1
        if not result.get("success"):
            reason = result.get("error") or "검색량 조회 실패"
            if reason not in errors:
                errors.append(reason)
            continue
        filled += _apply_stats(index, result.get("keywords") or [])

    logger.info("[KEYWORD_SOURCES] 검색량 보강 %d/%d | API %d회",
                filled, len(targets), calls)
    return {"filled": filled, "api_calls": calls, "errors": errors}


def _apply_stats(index: Dict[str, KeywordIdea], rows: List[dict]) -> int:
    """조회 결과를 아이디어에 옮긴다."""
    filled = 0
    for row in rows:
        key = (row.get("keyword") or "").replace(" ", "").lower()
        idea = index.get(key)
        if idea is None or idea.search_volume is not None:
            continue
        idea.search_volume = row.get("total_search_volume")
        idea.search_volume_pc = row.get("pc_search_volume")
        idea.search_volume_mobile = row.get("mobile_search_volume")
        idea.competition = row.get("competition")
        idea.volume_is_range = False
        filled += 1
    return filled
