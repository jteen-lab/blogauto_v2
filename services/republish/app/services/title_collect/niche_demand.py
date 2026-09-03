"""니치 수요 — 어디에 제목이 부족한가.

정식제목 탭의 '니치 현황' 이 보여 주는 것과 **같은 기준**을 쓴다. 화면과
수집이 다른 기준으로 판단하면, 화면은 부족하다는데 수집은 다른 곳을
채우는 일이 생긴다.

부족 = **쓰는 블로그가 있는데** 재고가 기준보다 적은 니치.
쓰는 블로그가 없는 니치는 채워 봐야 죽은 재고다 — 부족으로 세지 않는다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from __future__ import annotations

from typing import Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import BlogCategory, SubTopic, Topic
from ...models.title import MainTitle

logger = get_logger("niche_demand", "app.log")

# 이보다 적으면 부족. 블로그 하나가 며칠 쓸 분량이다.
DEFAULT_LOW = 20


async def low_subtopics(db: AsyncSession, user_id: int,
                        threshold: int = DEFAULT_LOW) -> Set[int]:
    """재고가 부족한 하위주제 id 집합.

    실패는 빈 집합이다 — 우선순위를 못 정해도 수집은 계속해야 한다.
    """
    try:
        titles = (
            select(MainTitle.subtopic_id.label("sid"),
                   func.count(MainTitle.id).label("n"))
            .where(MainTitle.status == "available",
                   MainTitle.subtopic_id.is_not(None))
            .group_by(MainTitle.subtopic_id).subquery())
        blogs = (
            select(BlogCategory.subtopic_id.label("sid"),
                   func.count(func.distinct(BlogCategory.blog_id)).label("n"))
            .where(BlogCategory.is_active.is_(True),
                   BlogCategory.subtopic_id.is_not(None))
            .group_by(BlogCategory.subtopic_id).subquery())

        rows = (await db.execute(
            select(SubTopic.id, func.coalesce(titles.c.n, 0),
                   func.coalesce(blogs.c.n, 0))
            .select_from(SubTopic)
            .join(Topic, Topic.id == SubTopic.topic_id)
            .outerjoin(titles, titles.c.sid == SubTopic.id)
            .outerjoin(blogs, blogs.c.sid == SubTopic.id)
            .where(SubTopic.is_deleted.is_(False),
                   Topic.is_deleted.is_(False),
                   Topic.user_id == user_id)
        )).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("[NICHE_DEMAND] 조회 실패 | %s", e)
        return set()

    low = {sid for sid, count, blog_count in rows
           if blog_count and (count or 0) < max(1, threshold)}
    if low:
        logger.info("[NICHE_DEMAND] 재고 부족 니치 %d개(기준 %d)",
                    len(low), threshold)
    return low
