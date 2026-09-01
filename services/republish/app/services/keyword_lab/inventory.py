"""재고 목표치 산정 — 상수가 아니라 **소진 속도**로 정한다.

지금까지는 "재고 30개 넘으면 안 돈다" 는 고정 상수였다. 하루 5편 쓰는
블로그와 30편 쓰는 블로그의 필요 재고가 같을 리 없다.

목표재고 = max(모듈 하한, 일일 발행수 × 리드타임 × 안전계수)

일일 발행수는 성장 프로파일 설정이 아니라 **최근 실제 발행 실적**으로 잰다.
설정은 의도이고 실적은 사실이다. 스케줄이 밀리거나 발행이 실패하면 설정값은
현실과 벌어진다.

재고를 세는 기준은 `InventoryTrigger.count_available_titles` 하나만 쓴다.
세는 쪽과 꺼내는 쪽이 다르면 못 쓰는 제목을 재고로 세게 된다(검토서 D-5).

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Optional

import pytz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.publish_log import PublishLog

logger = get_logger("keyword_inventory", "app.log")

# 발행 실적을 볼 기간(일). 짧으면 하루 쉰 것에 흔들리고, 길면 최근 증속을
# 못 따라간다.
OBSERVE_DAYS = 14

# 며칠치를 미리 들고 있을지. 키워드 수집은 API 한도가 있어 하루치만 들고
# 있으면 한 번 실패했을 때 바로 굶는다.
DEFAULT_LEAD_TIME_DAYS = 3

# 안전계수. 제목이 전부 쓰이는 것은 아니다(중복·매칭 실패로 일부는 남는다).
DEFAULT_SAFETY_FACTOR = 1.5


async def daily_publish_rate(db: AsyncSession, blog_id: int,
                             days: int = OBSERVE_DAYS) -> float:
    """최근 며칠간의 하루 평균 발행 수(실적).

    Args:
        db: DB 세션
        blog_id: 블로그 ID
        days: 관찰 기간(일)

    Returns:
        하루 평균 발행 수. 실적이 없으면 0.0
    """
    since = datetime.now(pytz.timezone("Asia/Seoul")) - timedelta(days=days)
    count = (await db.execute(
        select(func.count(PublishLog.id)).where(
            PublishLog.blog_id == blog_id,
            PublishLog.action == "publish",
            PublishLog.status == "success",
            PublishLog.created_at >= since,
        )
    )).scalar() or 0
    return round(count / max(1, days), 3)


async def target_inventory(
    db: AsyncSession, blog: Any, cfg: Any,
    lead_days: int = DEFAULT_LEAD_TIME_DAYS,
    safety: float = DEFAULT_SAFETY_FACTOR,
) -> int:
    """이 블로그가 들고 있어야 할 제목 수.

    Args:
        db: DB 세션
        blog: 대상 블로그(None 이면 모듈 하한을 그대로 쓴다)
        cfg: 키워드 모듈 설정(min_inventory 를 하한으로 쓴다)
        lead_days: 며칠치를 비축할지
        safety: 안전계수

    Returns:
        목표 재고 수
    """
    floor = max(0, int(getattr(cfg, "min_inventory", 0) or 0))
    if blog is None:
        return floor

    rate = await daily_publish_rate(db, blog.id)
    if rate <= 0:
        # 아직 발행 실적이 없는 블로그. 하한만 지킨다.
        return floor

    target = math.ceil(rate * lead_days * safety)
    logger.info(
        "[KEYWORD_INVENTORY] blog=%s | 일일발행 %.2f × %d일 × %.1f → 목표 %d "
        "(하한 %d)", blog.id, rate, lead_days, safety, target, floor,
    )
    return max(floor, target)


async def available_titles(db: AsyncSession, blog: Any,
                           module_settings: Optional[dict] = None) -> int:
    """이 블로그가 꺼내 쓸 수 있는 제목 수.

    생성이 제목을 고르는 조건과 **같은 함수**를 쓴다.
    """
    if blog is None:
        from ...models.title import MainTitle

        return (await db.execute(
            select(func.count(MainTitle.id)).where(
                MainTitle.status == "available")
        )).scalar() or 0

    from ..generation.inventory_trigger import InventoryTrigger

    return await InventoryTrigger(db).count_available_titles(
        blog.id, module_settings)
