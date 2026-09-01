"""구글 키워드플래너·트렌드 어댑터.

두 서비스는 이미 프로젝트에 있는데(`google_keyword_planner_service`,
`google_trends_service`) 키워드 모듈이 한 줄도 쓰지 않았다. 여기서 공통
형태(KeywordIdea)로 옮겨 붙인다.

**플래너 검색량은 구간값이다.** 활성 광고 캠페인이 없으면 "1천~1만" 처럼
넓은 범위로만 나오고, 유사 키워드를 묶어 합산해 보여 준다. 그래서
`volume_is_range=True` 로 표시하고 **정렬·필터 용도로만** 쓴다. 하한·상한
같은 절대 기준은 네이버 지표나 서치콘솔 실측에 건다.

**트렌드는 절대 검색량이 아니다.** 상대 관심도(0~100)라 검색량 칸을 비운다.

계획서: docs/plans/keyword_module_redesign_plan.md §4-1
"""
from __future__ import annotations

from typing import Any, List, Optional

from ....core.logger import get_logger
from .base import (
    SRC_GOOGLE_PLANNER, SRC_GOOGLE_TRENDS, KeywordIdea, normalize,
)

logger = get_logger("keyword_google", "app.log")

# 플래너·트렌드 모두 시드 5개까지 받는다.
SEED_CHUNK = 5

# 플래너 경쟁도 → 우리 표기
COMPETITION_LABEL = {"LOW": "낮음", "MEDIUM": "중간", "HIGH": "높음"}


async def planner_ideas(settings: Any, seeds: List[str],
                        limit: int = 200) -> List[KeywordIdea]:
    """키워드플래너 아이디어.

    Args:
        settings: UserSettings(구글 Ads 자격증명)
        seeds: 시드 키워드
        limit: 최대 결과 수

    Returns:
        키워드 아이디어 목록. 미설정이면 빈 목록.
    """
    from ...google_keyword_planner_service import GoogleKeywordPlannerService

    service = GoogleKeywordPlannerService(settings)
    if not service.is_configured():
        logger.info("[GOOGLE_PLANNER] 미설정 — 건너뜀")
        return []

    out: List[KeywordIdea] = []
    for chunk in _chunks(seeds, SEED_CHUNK):
        result = await service.get_keyword_ideas(chunk)
        if not result.get("success"):
            logger.warning("[GOOGLE_PLANNER] 조회 실패 | %s",
                           result.get("error"))
            continue
        for row in result.get("keywords") or []:
            idea = _planner_row(row, chunk[0])
            if idea:
                out.append(idea)
            if len(out) >= limit:
                return out
    return out


async def trends_related(seeds: List[str],
                         limit: int = 100) -> List[KeywordIdea]:
    """구글 트렌드 연관·급상승 검색어.

    검색량이 아니라 상대 관심도라 검색량 칸은 비워 둔다. 급상승은
    시의성 소재로 값지므로 extra 에 표시를 남긴다.
    """
    from ...google_trends_service import GoogleTrendsService

    service = GoogleTrendsService()
    out: List[KeywordIdea] = []
    for chunk in _chunks(seeds, SEED_CHUNK):
        try:
            result = await service.get_related_queries(chunk)
        except Exception as e:  # noqa: BLE001
            logger.warning("[GOOGLE_TRENDS] 조회 실패 | %s", e)
            continue
        if not result.get("success"):
            continue
        rows = [(r, False) for r in result.get("keywords") or []]
        rows += [(r, True) for r in result.get("rising_keywords") or []]
        for row, rising in rows:
            idea = _trends_row(row, rising)
            if idea:
                out.append(idea)
            if len(out) >= limit:
                return out
    return out


def _planner_row(row: dict, seed: str) -> Optional[KeywordIdea]:
    keyword = normalize(row.get("keyword", ""))
    if not keyword:
        return None
    volume = row.get("avg_monthly_searches")
    return KeywordIdea(
        keyword=keyword, source=SRC_GOOGLE_PLANNER, engine="google",
        search_volume=int(volume) if volume else None,
        competition=COMPETITION_LABEL.get(row.get("competition")),
        # 플래너 수치는 구간값이다. 절대 기준으로 쓰지 말 것.
        volume_is_range=True, seed=seed,
        extra={"competition_index": row.get("competition_index")},
    )


def _trends_row(row: dict, rising: bool) -> Optional[KeywordIdea]:
    keyword = normalize(row.get("keyword", ""))
    if not keyword:
        return None
    return KeywordIdea(
        keyword=keyword, source=SRC_GOOGLE_TRENDS, engine="google",
        seed=row.get("source_keyword"),
        extra={"rising": rising,
               "trend_score": row.get("trend_score"),
               "rising_percent": row.get("rising_percent")},
    )


def _chunks(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]
