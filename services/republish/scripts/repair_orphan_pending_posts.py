"""정식제목이 없는 발행대기글을 이어 붙인다.

모듈 테스터가 글을 저장하면서 정식제목을 만들지 않아, 카운트에는
잡히는데 목록에는 안 뜨는 글이 생겼다(2026-09-15). 코드는 고쳤고,
이 스크립트는 **이미 그렇게 저장된 글**을 되살린다.

    python3 scripts/repair_orphan_pending_posts.py          # 무엇을 고칠지 보기
    python3 scripts/repair_orphan_pending_posts.py --apply  # 실제로 고치기
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import db_manager  # noqa: E402
from app.models.crawled_post import CrawledPost  # noqa: E402
from app.services.workbench.apply import _ensure_main_title  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main(apply: bool) -> None:
    """정식제목 없이 매칭된 글을 찾아 이어 붙인다."""
    await db_manager.initialize()
    async with db_manager.get_session() as db:
        rows = (await db.execute(
            select(CrawledPost).where(
                CrawledPost.match_status == "matched",
                CrawledPost.matched_main_title_id.is_(None),
                CrawledPost.source == "generated",
            ).order_by(CrawledPost.id)
        )).scalars().all()

        if not rows:
            logger.info("고칠 글이 없습니다.")
            return

        logger.info("정식제목이 없는 발행글 %d건", len(rows))
        for post in rows:
            state = "발행완료" if post.published_at else "발행대기"
            logger.info("  [%s] 블로그%s · %s", state, post.blog_id,
                        (post.title or "")[:40])
            if apply:
                post.matched_main_title_id = await _ensure_main_title(
                    db, post.blog_id, post.title or "")

        if apply:
            await db.commit()
            logger.info("\n%d건을 정식제목에 이어 붙였습니다.", len(rows))
        else:
            logger.info("\n미리보기입니다. 실제로 고치려면 --apply 를 붙이세요.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
