"""
자동 매칭 서비스 (Phase MATCH-040 개편)

정식제목 탭에서 블로그 선택 시 V3 SimilarityService 로 크롤링 포스트와
정식제목(MainTitle) 간 유사도 매칭을 수행한다.

새 정책 (사용자 디벨롭 A + B):
1. CrawledPost.match_status='pending' (신규 발행글) 만 매번 재매칭한다.
2. match_status='unmatched' (미매칭 굳힘) 는 재매칭하지 않고 그대로 둔다.
   → 새 정식제목이 등장(=BlogMainTitleScan 카드 없는 정식제목)했을 때만
     unmatched 발행글을 그 새 정식제목과 다시 비교한다.
3. 블로그×정식제목 검토 결과는 BlogMainTitleScan 에 영구 기록한다.
   같은 쌍은 두 번 비교하지 않는다.
4. 그룹3 = 그 블로그 카테고리 ∩ BlogMainTitleScan 카드 없는 정식제목.
   그룹3 정식제목과 그 블로그의 unmatched + pending 발행글을 매칭한다.
"""
import sys
import os
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from ..models.blog import Blog
from ..models.crawled_post import CrawledPost
from ..models.title import MainTitle
from ..models.category import BlogCategory
from ..models.blog_main_title_scan import BlogMainTitleScan
from ..core.logger import get_logger

# shared SimilarityService 임포트 (Docker/로컬 환경 모두 지원)
_shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
for _path in _shared_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
        break

from services.similarity_service import SimilarityService

logger = get_logger("auto_match", "matching.log")


class AutoMatchService:
    """V3 엔진 기반 자동 매칭 서비스 (검토 카드 정책).

    Phase MATCH-040: 검토 카드(BlogMainTitleScan) 기반으로 매칭 범위를
    "신규 발행글" + "그룹3 정식제목" 두 축에 한정한다.
    """

    DEFAULT_THRESHOLD = 65.0

    def __init__(self, db: AsyncSession):
        self.db = db
        self.similarity_service = SimilarityService()

    async def auto_match(
        self,
        blog_id: int,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> dict:
        """블로그 선택 시 자동 매칭 (사용자 디벨롭 A+B 정책)."""
        logger.info(
            f"[AUTO_MATCH] 시작 | blog_id={blog_id} | th={threshold}%"
        )
        candidate_titles = await self._get_category_filtered_titles(blog_id)
        if not candidate_titles:
            return await self._handle_no_candidates(blog_id)

        unscanned_titles = await self._get_unscanned_titles(
            blog_id, candidate_titles
        )
        unscanned_ids = {t.id for t in unscanned_titles}

        pending_posts, p_matched, p_unmatched = await self._run_pending_match(
            blog_id, candidate_titles, threshold
        )
        unmatched_posts, u_matched = await self._run_unscanned_match(
            blog_id, unscanned_titles, threshold
        )

        matched_in_round = {
            p.matched_main_title_id for p in (pending_posts + unmatched_posts)
            if p.matched_main_title_id in unscanned_ids
        }
        await self._insert_scan_cards(
            blog_id, unscanned_ids, matched_in_round
        )
        await self._touch_blog_matched_at(blog_id)
        await self.db.commit()

        logger.info(
            f"[AUTO_MATCH] 완료 | blog_id={blog_id} | "
            f"pending={len(pending_posts)}/{p_matched} | "
            f"unscanned={len(unscanned_titles)}/{u_matched}"
        )
        return {
            "matched": p_matched + u_matched,
            "unmatched": p_unmatched,
            "skipped": 0,
            "pending_processed": len(pending_posts),
            "unscanned_processed": len(unscanned_titles),
        }

    async def _handle_no_candidates(self, blog_id: int) -> dict:
        """후보 정식제목 0건 시 pending 전체 unmatched 처리."""
        logger.warning(
            f"[AUTO_MATCH] 사용 가능한 MainTitle 없음 | blog_id={blog_id}"
        )
        pending_posts = await self._get_posts_by_status(blog_id, ["pending"])
        for post in pending_posts:
            post.mark_unmatched()
        await self.db.commit()
        return {
            "matched": 0,
            "unmatched": len(pending_posts),
            "skipped": 0,
            "pending_processed": len(pending_posts),
            "unscanned_processed": 0,
        }

    async def _run_pending_match(
        self,
        blog_id: int,
        candidate_titles: List[MainTitle],
        threshold: float,
    ) -> Tuple[List[CrawledPost], int, int]:
        """pending 발행글을 모든 후보와 매칭."""
        pending_posts = await self._get_posts_by_status(blog_id, ["pending"])
        matched, unmatched = self._match_posts_against_titles(
            pending_posts, candidate_titles, threshold
        )
        return pending_posts, matched, unmatched

    async def _run_unscanned_match(
        self,
        blog_id: int,
        unscanned_titles: List[MainTitle],
        threshold: float,
    ) -> Tuple[List[CrawledPost], int]:
        """그룹3 정식제목이 있으면 unmatched 발행글을 그 그룹3과만 재매칭."""
        if not unscanned_titles:
            return [], 0
        unmatched_posts = await self._get_posts_by_status(
            blog_id, ["unmatched"]
        )
        matched, _ = self._match_posts_against_titles(
            unmatched_posts, unscanned_titles, threshold
        )
        return unmatched_posts, matched

    async def _touch_blog_matched_at(self, blog_id: int) -> None:
        """Blog.last_matched_at 갱신."""
        blog = await self.db.get(Blog, blog_id)
        if blog:
            blog.last_matched_at = datetime.utcnow()

    async def _get_posts_by_status(
        self, blog_id: int, statuses: List[str]
    ) -> List[CrawledPost]:
        """블로그의 특정 매칭 상태 발행글 조회."""
        query = select(CrawledPost).where(
            and_(
                CrawledPost.blog_id == blog_id,
                CrawledPost.match_status.in_(statuses),
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_category_filtered_titles(
        self, blog_id: int
    ) -> List[MainTitle]:
        """블로그 카테고리에 해당하는 정식제목 후보 조회.

        BlogCategory(blog_id, is_active) 의 subtopic_id/topic_id 기준으로
        MainTitle 을 필터링한다. 카테고리 없으면 전체 반환.
        """
        bc_query = select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active == True,
        )
        bc_result = await self.db.execute(bc_query)
        blog_categories = bc_result.scalars().all()

        base_query = select(MainTitle).where(
            MainTitle.status.in_(["available", "matched", "used"])
        )

        if not blog_categories:
            logger.debug(
                f"[AUTO_MATCH] 활성 카테고리 없음, 전체 MainTitle 사용 | "
                f"blog_id={blog_id}"
            )
            result = await self.db.execute(base_query)
            return list(result.scalars().all())

        subtopic_ids: set = set()
        topic_only_ids: set = set()
        for bc in blog_categories:
            if bc.subtopic_id:
                subtopic_ids.add(bc.subtopic_id)
            elif bc.topic_id:
                topic_only_ids.add(bc.topic_id)

        conditions: list = []
        if subtopic_ids:
            conditions.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
        if topic_only_ids:
            conditions.append(MainTitle.topic_id.in_(list(topic_only_ids)))

        if conditions:
            base_query = base_query.where(or_(*conditions))

        result = await self.db.execute(base_query)
        return list(result.scalars().all())

    async def _get_unscanned_titles(
        self, blog_id: int, candidates: List[MainTitle]
    ) -> List[MainTitle]:
        """검토 카드(BlogMainTitleScan) 없는 정식제목 추출 (그룹3)."""
        if not candidates:
            return []
        candidate_ids = [t.id for t in candidates]
        scanned_query = select(BlogMainTitleScan.main_title_id).where(
            BlogMainTitleScan.blog_id == blog_id,
            BlogMainTitleScan.main_title_id.in_(candidate_ids),
        )
        result = await self.db.execute(scanned_query)
        scanned_ids = set(result.scalars().all())
        return [t for t in candidates if t.id not in scanned_ids]

    def _match_posts_against_titles(
        self,
        posts: List[CrawledPost],
        titles: List[MainTitle],
        threshold: float,
    ) -> Tuple[int, int]:
        """발행글 N개 × 정식제목 M개 매칭 + 결과 반영."""
        matched = 0
        unmatched = 0
        if not posts or not titles:
            return 0, 0
        for post in posts:
            best_id, best_score = self._find_best_match(post.title, titles)
            if best_id is not None and best_score >= threshold:
                post.mark_matched(best_id, best_score)
                matched += 1
            else:
                post.mark_unmatched(best_score if best_score > 0 else None)
                unmatched += 1
        return matched, unmatched

    def _find_best_match(
        self, post_title: str, titles: List[MainTitle]
    ) -> Tuple[Optional[int], float]:
        """V3 유사도 최고점 정식제목 1건 반환."""
        best_id: Optional[int] = None
        best_score: float = 0.0
        for t in titles:
            score = self.similarity_service.calculate_similarity_v2(
                post_title, t.title
            )
            if score > best_score:
                best_score = score
                best_id = t.id
        return best_id, best_score

    async def _insert_scan_cards(
        self,
        blog_id: int,
        unscanned_ids: set,
        matched_title_ids: set,
    ) -> None:
        """그룹3 정식제목에 대해 검토 카드 신규 생성.

        unscanned_ids 의 정의상 카드가 없으므로 INSERT 만 한다.
        matched_title_ids 에 포함되면 matched=True (그룹1로 전환),
        아니면 matched=False (그룹2로 굳힘).
        """
        if not unscanned_ids:
            return
        now = datetime.utcnow()
        for mt_id in unscanned_ids:
            card = BlogMainTitleScan(
                blog_id=blog_id,
                main_title_id=mt_id,
                matched=(mt_id in matched_title_ids),
                scanned_at=now,
            )
            self.db.add(card)
