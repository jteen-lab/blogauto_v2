"""임시제목에서 글감 찾기 — 이미 우리가 모아 둔 제목 중에서.

바깥에서 새로 찾기 전에, **담은 블로그의 하위 주제 안에 쌓인 임시제목**을
먼저 본다. 이미 니치 안에서 모은 것이라 헛도는 일이 없다.

담은 블로그가 없으면 검색하지 않는다 — 어느 하위 주제로 좁힐지 알 수 없고,
전체를 뒤지면 니치 밖 제목이 섞인다.

순서도: docs/flowcharts/workbench_source_modes.md
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import Keyword
from ...models.title import TempTitle
from .blog_keywords import owned_blogs, subtopics_of

logger = get_logger("workbench_temp_titles", "app.log")

SOURCE = "temp_title"
SOURCE_LABEL = "임시제목"

#: 정식제목으로 이미 옮긴 것은 뺀다 — 재고에서 꺼내 쓸 대상이 아니다.
EXCLUDED_STATUS = ("moved",)

PER_PAGE = 20


def _match_terms(query: str) -> List[str]:
    """같은 키워드로 볼 형태들.

    같은 말이 세 군데서 다르게 적힌다.

        키워드 풀   포장+이사   (+ 로 묶어 저장)
        검색창      포장 이사   (칩이 띄어서 넣는다)
        제목        포장이사    (사람이 붙여 쓴다)

    셋 다 같은 것으로 본다. 아니면 칩을 눌러 넣은 검색어로 우리가 모아 둔
    제목을 못 찾는다.
    """
    text = " ".join((query or "").replace("+", " ").split())
    if not text:
        return []
    terms = {text, text.replace(" ", ""), text.replace(" ", "+")}
    return [t for t in terms if len(t) >= 2]


async def search_temp_titles(
    db: AsyncSession, user_id: int, blog_ids: List[int], query: str,
    limit: int = PER_PAGE, start: int = 1,
) -> Dict[str, Any]:
    """담은 블로그의 하위 주제 안에서 검색어와 맞는 임시제목.

    Args:
        db: 세션
        user_id: 내 것만 — 남의 블로그 id 는 조용히 빠진다
        blog_ids: 모듈 테스터에 담은 블로그
        query: 검색어(대개 키워드 칩)
        limit: 한 번에 볼 건수
        start: 몇 번째부터. '더 보기' 가 올린다

    Returns:
        다른 소스와 같은 모양 — {"items": [...], "next_start": …, "error": …}
    """
    text = " ".join((query or "").split())
    if len(text) < 2:
        return {"items": [], "by_source": {}, "next_start": None,
                "error": "검색어가 너무 짧습니다"}

    blogs = await owned_blogs(db, user_id, blog_ids)
    if not blogs:
        return {"items": [], "by_source": {}, "next_start": None,
                "error": "블로그를 먼저 담으세요 — 그 블로그의 "
                         "하위 주제 안에서만 찾습니다"}

    sub_names: Dict[int, str] = {}
    for blog in blogs:
        for sub in await subtopics_of(db, blog.id):
            sub_names[sub["subtopic_id"]] = sub["subtopic_name"]
    if not sub_names:
        return {"items": [], "by_source": {}, "next_start": None,
                "error": "담은 블로그에 연결된 하위 주제가 없습니다"}

    terms = _match_terms(text)
    title_match = [TempTitle.title.ilike(f"%{t}%") for t in terms]
    # 제목 글자가 달라도, 그 제목을 걸어 준 카테고리 키워드가 같으면 맞다
    keyword_match = TempTitle.matched_keyword_id.in_(
        select(Keyword.id).where(
            or_(*[Keyword.name.ilike(f"%{t}%") for t in terms])))

    offset = max(0, int(start) - 1)
    rows = (await db.execute(
        select(TempTitle)
        .where(
            TempTitle.subtopic_id.in_(list(sub_names)),
            TempTitle.status.notin_(EXCLUDED_STATUS),
            or_(*title_match, keyword_match),
        )
        .order_by(TempTitle.created_at.desc(), TempTitle.id.desc())
        .offset(offset).limit(limit + 1)
    )).scalars().all()

    has_more = len(rows) > limit
    items = []
    for rank, row in enumerate(rows[:limit], start=int(start)):
        items.append({
            "title": row.title,
            "description": row.source_blog_url or "",
            "link": row.source_post_url or "",
            "source": SOURCE,
            "source_label": SOURCE_LABEL,
            "has_situation": False,
            "rank": rank,
            "signals": [s for s in (
                sub_names.get(row.subtopic_id, ""),
                row.created_at.strftime("%Y-%m-%d") if row.created_at else "",
            ) if s],
        })

    logger.info("[WB_TEMP_TITLE] user=%s blogs=%s '%s' %d번째부터 → %d건",
                user_id, [b.id for b in blogs], text, start, len(items))
    return {
        "items": items,
        "by_source": {SOURCE: len(items)},
        "next_start": (int(start) + limit) if has_more else None,
        "error": None if items else "이 블로그의 하위 주제에서 찾지 못했습니다",
    }
