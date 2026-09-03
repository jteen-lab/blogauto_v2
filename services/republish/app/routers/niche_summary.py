"""니치 현황 요약 — 어느 니치에 제목이 얼마나 쌓였나.

정식제목 탭의 **네비게이션**이다. 숫자만 보고 "어디를 채워야 하는지"
판단할 수 있어야 수집·생성을 적극적으로 돌리게 된다.

두 값을 함께 본다.

    재고    이 니치에 쓸 수 있는 정식제목 수
    블로그  이 니치를 쓰는 블로그 수

**블로그 0인 니치의 재고는 죽은 재고다.** 아무도 꺼내 쓰지 않는다.
반대로 블로그는 많은데 재고가 적으면 그쪽부터 채워야 한다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.category import BlogCategory, SubTopic, Topic
from ..models.title import MainTitle
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/niches", tags=["data-titles"])
logger = get_logger("niche_summary", "app.log")

# 이보다 적으면 "부족" 으로 본다. 블로그 하나가 며칠 쓸 분량이다.
DEFAULT_LOW = 20


class NicheRow(BaseModel):
    """니치 한 줄."""

    topic_id: int
    topic_name: str
    subtopic_id: int
    subtopic_name: str
    titles: int = 0
    blogs: int = 0
    # 쓰는 블로그가 있는데 재고가 적은 곳 — 여기부터 채워야 한다
    is_low: bool = False
    # 재고는 있는데 쓰는 블로그가 없는 곳 — 죽은 재고
    is_orphan: bool = False


class NicheSummaryResponse(BaseModel):
    items: List[NicheRow]
    total_titles: int = 0
    low_count: int = 0
    orphan_count: int = 0
    threshold: int = DEFAULT_LOW


@router.get("", response_model=NicheSummaryResponse)
async def niche_summary(
    low_threshold: int = Query(DEFAULT_LOW, ge=1, le=1000),
    only_used: bool = Query(
        False, description="블로그가 쓰는 니치만 — 죽은 재고를 숨긴다"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> NicheSummaryResponse:
    """니치별 재고·블로그 수.

    삭제된 분류는 뺀다 — 분류 매처가 쓰지 않는 것을 보여 주면 사람이
    그쪽을 채우려 든다.
    """
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
        select(Topic.id, Topic.name, SubTopic.id, SubTopic.name,
               func.coalesce(titles.c.n, 0), func.coalesce(blogs.c.n, 0))
        .select_from(SubTopic)
        .join(Topic, Topic.id == SubTopic.topic_id)
        .outerjoin(titles, titles.c.sid == SubTopic.id)
        .outerjoin(blogs, blogs.c.sid == SubTopic.id)
        .where(SubTopic.is_deleted.is_(False), Topic.is_deleted.is_(False),
               Topic.user_id == current_user.id)
        .order_by(func.coalesce(titles.c.n, 0).desc())
    )).all()

    items: List[NicheRow] = []
    for topic_id, topic_name, sub_id, sub_name, count, blog_count in rows:
        count, blog_count = int(count or 0), int(blog_count or 0)
        if only_used and not blog_count:
            continue
        items.append(NicheRow(
            topic_id=topic_id, topic_name=topic_name,
            subtopic_id=sub_id, subtopic_name=sub_name,
            titles=count, blogs=blog_count,
            is_low=bool(blog_count and count < low_threshold),
            is_orphan=bool(count and not blog_count)))

    return NicheSummaryResponse(
        items=items,
        total_titles=sum(r.titles for r in items),
        low_count=sum(1 for r in items if r.is_low),
        orphan_count=sum(1 for r in items if r.is_orphan),
        threshold=low_threshold)
