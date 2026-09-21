"""미매칭 발행글을 정식제목으로 올린다.

정식제목은 `(제목, 주제)` 가 겹칠 수 없다. 고른 것 가운데 이미 있는
제목이 섞이면 넣기가 깨지고, **깨진 트랜잭션은 그 뒤 전부를 함께
죽인다**. 한 건씩은 되고 전체는 안 되던 까닭이 이것이다.

그래서 두 가지를 한다.
  · 이미 있는 제목은 새로 만들지 않고 **그 제목에 붙인다**.
  · 건마다 되돌림점을 찍어 하나가 깨져도 나머지를 살린다.

순서도: docs/flowcharts/unmatched_promote.md
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.blog_main_title_scan import BlogMainTitleScan
from ..models.category import BlogCategory
from ..models.crawled_post import CrawledPost
from ..models.title import MainTitle

logger = get_logger("unmatched_promote", "app.log")


async def _seed_category(db: AsyncSession,
                         blog_id: int) -> Tuple[Optional[int], Optional[int]]:
    """새 정식제목에 달아 줄 주제. 블로그의 첫 활성 카테고리를 따른다."""
    row = (await db.execute(
        select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
        ).limit(1)
    )).scalar_one_or_none()
    return (row.topic_id, row.subtopic_id) if row else (None, None)


async def _existing_titles(db: AsyncSession, titles: List[str],
                           topic_id: Optional[int]) -> Dict[str, int]:
    """이 주제에 이미 있는 정식제목. 제목 → id.

    미리 모아 두면 대부분의 충돌을 넣기 전에 피할 수 있다.
    """
    if not titles:
        return {}
    query = select(MainTitle.id, MainTitle.title).where(
        MainTitle.title.in_(titles))
    query = query.where(MainTitle.topic_id == topic_id) if topic_id is not None \
        else query.where(MainTitle.topic_id.is_(None))
    rows = (await db.execute(query)).all()
    return {title: tid for tid, title in rows}


async def _ensure_scan(db: AsyncSession, blog_id: int,
                       main_title_id: int, now: datetime) -> None:
    """스캔 카드는 (블로그, 정식제목) 이 열쇠라 없을 때만 넣는다."""
    found = (await db.execute(
        select(BlogMainTitleScan).where(
            BlogMainTitleScan.blog_id == blog_id,
            BlogMainTitleScan.main_title_id == main_title_id,
        )
    )).scalar_one_or_none()
    if found:
        found.matched = True
        found.scanned_at = now
        return
    db.add(BlogMainTitleScan(blog_id=blog_id, main_title_id=main_title_id,
                             matched=True, scanned_at=now))


async def _link_one(db: AsyncSession, blog_id: int, post: CrawledPost,
                    known: Dict[str, int], seed: Tuple[Optional[int],
                                                       Optional[int]],
                    now: datetime) -> str:
    """한 건을 붙인다. 'linked' | 'promoted' 를 돌려준다.

    이미 있는 제목이면 그 제목에 붙이고, 없으면 새로 만든다.
    깨질 수 있는 넣기는 되돌림점 안에서만 한다.
    """
    title = (post.title or "").strip()
    hit = known.get(title)
    if hit is None:
        async with db.begin_nested():
            fresh = MainTitle(title=title, status="matched",
                              topic_id=seed[0], subtopic_id=seed[1])
            db.add(fresh)
            await db.flush()
            known[title] = fresh.id
        hit = known[title]
        kind = "promoted"
    else:
        kind = "linked"

    async with db.begin_nested():
        post.mark_matched(hit, 100.0)
        await _ensure_scan(db, blog_id, hit, now)
    return kind


async def promote_to_main(db: AsyncSession, blog_id: int,
                          post_ids: List[int]) -> Dict[str, Any]:
    """고른 미매칭 발행글을 정식제목에 붙인다.

    Args:
        db: 세션
        blog_id: 대상 블로그
        post_ids: 고른 발행글 id

    Returns:
        promoted/linked/failed/requested 와 사람이 읽을 message
    """
    seed = await _seed_category(db, blog_id)
    posts = (await db.execute(
        select(CrawledPost).where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.id.in_(post_ids),
            CrawledPost.match_status == "unmatched",
        )
    )).scalars().all()

    known = await _existing_titles(
        db, [(p.title or "").strip() for p in posts], seed[0])

    now = datetime.utcnow()
    promoted = linked = 0
    errors: List[str] = []
    for post in posts:
        try:
            kind = await _link_one(db, blog_id, post, known, seed, now)
            if kind == "promoted":
                promoted += 1
            else:
                linked += 1
        except Exception as e:                        # noqa: BLE001
            errors.append(f"post_id={post.id}: {str(e)[:120]}")

    await db.commit()
    logger.info(
        "[PROMOTE-MAIN] blog=%s | 새로 %s · 이어붙임 %s · 실패 %s / 고른 %s",
        blog_id, promoted, linked, len(errors), len(post_ids),
    )

    parts = []
    if promoted:
        parts.append(f"{promoted}개는 정식제목으로 새로 등록")
    if linked:
        parts.append(f"{linked}개는 이미 있던 정식제목에 연결")
    if errors:
        parts.append(f"{len(errors)}개는 실패")
    message = (" · ".join(parts) + "했습니다.") if parts \
        else "처리할 발행글이 없습니다."

    return {
        "success": True,
        "promoted": promoted,
        "linked": linked,
        "failed": len(errors),
        "requested": len(post_ids),
        "errors": errors[:20],
        "message": message,
    }
