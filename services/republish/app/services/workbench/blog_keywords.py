"""담은 블로그의 하위 주제 → 키워드 트리.

모듈 테스터의 소스 검색창 아래에 칩으로 펼쳐, 누르면 검색창에 들어간다.

순서도: docs/flowcharts/workbench_blog_keywords.md
"""
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.category import BlogCategory, Keyword, SubTopic, Topic

logger = get_logger("workbench_blog_keywords", "app.log")


async def _owned_blogs(
    db: AsyncSession, user_id: int, blog_ids: List[int],
) -> List[Blog]:
    """요청한 id 중 내 블로그만. 남의 id 는 조용히 빠진다."""
    if not blog_ids:
        return []
    rows = await db.execute(
        select(Blog).where(
            Blog.id.in_(blog_ids),
            Blog.user_id == user_id,
            Blog.is_deleted.is_(False),
        )
    )
    blogs = rows.scalars().all()
    # 담은 순서를 지킨다 — 화면 칩 순서가 담은 순서와 같아야 헷갈리지 않는다
    order = {bid: i for i, bid in enumerate(blog_ids)}
    return sorted(blogs, key=lambda b: order.get(b.id, 0))


async def _subtopics_of(db: AsyncSession, blog_id: int) -> List[dict]:
    """블로그에 연결된 활성 하위 주제(주제명 포함), 정렬 순서대로."""
    rows = await db.execute(
        select(SubTopic.id, SubTopic.name, Topic.name)
        .join(BlogCategory, BlogCategory.subtopic_id == SubTopic.id)
        .join(Topic, SubTopic.topic_id == Topic.id)
        .where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
            BlogCategory.subtopic_id.isnot(None),
            SubTopic.is_deleted.is_(False),
            Topic.is_deleted.is_(False),
        )
        .distinct()
        .order_by(Topic.order, Topic.name, SubTopic.order, SubTopic.name)
    )
    return [
        {"subtopic_id": sid, "subtopic_name": sname, "topic_name": tname}
        for sid, sname, tname in rows.all()
    ]


async def _keywords_by_subtopic(
    db: AsyncSession, subtopic_ids: List[int],
) -> Dict[int, List[str]]:
    """하위 주제 id → 키워드 이름 목록. 한 번에 받아 N+1 을 피한다."""
    if not subtopic_ids:
        return {}
    rows = await db.execute(
        select(Keyword.subtopic_id, Keyword.name)
        .where(
            Keyword.subtopic_id.in_(subtopic_ids),
            Keyword.is_deleted.is_(False),
        )
        .order_by(Keyword.subtopic_id, Keyword.order, Keyword.priority,
                  Keyword.name)
    )
    out: Dict[int, List[str]] = {}
    for sid, name in rows.all():
        name = (name or "").strip()
        if name and name not in out.setdefault(sid, []):
            out[sid].append(name)
    return out


async def keywords_for_blogs(
    db: AsyncSession, user_id: int, blog_ids: List[int],
) -> List[dict]:
    """블로그 → 하위 주제 → 키워드 트리.

    키워드가 하나도 없는 하위 주제도 남긴다 — 화면이 "이 주제엔 키워드가
    없다"고 알려 줘야 카테고리 화면에서 채우러 갈 수 있다.
    """
    blogs = await _owned_blogs(db, user_id, blog_ids)
    result: List[dict] = []
    for blog in blogs:
        subs = await _subtopics_of(db, blog.id)
        kw_map = await _keywords_by_subtopic(
            db, [s["subtopic_id"] for s in subs])
        for s in subs:
            s["keywords"] = kw_map.get(s["subtopic_id"], [])
        result.append({
            "blog_id": blog.id,
            "blog_name": blog.name,
            "subtopics": subs,
        })
    logger.info(
        f"[WB_KEYWORDS] user={user_id} blogs={[b.id for b in blogs]} "
        f"subtopics={sum(len(b['subtopics']) for b in result)}")
    return result
