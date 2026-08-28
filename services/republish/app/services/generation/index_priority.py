"""S7 — 내부링크 대상을 색인 상태로 우선순위화.

배경: 구글이 "발견됨 - 현재 색인이 생성되지 않음" 으로 판정한 URL 에 대한 표준
처방이 내부링크다. 그런데 기존 내부링커는 **색인 여부를 전혀 보지 않았다.**
특히 결론 링크는 `random.shuffle` 로 아무거나 골랐다.

여기서는 결론 링크에 한해 **미색인 글을 먼저** 고르게 한다. 서론·본문 섹션은
유사도가 1차 기준이라 건드리지 않는다 — 관련 없는 글을 링크하면 사용자에게도
검색엔진에게도 손해다.

한계(정직하게): 링크를 거는 **새 글 자체가 아직 미색인**이면 크롤 유도 효과가 약하다.
이미 색인된 글에서 미색인 글로 거는 것이 본래 처방이며, 그건 발행된 글을 수정해야
해서 별도 작업(S7-b)으로 둔다.

설계: docs/plans/search_visibility_plan.md §10.4
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.search_visibility import (
    IX_INDEXED, IX_NOT_INDEXED, IX_UNKNOWN, SearchVisibilityUrl,
)

logger = get_logger("index_priority", "app.log")

# 낮을수록 먼저 고른다.
# 미색인이 최우선, 미확인이 다음, 이미 색인된 글은 마지막(링크가 덜 급하다).
PRIORITY = {
    IX_NOT_INDEXED: 0,
    "error": 1,
    IX_UNKNOWN: 2,
    IX_INDEXED: 3,
}
DEFAULT_PRIORITY = PRIORITY[IX_UNKNOWN]


def _normalize(url: str) -> str:
    """비교용으로 URL 끝 슬래시를 정리한다."""
    return (url or "").strip().rstrip("/")


async def load_index_states(
    db: AsyncSession, blog_id: int, urls: Sequence[str],
) -> Dict[str, str]:
    """원장에서 URL별 색인 상태를 읽는다.

    Args:
        db: 세션
        blog_id: 블로그
        urls: 조회할 URL 목록

    Returns:
        {정규화된 URL: index_state}. 원장에 없는 URL 은 빠진다.
    """
    cleaned = [u for u in urls if u]
    if not cleaned:
        return {}

    stmt = select(
        SearchVisibilityUrl.url, SearchVisibilityUrl.index_state,
    ).where(
        SearchVisibilityUrl.blog_id == blog_id,
        SearchVisibilityUrl.url.in_(cleaned),
    )
    rows = (await db.execute(stmt)).all()
    return {_normalize(url): state for url, state in rows}


def sort_by_index_priority(
    posts: List[Any], states: Dict[str, str],
) -> List[Any]:
    """미색인 글이 앞에 오도록 정렬한다.

    파이썬 정렬은 안정적이므로 **같은 우선순위 안에서는 입력 순서가 보존된다.**
    호출 전에 섞어두면 무작위성이 유지되면서 미색인만 앞으로 당겨진다.
    """
    return sorted(
        posts,
        key=lambda post: PRIORITY.get(
            states.get(_normalize(getattr(post, "url", ""))), DEFAULT_PRIORITY,
        ),
    )


async def prioritize(
    db: AsyncSession, blog_id: int, posts: List[Any],
) -> List[Any]:
    """원장을 조회해 미색인 우선으로 재정렬한다.

    원장이 비었거나 조회에 실패하면 입력을 그대로 돌려준다(내부링크를 막지 않는다).
    """
    if not posts:
        return posts

    try:
        states = await load_index_states(
            db, blog_id, [getattr(p, "url", "") for p in posts],
        )
        if not states:
            return posts

        ordered = sort_by_index_priority(posts, states)
        not_indexed = sum(
            1 for p in ordered
            if states.get(_normalize(getattr(p, "url", ""))) == IX_NOT_INDEXED
        )
        logger.info(
            "[INDEX_PRIORITY] 정렬 | blog=%s | 후보 %d | 미색인 %d | 원장 %d",
            blog_id, len(posts), not_indexed, len(states),
        )
        return ordered
    except Exception as exc:  # noqa: BLE001 — 내부링크를 막지 않는다
        logger.warning("[INDEX_PRIORITY] 정렬 실패(무시): %s", exc)
        return posts
