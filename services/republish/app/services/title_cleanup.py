"""임시제목 정리 — 미분류·니치 무관을 걷어낸다.

배경(운영 실측 2026-09-02):
    `temp_titles` 105,004건 중 정식제목으로 올라간 것은 2% 뿐이었다.
    옛 파이프라인이 사이트맵을 통째로 긁어 니치와 무관한 제목까지 재고에
    넣었기 때문이다. 남겨 두면 유사도 검사와 목록 조회가 계속 느려지고,
    사람이 목록을 훑을 수도 없다.

정리 기준 두 가지:
    1. **미분류** — `topic_id` 가 없다. 어느 니치인지 모르는 제목은
       발행 대상으로 고를 수 없다.
    2. **니치 무관** — 분류는 됐지만 그 주제를 쓰는 블로그가 하나도 없다.

⚠️ 반드시 **재분류를 먼저 돌린 뒤** 정리한다. 분류표는 계속 자라므로
   지금 미분류인 것이 다음 재분류에서 붙을 수 있다. 그냥 지우면 살릴 수
   있는 것까지 버린다. 그래서 `preview()` 가 먼저고 삭제는 그 다음이다.

계획서: docs/plans/title_pipeline_redesign_plan.md §5 (B안)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.category import BlogCategory
from ..models.title import TempTitle

logger = get_logger("title_cleanup", "app.log")

# 정리 사유 코드
REASON_UNCLASSIFIED = "unclassified"
REASON_OFF_NICHE = "off_niche"
REASONS = (REASON_UNCLASSIFIED, REASON_OFF_NICHE)

REASON_LABEL = {
    REASON_UNCLASSIFIED: "미분류 (주제를 모름)",
    REASON_OFF_NICHE: "니치 무관 (그 주제를 쓰는 블로그가 없음)",
}


async def active_topics(db: AsyncSession) -> set:
    """블로그가 실제로 쓰는 주제 집합.

    비어 있으면 니치 판정을 하지 않는다 — 카테고리를 아직 안 붙인
    상태에서 전량 삭제되는 사고를 막는다.
    """
    rows = (await db.execute(
        select(BlogCategory.topic_id).where(
            BlogCategory.is_active.is_(True),
            BlogCategory.topic_id.is_not(None))
    )).scalars().all()
    return {t for t in rows if t}


def _condition(reason: str, topics: set):
    """사유별 대상 조건. 판정할 수 없으면 None."""
    if reason == REASON_UNCLASSIFIED:
        return TempTitle.topic_id.is_(None)
    if reason == REASON_OFF_NICHE:
        if not topics:
            # 쓰는 주제가 하나도 없으면 '무관' 을 정의할 수 없다.
            return None
        return TempTitle.topic_id.is_not(None) & \
            TempTitle.topic_id.not_in(list(topics))
    return None


async def preview(db: AsyncSession) -> Dict[str, Any]:
    """무엇이 얼마나 지워지는지 먼저 보여 준다. 삭제하지 않는다."""
    topics = await active_topics(db)
    total = (await db.execute(
        select(func.count()).select_from(TempTitle))).scalar() or 0

    counts: Dict[str, int] = {}
    for reason in REASONS:
        condition = _condition(reason, topics)
        if condition is None:
            counts[reason] = 0
            continue
        counts[reason] = (await db.execute(
            select(func.count()).select_from(TempTitle).where(condition)
        )).scalar() or 0

    removable = sum(counts.values())
    return {
        "total": total,
        "counts": counts,
        "labels": REASON_LABEL,
        "removable": removable,
        "keep": max(0, total - removable),
        "active_topics": len(topics),
        # 카테고리가 없으면 니치 판정을 건너뛴다는 사실을 화면이 말해야 한다
        "niche_check_skipped": not topics,
    }


async def cleanup(db: AsyncSession,
                  reasons: Optional[list] = None) -> Dict[str, Any]:
    """선택한 사유의 임시제목을 삭제한다.

    Args:
        db: DB 세션
        reasons: 지울 사유 목록. `None` 이면 둘 다.
                 **빈 목록은 "아무것도 고르지 않음" 이라 거부한다** —
                 화면에서 체크를 모두 끈 채 호출했을 때 전량 기준으로
                 지워지면 되돌릴 수 없다.

    Returns:
        사유별 삭제 건수와 합계.
    """
    candidates = REASONS if reasons is None else reasons
    picked = [r for r in candidates if r in REASONS]
    if not picked:
        return {"success": False, "error": "정리 사유를 고르세요", "deleted": 0}

    topics = await active_topics(db)
    deleted: Dict[str, int] = {}
    skipped: list = []

    for reason in picked:
        condition = _condition(reason, topics)
        if condition is None:
            skipped.append(reason)
            deleted[reason] = 0
            continue
        result = await db.execute(delete(TempTitle).where(condition))
        deleted[reason] = result.rowcount or 0

    await db.commit()
    total = sum(deleted.values())
    logger.info("[TITLE_CLEANUP] 삭제 %s건 | %s | 건너뜀 %s",
                total, deleted, skipped)
    return {"success": True, "deleted": total, "by_reason": deleted,
            "skipped": skipped, "labels": REASON_LABEL}
