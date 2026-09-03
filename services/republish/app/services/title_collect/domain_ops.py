"""도메인 단위 정리 — 삭제 누계 추적과 차단.

**목적은 수작업 보조다.** 결이 맞지 않는 도메인의 제목을 여러 페이지 넘겨
가며 하나씩 지우지 않기 위한 도구다. 자동 삭제가 아니다.

**비율(%) 기준을 쓰지 않는 이유**: 제목이 100건인 도메인에서 30건을 지워야
반응하게 된다. 운영자는 보통 3~5건만 봐도 결이 다름을 안다. 그때 물어야
한다. 그래서 **횟수만** 본다.

삭제 누계는 세션이 아니라 **DB 에 쌓는다.** 오늘 3건, 내일 3건을 지워도
임계에 걸려야 한다.

계획서: docs/plans/title_tab_workplan.md §2-3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.niche_domain import EXTRACT_BLOCKED, NicheDomain
from ...models.title import TempTitle

logger = get_logger("title_domain_ops", "app.log")

# 사용자가 조정할 수 있는 범위. 3보다 낮으면 오탐이 잦고, 20을 넘으면
# 이 기능을 만든 이유(페이지 넘기며 지우기 싫다)가 사라진다.
DEFAULT_THRESHOLD = 5
MIN_THRESHOLD = 3
MAX_THRESHOLD = 20

BLOCK_REASON_BULK = "제목 대량 삭제"
BLOCK_REASON_MANUAL = "수동 차단"


def clamp_threshold(value: Any) -> int:
    """임계값을 안전한 범위로."""
    try:
        number = int(value) if value not in (None, "") else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, number))


async def record_deletions(db: AsyncSession, user_id: int,
                           domains: Dict[str, int],
                           threshold: int = DEFAULT_THRESHOLD,
                           ) -> List[Dict[str, Any]]:
    """삭제 누계를 도메인에 쌓고, 임계를 넘은 것을 돌려준다.

    Returns:
        [{"domain": str, "deleted": int, "remaining": int, "id": int}]
        화면이 이 목록으로 팝업을 띄운다.
    """
    limit = clamp_threshold(threshold)
    hits: List[Dict[str, Any]] = []

    for host, count in domains.items():
        row = (await db.execute(
            select(NicheDomain).where(NicheDomain.user_id == user_id,
                                      NicheDomain.domain == host)
        )).scalar_one_or_none()
        if row is None:
            continue

        row.deleted_title_count = (row.deleted_title_count or 0) + count
        if row.deleted_title_count < limit or row.is_blocked:
            continue

        remaining = await count_titles(db, host)
        hits.append({"id": row.id, "domain": host,
                     "deleted": row.deleted_title_count,
                     "remaining": remaining})

    await db.commit()
    if hits:
        logger.info("[DOMAIN_OPS] 임계 초과 %d개 | 기준 %d회",
                    len(hits), limit)
    return hits


async def count_titles(db: AsyncSession, domain: str) -> int:
    """이 도메인에서 온 임시제목 수."""
    return (await db.execute(
        select(func.count()).select_from(TempTitle).where(
            TempTitle.source_post_url.ilike(f"%{domain}%"))
    )).scalar() or 0


async def list_titles(db: AsyncSession, domain: str,
                      limit: int = 500) -> List[Dict[str, Any]]:
    """팝업에 뿌릴 남은 제목. 한 화면에서 다 보고 고를 수 있어야 한다."""
    rows = (await db.execute(
        select(TempTitle)
        .where(TempTitle.source_post_url.ilike(f"%{domain}%"))
        .order_by(TempTitle.created_at.desc())
        .limit(max(1, limit))
    )).scalars().all()
    return [{"id": r.id, "title": r.title,
             "topic_id": r.topic_id,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


async def delete_titles(db: AsyncSession, ids: List[int]) -> int:
    """고른 제목만 지운다."""
    if not ids:
        return 0
    result = await db.execute(delete(TempTitle).where(TempTitle.id.in_(ids)))
    await db.commit()
    return result.rowcount or 0


async def purge_domain(db: AsyncSession, user_id: int, domain: str,
                       block: bool = True) -> Dict[str, Any]:
    """도메인의 제목을 모두 지우고, 원하면 재수집을 차단한다.

    차단은 `is_blocked` 다. `is_active`(각도 조회 참조)와 축이 다르므로
    건드리지 않는다 — 합치면 각도를 끄려다 재수집까지 막힌다.
    """
    removed = (await db.execute(
        delete(TempTitle).where(
            TempTitle.source_post_url.ilike(f"%{domain}%")))).rowcount or 0

    row = (await db.execute(
        select(NicheDomain).where(NicheDomain.user_id == user_id,
                                  NicheDomain.domain == domain)
    )).scalar_one_or_none()

    if row is not None and block:
        row.is_blocked = True
        row.blocked_reason = BLOCK_REASON_BULK
        row.blocked_at = func.now()
        row.extract_status = EXTRACT_BLOCKED

    await db.commit()
    logger.info("[DOMAIN_OPS] %s 제목 %d건 삭제 | 차단=%s",
                domain, removed, block)
    return {"deleted": removed, "blocked": bool(row is not None and block)}


async def unblock(db: AsyncSession, user_id: int,
                  domain_id: int) -> Optional[NicheDomain]:
    """차단 해제. 다시 수집·추출 대상이 된다."""
    from ...models.niche_domain import EXTRACT_PENDING

    row = (await db.execute(
        select(NicheDomain).where(NicheDomain.id == domain_id,
                                  NicheDomain.user_id == user_id)
    )).scalar_one_or_none()
    if row is None:
        return None
    row.is_blocked = False
    row.blocked_reason = None
    row.blocked_at = None
    row.extract_status = EXTRACT_PENDING
    row.deleted_title_count = 0
    await db.commit()
    return row
