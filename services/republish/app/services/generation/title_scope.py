"""어느 제목을 어느 블로그가 쓸 수 있나.

CPA 제목이 일반 재고에 섞여 있다. 격리하지 않으면 애드센스 블로그가
오퍼 규칙이 붙은 글을 발행한다(2026-09-09에 그 직전까지 갔다).

    일반 블로그   CPA 제목을 하나도 못 뽑는다
    담당 블로그   **그 오퍼의 제목만** 쓴다 (일반 제목도 뽑지 않는다)

담당 블로그가 일반 제목까지 뽑으면 두 가지가 어긋난다.

- 오퍼와 무관한 글이 CPA 블로그에 올라간다. 프로모션별로 나눠 운영하는
  뜻이 없어진다.
- **CPA 제목은 영영 순번이 오지 않는다.** 실측(2026-09-09): 일반 제목
  4,401개에 CPA 5개인데 조회는 오래된 순 50개다. 방금 만든 CPA 제목은
  후보에 들지 못한다.

카테고리도 보지 않는다. CPA 제목에는 주제·하위주제가 없고, 오퍼를
블로그에 붙인 순간 그 블로그가 무엇을 쓸지 정해진다.

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
        cpa_offer_ids: 이 블로그가 담당하는 오퍼. 있으면 그 오퍼의 제목만,
            비면 CPA 제목을 뺀 나머지.

    Returns:
        SQLAlchemy 조건식
    """
    if cpa_offer_ids:
        # 담당 블로그는 CPA 전용이다. 일반 제목을 섞지 않는다.
        return MainTitle.cpa_offer_id.in_(list(cpa_offer_ids))

    plain = MainTitle.cpa_offer_id.is_(None)
    if category_conditions:
        plain = and_(plain, or_(*category_conditions))
    return plain


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
