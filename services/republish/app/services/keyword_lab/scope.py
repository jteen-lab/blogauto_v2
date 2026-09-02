"""블로그가 쓸 수 있는 키워드 범위.

키워드에 니치(topic/subtopic)를 붙여 놓고도 **배정에 쓰지 않고 있었다.**
제목 생성 대상을 `blog_id == 이 블로그` 로만 좁혀, 전역 풀(blog_id IS NULL)에
쌓인 키워드는 어느 블로그도 쓰지 못했다. 실제로 채택 469건이 전역 풀에
있는데 블로그가 붙은 제목 모듈에서 한 건도 안 잡혔다.

니치 분류의 값은 여기서 나온다: **이 키워드를 어느 블로그가 쓸 것인가.**

    쓸 수 있다 = 이 블로그에 직접 배정됐거나
                 (전역 풀이면서 니치가 이 블로그의 활성 카테고리에 속함)

블로그에 카테고리가 없으면 전역 풀을 열지 않는다. 니치를 정하지 않은
블로그에 아무 키워드나 흘러들면 무엇으로 쓸지 알 수 없다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-1
"""
from __future__ import annotations

from typing import Any, Optional, Set, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import BlogCategory

logger = get_logger("keyword_scope", "app.log")


async def blog_categories(db: AsyncSession,
                          blog: Any) -> Tuple[Set[int], Set[int]]:
    """블로그의 활성 카테고리 (topic_id 집합, subtopic_id 집합)."""
    if blog is None:
        return set(), set()

    rows = (await db.execute(
        select(BlogCategory.topic_id, BlogCategory.subtopic_id).where(
            BlogCategory.blog_id == blog.id,
            BlogCategory.is_active.is_(True))
    )).all()
    topics = {r[0] for r in rows if r[0]}
    subs = {r[1] for r in rows if r[1]}
    return topics, subs


async def usable_by(db: AsyncSession, blog: Any, model: Any):
    """이 블로그가 쓸 수 있는 행을 고르는 조건.

    Args:
        db: DB 세션
        blog: 대상 블로그(None 이면 전역 — 조건 없음)
        model: `blog_id`·`topic_id`·`subtopic_id` 를 가진 모델
               (KeywordCandidate 또는 KeywordCluster)

    Returns:
        SQLAlchemy 조건. 블로그가 없으면 None(제한 없음).
    """
    if blog is None:
        return None

    mine = model.blog_id == blog.id
    topics, subs = await blog_categories(db, blog)
    if not topics and not subs:
        # 니치를 안 정한 블로그. 전역 풀을 열면 아무 키워드나 들어온다.
        logger.info("[KEYWORD_SCOPE] blog=%s 카테고리 없음 — 직접 배정분만",
                    blog.id)
        return mine

    niche = []
    if subs:
        niche.append(model.subtopic_id.in_(list(subs)))
    if topics:
        niche.append(model.topic_id.in_(list(topics)))

    return or_(mine, and_(model.blog_id.is_(None), or_(*niche)))
