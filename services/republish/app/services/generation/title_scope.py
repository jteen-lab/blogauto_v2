"""어느 제목을 어느 블로그가 쓸 수 있나.

CPA 제목이 일반 재고에 섞여 있다. 격리하지 않으면 애드센스 블로그가
오퍼 규칙이 붙은 글을 발행한다(2026-09-09에 그 직전까지 갔다).

두 가지를 동시에 만족해야 한다.

    일반 블로그   CPA 제목을 하나도 못 뽑는다
    담당 블로그   그 오퍼의 제목만, **카테고리와 무관하게** 뽑는다

카테고리를 건너뛰는 이유: CPA 제목에는 주제·하위주제가 없다. 오퍼가 곧
주제이고, 오퍼를 블로그에 붙인 순간 그 블로그가 무엇을 쓸지 정해진다.

순서도: docs/flowcharts/cpa_offer.md
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.title import MainTitle

logger = get_logger("title_scope", "app.log")


async def owned_offer_ids(db: AsyncSession, blog_id: int) -> List[int]:
    """이 블로그가 담당하는, **지금 쓸 수 있는** CPA 오퍼.

    확인 전이거나 재확인 기한이 지난 오퍼의 제목을 뽑으면 생성기가 다시
    막아 헛돈다. 여기서 걸러 준다.

    Args:
        db: DB 세션
        blog_id: 블로그 ID

    Returns:
        오퍼 ID 목록. 조회에 실패하면 빈 목록 — 생성을 막지 않는다.
    """
    try:
        from ...models.cpa_offer import CpaOffer, ST_ACTIVE

        rows = (await db.execute(
            select(CpaOffer).where(
                CpaOffer.status == ST_ACTIVE,
                CpaOffer.is_deleted.is_(False))
        )).scalars().all()
        found = [r.id for r in rows
                 if r.usable and blog_id in (r.blog_ids or [])]
        if found:
            logger.info("[SCOPE] CPA 오퍼 담당 | blog=%s | %s", blog_id, found)
        return found
    except Exception as e:  # noqa: BLE001 — 조회 실패로 생성을 막지 않는다
        logger.warning("[SCOPE] CPA 오퍼 조회 실패 | %s", e)
        return []


def title_condition(category_conditions: Sequence[Any],
                    cpa_offer_ids: Optional[Sequence[int]] = None) -> Any:
    """제목 조회에 붙일 조건.

    Args:
        category_conditions: 카테고리 OR 조건들(없으면 빈 목록)
        cpa_offer_ids: 이 블로그가 담당하는 오퍼. 비면 CPA 제목을 뺀다.

    Returns:
        SQLAlchemy 조건식
    """
    plain = MainTitle.cpa_offer_id.is_(None)
    if category_conditions:
        plain = and_(plain, or_(*category_conditions))
    if cpa_offer_ids:
        return or_(plain, MainTitle.cpa_offer_id.in_(list(cpa_offer_ids)))
    return plain
