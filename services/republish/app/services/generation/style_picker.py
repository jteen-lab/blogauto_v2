"""제목 스타일 선택 — 성과가 좋았던 쪽에 무게를 준다.

`random.choice(styles)` 로 고르면서 **어떤 스타일을 썼는지 남기지 않아**
5개를 굴리며 아무것도 배우지 못했다. 이제 `generation_histories.title_style`
에 기록되므로 실측과 대조할 수 있다.

무작위를 없애지는 않는다. 한 스타일로 고정하면 그 스타일이 통하지 않는
글에서도 계속 쓰게 되고, 다른 스타일의 성과를 다시는 알 수 없다
(탐색이 죽는다). **무게만 준다.**

계획서: docs/plans/title_tab_workplan.md §4-5 A
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("style_picker", "app.log")

# 성과를 볼 기간(일)
LOOKBACK_DAYS = 60

# 표본이 이보다 적은 스타일은 판단하지 않는다 — 1건 성공을 100%로 읽으면
# 그 스타일만 계속 뽑힌다.
MIN_SAMPLE = 5

# 성과를 모르는 스타일에 주는 기본 무게. 0 으로 두면 새 스타일이 영원히
# 안 뽑혀 탐색이 죽는다.
BASE_WEIGHT = 1.0

# 성과가 좋아도 이 배수를 넘지 않는다. 한 스타일이 판을 독점하면 탐색이
# 사라진다.
MAX_WEIGHT = 3.0


async def pick(db: AsyncSession, styles: List[str],
               blog_id: Optional[int] = None,
               rng: Any = None) -> Optional[str]:
    """스타일 하나를 고른다. 후보가 없으면 None."""
    candidates = [s for s in (styles or []) if s]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    weights = await weigh(db, candidates, blog_id)
    chooser = rng or random
    return chooser.choices(candidates,
                           weights=[weights[s] for s in candidates], k=1)[0]


async def weigh(db: AsyncSession, styles: List[str],
                blog_id: Optional[int] = None) -> Dict[str, float]:
    """스타일별 무게. 실측이 없으면 전부 같은 무게다."""
    base = {s: BASE_WEIGHT for s in styles}
    try:
        stats = await performance(db, blog_id)
    except Exception as e:  # noqa: BLE001
        # 통계 실패로 생성이 멈추면 안 된다
        logger.warning("[STYLE] 성과 조회 실패 | %s", e)
        return base

    scored = {s: v for s, v in stats.items()
              if s in base and v["count"] >= MIN_SAMPLE}
    if not scored:
        return base

    average = sum(v["score"] for v in scored.values()) / len(scored)
    if average <= 0:
        return base

    for style, value in scored.items():
        ratio = value["score"] / average
        base[style] = max(0.2, min(MAX_WEIGHT, ratio))
    logger.info("[STYLE] 무게 | %s",
                {k: round(v, 2) for k, v in base.items()})
    return base


async def performance(db: AsyncSession,
                      blog_id: Optional[int] = None,
                      days: int = LOOKBACK_DAYS) -> Dict[str, Dict[str, Any]]:
    """스타일별 실측 성과.

    지표는 **색인률**이다 — 발행한 글이 검색엔진에 잡혔는가
    (`search_visibility_urls.index_state='indexed'`).

    노출수(impressions)를 쓰는 편이 더 정확하지만 그 컬럼이 아직 없다.
    색인은 노출의 전제이므로 대리 지표로 성립한다. 노출 수집이 붙으면
    **이 함수만** 바꾸면 된다 — 호출부는 그대로다.
    """
    from ...models.generation_history import GenerationHistory
    from ...models.search_visibility import IX_INDEXED, SearchVisibilityUrl

    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    indexed = func.sum(
        case((SearchVisibilityUrl.index_state == IX_INDEXED, 1), else_=0))
    query = (
        select(GenerationHistory.title_style,
               func.count(GenerationHistory.id),
               func.coalesce(indexed, 0))
        .select_from(GenerationHistory)
        .outerjoin(SearchVisibilityUrl,
                   SearchVisibilityUrl.crawled_post_id ==
                   GenerationHistory.crawling_post_id)
        .where(GenerationHistory.title_style.is_not(None),
               GenerationHistory.created_at >= since)
        .group_by(GenerationHistory.title_style))
    if blog_id:
        query = query.where(GenerationHistory.blog_id == blog_id)

    rows = (await db.execute(query)).all()
    out: Dict[str, Dict[str, Any]] = {}
    for style, count, hits in rows:
        count = int(count or 0)
        if not count:
            continue
        out[style] = {"count": count, "indexed": int(hits or 0),
                      "score": float(hits or 0) / count}
    return out
