"""블로그의 카테고리 안과 밖 — 한 곳에서 판정한다.

정식제목 목록(titles.py)과 매칭 카운트(blogs.py)가 같은 규칙을 따로
구현하고 있었다. 한쪽만 고치면 목록과 숫자가 어긋난다.

순서도: docs/flowcharts/blog_category_scope.md
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from ...core.logger import get_logger
from ...models.category import BlogCategory
from ...models.title import MainTitle

logger = get_logger("blog_category_scope", "app.log")


async def category_sets(db: AsyncSession,
                        blog_id: int) -> Tuple[Set[int], Set[int]]:
    """블로그에 걸린 활성 카테고리를 두 갈래로.

    Returns:
        (하위주제 id 집합, 주제만 지정된 topic id 집합)
    """
    rows = (await db.execute(
        select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
        )
    )).scalars().all()

    subtopic_ids: Set[int] = set()
    topic_only_ids: Set[int] = set()
    for bc in rows:
        if bc.subtopic_id:
            subtopic_ids.add(bc.subtopic_id)
        elif bc.topic_id:
            topic_only_ids.add(bc.topic_id)
    return subtopic_ids, topic_only_ids


def inside(subtopic_ids: Set[int],
           topic_only_ids: Set[int]) -> Optional[ColumnElement]:
    """카테고리 안에 있는 제목 조건. 카테고리가 없으면 None(제한 없음)."""
    conditions: List[ColumnElement] = []
    if subtopic_ids:
        conditions.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
    if topic_only_ids:
        conditions.append(MainTitle.topic_id.in_(list(topic_only_ids)))
    if not conditions:
        return None
    return or_(*conditions)


def outside(subtopic_ids: Set[int],
            topic_only_ids: Set[int]) -> Optional[ColumnElement]:
    """카테고리 밖에 있는 제목 조건.

    **분류가 없는 제목도 밖이다.** `NOT IN` 은 NULL 에서 참이 되지 않아
    그냥 뒤집으면 분류 없는 제목이 조용히 사라진다.
    """
    if not subtopic_ids and not topic_only_ids:
        return None
    parts: List[ColumnElement] = []
    if subtopic_ids:
        parts.append(or_(
            MainTitle.subtopic_id.is_(None),
            MainTitle.subtopic_id.notin_(list(subtopic_ids)),
        ))
    if topic_only_ids:
        parts.append(or_(
            MainTitle.topic_id.is_(None),
            MainTitle.topic_id.notin_(list(topic_only_ids)),
        ))
    return and_(*parts)


async def filters(db: AsyncSession, blog_id: int
                  ) -> Tuple[Optional[ColumnElement], Optional[ColumnElement]]:
    """(안 조건, 밖 조건). 카테고리를 안 걸어 둔 블로그는 (None, None)."""
    subs, topics = await category_sets(db, blog_id)
    if not subs and not topics:
        logger.debug("[BLOG_SCOPE] blog_id=%s 활성 카테고리 없음", blog_id)
        return None, None
    return inside(subs, topics), outside(subs, topics)
