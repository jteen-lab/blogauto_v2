"""어느 제목을 어느 블로그가 쓸 수 있나.

CPA 제목이 일반 재고에 섞여 있다. 격리하지 않으면 애드센스 블로그가
오퍼 규칙이 붙은 글을 발행한다(2026-09-09에 그 직전까지 갔다).

    일반 블로그   오퍼 전용 제목을 뽑지 않는다
    담당 블로그   오퍼 전용 제목 + **그 오퍼가 쓰는 하위주제의 일반 제목**

담당 블로그가 하위주제의 일반 제목도 쓰는 이유: 정보성 글로 상담 페이지에
유도하는 구조다. 그 정보성 글이 곧 하위주제의 제목이다.

**오퍼 전용 제목을 먼저 쓴다.** 하위주제에 일반 제목이 수백 건이면 방금
만든 오퍼 제목이 순번에서 밀린다. 실측(2026-09-09): 일반 4,401개에 CPA
5개일 때 조회가 오래된 순 50개라 후보에 들지도 못했다.

순서도: docs/flowcharts/cpa_offer.md
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.title import MainTitle

logger = get_logger("title_scope", "app.log")


async def owned_subtopic_ids(db: AsyncSession,
                             offer_ids: Sequence[int]) -> List[int]:
    """담당 오퍼들이 쓰는 하위주제."""
    if not offer_ids:
        return []
    try:
        from ...models.cpa_offer import CpaOffer

        rows = (await db.execute(
            select(CpaOffer.subtopic_ids).where(
                CpaOffer.id.in_(list(offer_ids))))).scalars().all()
        out: List[int] = []
        for ids in rows:
            for one in (ids or []):
                try:
                    value = int(one)
                except (TypeError, ValueError):
                    continue
                if value not in out:
                    out.append(value)
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("[SCOPE] 오퍼 하위주제 조회 실패 | %s", e)
        return []


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
                    cpa_offer_ids: Optional[Sequence[int]] = None,
                    cpa_subtopic_ids: Optional[Sequence[int]] = None) -> Any:
    """제목 조회에 붙일 조건.

    Args:
        category_conditions: 카테고리 OR 조건들(없으면 빈 목록)
        cpa_offer_ids: 이 블로그가 담당하는 오퍼
        cpa_subtopic_ids: 그 오퍼들이 쓰는 하위주제

    Returns:
        SQLAlchemy 조건식
    """
    if cpa_offer_ids:
        mine = [MainTitle.cpa_offer_id.in_(list(cpa_offer_ids))]
        if cpa_subtopic_ids:
            # 하위주제의 일반 제목도 쓴다 — 정보성 글로 유도하는 구조다.
            # 남의 오퍼 제목이 들어오면 안 되므로 NULL 조건을 함께 건다.
            mine.append(and_(
                MainTitle.cpa_offer_id.is_(None),
                MainTitle.subtopic_id.in_(list(cpa_subtopic_ids))))
        return or_(*mine) if len(mine) > 1 else mine[0]

    plain = MainTitle.cpa_offer_id.is_(None)
    if category_conditions:
        plain = and_(plain, or_(*category_conditions))
    return plain


async def blog_cpa_scope(db: AsyncSession, blog_id: int) -> tuple:
    """이 블로그의 CPA 범위 — (담당 오퍼, 그 오퍼들의 하위주제).

    세는 곳·목록·고르는 곳이 같은 값을 써야 한다. 따로 구하면 어긋난다.
    """
    offers = await owned_offer_ids(db, blog_id)
    return offers, await owned_subtopic_ids(db, offers)


def offer_first_order() -> Any:
    """오퍼 전용 제목을 앞으로.

    하위주제에 일반 제목이 수백 건이면 방금 만든 오퍼 제목이 순번에서
    밀린다. 실측(2026-09-09): 4,401 대 5로 후보에 들지도 못했다.
    """
    return MainTitle.cpa_offer_id.is_(None).asc()


async def log_empty(db: AsyncSession, blog_id_str: str, used_subquery: Any) -> None:
    """제목 후보가 0개일 때 어디서 걸렸는지 남긴다.

    조용히 비면 재고가 없는 것인지 조건이 틀린 것인지 구분할 수 없다.
    """
    from sqlalchemy import func

    total = (await db.execute(
        select(func.count(MainTitle.id))
        .where(MainTitle.status != "archived"))).scalar() or 0
    used = (await db.execute(
        select(func.count()).select_from(used_subquery.subquery())
    )).scalar() or 0
    logger.info("[SCOPE] 후보 0개 원인 | blog=%s | 비archived전체=%s | "
                "이블로그사용제외=%s", blog_id_str, total, used)
