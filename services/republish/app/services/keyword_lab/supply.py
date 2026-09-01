"""공급 측정 — 지금 경쟁이 붙고 있는지를 잰다.

누적 문서수는 10년치 총합이라 "이 자리가 지금 붐비는가" 를 말해 주지
않는다. 국내 키워드 도구들이 쓰는 축은 **최근 30일 발행량**이다.

네이버 검색 API 에는 기간 필터가 없다. 대신 `sort=date` 로 최신순 100건을
받아 그중 최근 30일 안에 들어오는 건수를 센다. 100건이 전부 30일 안이면
실제 발행량은 그 이상이라는 뜻이므로 **상한 도달(capped)** 로 표시한다.
"100건 이상" 은 그 자체로 충분한 신호다 — 이미 붐비는 자리다.

호출 비용: 키워드당 2회(누적 문서수 1 + 최신순 표본 1).

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ...core.logger import get_logger

logger = get_logger("keyword_supply", "app.log")

# 발행량을 볼 기간(일)
PUB_WINDOW_DAYS = 30

# 최신순 표본 크기. 네이버 검색 API 한 번에 받을 수 있는 최대치다.
PUB_SAMPLE_SIZE = 100

KST = pytz.timezone("Asia/Seoul")


def parse_postdate(value: Any) -> Optional[datetime]:
    """네이버 blog 검색의 postdate(YYYYMMDD)를 날짜로 바꾼다."""
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return None


def count_recent(items: List[dict], window_days: int = PUB_WINDOW_DAYS,
                 today: Optional[datetime] = None) -> Tuple[int, bool]:
    """표본에서 최근 N일 안에 발행된 건수와 상한 도달 여부.

    Args:
        items: 검색 결과 항목(postdate 포함)
        window_days: 기간(일)
        today: 기준일(테스트용). 없으면 오늘(KST)

    Returns:
        (건수, 상한도달여부) — 표본을 전부 채웠으면 상한도달
    """
    base = (today or datetime.now(KST)).replace(tzinfo=None)
    since = base - timedelta(days=window_days)

    fresh = 0
    for item in items or []:
        posted = parse_postdate(item.get("postdate"))
        if posted is None:
            continue
        if posted >= since:
            fresh += 1

    capped = bool(items) and fresh >= len(items) >= PUB_SAMPLE_SIZE
    return fresh, capped


async def measure_supply(search_service: Any, keyword: str,
                         window_days: int = PUB_WINDOW_DAYS) -> Dict[str, Any]:
    """한 키워드의 공급 지표를 잰다.

    Args:
        search_service: NaverSearchService
        keyword: 키워드
        window_days: 발행량을 볼 기간(일)

    Returns:
        {"success": bool, "doc_count": int|None,
         "monthly_pub_count": int|None, "capped": bool, "error": str|None}
    """
    out: Dict[str, Any] = {"success": False, "doc_count": None,
                           "monthly_pub_count": None, "capped": False,
                           "error": None}

    total = await search_service.search_blog(keyword, display=1)
    if not total.get("success"):
        out["error"] = total.get("error") or "문서수 조회 실패"
        return out
    out["doc_count"] = int(total.get("total") or 0)
    out["success"] = True

    recent = await search_service.search_blog(
        keyword, display=PUB_SAMPLE_SIZE, sort="date")
    if not recent.get("success"):
        # 누적 문서수는 받았다. 발행량만 못 잰 것이므로 실패로 보지 않는다.
        logger.warning("[KEYWORD_SUPPLY] 발행량 표본 실패 | %s | %s",
                       keyword, recent.get("error"))
        return out

    fresh, capped = count_recent(recent.get("items") or [], window_days)
    out["monthly_pub_count"] = fresh
    out["capped"] = capped
    return out
