"""
자동 매칭 서비스

정식제목 탭에서 블로그 선택 시 V3 SimilarityService를 사용하여
크롤링 포스트와 정식제목(MainTitle) 간 유사도 매칭을 수행합니다.

핵심 로직:
1. 해당 블로그의 미매칭/pending 크롤링 포스트 조회
2. 블로그 카테고리에 해당하는 MainTitle만 필터링
3. V3 SimilarityService.calculate_similarity_v2()로 유사도 계산
4. 임계값 이상이면 매칭, 미만이면 미매칭 처리
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
    """V3 엔진 기반 자동 매칭 서비스

    블로그 선택 시 크롤링 포스트와 정식 제목 간
    유사도 매칭을 자동으로 수행합니다.
    """

    DEFAULT_THRESHOLD = 65.0

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 비동기 DB 세션
        """
        self.db = db
        self.similarity_service = SimilarityService()

    async def auto_match(
        self,
        blog_id: int,
        threshold: float = DEFAULT_THRESHOLD
    ) -> dict:
        """
        블로그 선택 시 자동 매칭 실행

        1. 해당 블로그의 미매칭/pending 크롤링 포스트 조회
        2. 블로그 카테고리 기반 MainTitle 필터링
        3. V3 SimilarityService로 유사도 계산
        4. 임계값 이상이면 매칭, 미만이면 미매칭 처리

        Args:
            blog_id: 블로그 ID
            threshold: 매칭 임계값 (기본 65%)

        Returns:
            {"matched": int, "unmatched": int, "skipped": int}
        """
        logger.info(
            f"[AUTO_MATCH] 자동 매칭 시작 | "
            f"blog_id={blog_id} | threshold={threshold}%"
        )

        # 1. 매칭 대상 크롤링 포스트 조회
        posts = await self._get_matchable_posts(blog_id)
        if not posts:
            logger.info(f"[AUTO_MATCH] 매칭 대상 포스트 없음 | blog_id={blog_id}")
            return {"matched": 0, "unmatched": 0, "skipped": 0}

        # 2. 블로그 카테고리 기반 MainTitle 조회
        main_titles = await self._get_category_filtered_titles(blog_id)
        if not main_titles:
            logger.warning(
                f"[AUTO_MATCH] 사용 가능한 MainTitle 없음 | blog_id={blog_id}"
            )
            # MainTitle이 없으면 모든 포스트를 미매칭 처리
            for post in posts:
                post.mark_unmatched()
            await self.db.commit()
            return {"matched": 0, "unmatched": len(posts), "skipped": 0}

        # 3. 각 포스트별 최적 매칭 탐색
        matched = 0
        unmatched = 0
        skipped = 0

        for post in posts:
            best_title_id, best_score = self._find_best_match(
                post.title, main_titles
            )

            if best_title_id is not None and best_score >= threshold:
                post.mark_matched(best_title_id, best_score)
                matched += 1
                logger.debug(
                    f"[AUTO_MATCH] 매칭 성공 | post_id={post.id} | "
                    f"title_id={best_title_id} | score={best_score:.1f}%"
                )
            else:
                post.mark_unmatched(best_score if best_score > 0 else None)
                unmatched += 1

        # 4. DB 커밋 (마지막에 한 번만)
        blog = await self.db.get(Blog, blog_id)
        if blog:
            blog.last_matched_at = datetime.now()

        await self.db.commit()

        logger.info(
            f"[AUTO_MATCH] 자동 매칭 완료 | blog_id={blog_id} | "
            f"matched={matched} | unmatched={unmatched} | skipped={skipped}"
        )

        return {"matched": matched, "unmatched": unmatched, "skipped": skipped}

    async def _get_matchable_posts(self, blog_id: int) -> List[CrawledPost]:
        """
        매칭 대상 크롤링 포스트 조회

        이미 matched 상태인 포스트는 건너뛰고,
        pending 또는 unmatched 상태만 조회합니다.

        Args:
            blog_id: 블로그 ID

        Returns:
            매칭 대상 CrawledPost 목록
        """
        query = select(CrawledPost).where(
            and_(
                CrawledPost.blog_id == blog_id,
                CrawledPost.match_status.in_(["pending", "unmatched"]),
            )
        )
        result = await self.db.execute(query)
        posts = list(result.scalars().all())

        logger.debug(
            f"[AUTO_MATCH] 매칭 대상 포스트 조회 | "
            f"blog_id={blog_id} | count={len(posts)}"
        )
        return posts

    async def _get_category_filtered_titles(
        self, blog_id: int
    ) -> List[MainTitle]:
        """
        블로그 카테고리에 해당하는 MainTitle 조회

        BlogCategory에서 해당 blog_id의 활성 카테고리를 조회한 뒤,
        subtopic_id/topic_id 기준으로 MainTitle을 필터링합니다.
        활성 카테고리가 없으면 전체 MainTitle을 반환합니다.

        Args:
            blog_id: 블로그 ID

        Returns:
            필터링된 MainTitle 목록
        """
        # BlogCategory에서 해당 blog_id의 활성 카테고리 조회
        bc_query = select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active == True,
        )
        bc_result = await self.db.execute(bc_query)
        blog_categories = bc_result.scalars().all()

        # 기본 쿼리: 사용 가능한 상태의 MainTitle만
        query = select(MainTitle).where(
            MainTitle.status.in_(["available", "matched", "used"])
        )

        # 카테고리가 없는 경우 전체 MainTitle 반환 (필터 미적용)
        if not blog_categories:
            logger.debug(
                f"[AUTO_MATCH] 활성 카테고리 없음, 전체 MainTitle 사용 | "
                f"blog_id={blog_id}"
            )
            result = await self.db.execute(query)
            return list(result.scalars().all())

        # subtopic_id / topic_id 분리 수집
        subtopic_ids: set = set()
        topic_only_ids: set = set()

        for bc in blog_categories:
            if bc.subtopic_id:
                subtopic_ids.add(bc.subtopic_id)
            elif bc.topic_id:
                topic_only_ids.add(bc.topic_id)

        # OR 조건 구성
        conditions: list = []
        if subtopic_ids:
            conditions.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
        if topic_only_ids:
            conditions.append(MainTitle.topic_id.in_(list(topic_only_ids)))

        if conditions:
            query = query.where(or_(*conditions))

        result = await self.db.execute(query)
        titles = list(result.scalars().all())

        logger.debug(
            f"[AUTO_MATCH] 카테고리 필터링 MainTitle 조회 | "
            f"blog_id={blog_id} | subtopic_ids={subtopic_ids} | "
            f"topic_only_ids={topic_only_ids} | count={len(titles)}"
        )
        return titles

    def _find_best_match(
        self,
        post_title: str,
        main_titles: List[MainTitle],
    ) -> Tuple[Optional[int], float]:
        """
        V3 유사도 기반 최적 매칭 찾기

        SimilarityService.calculate_similarity_v2()를 사용하여
        크롤링 포스트 제목과 가장 유사한 MainTitle을 찾습니다.

        Args:
            post_title: 크롤링 포스트 제목
            main_titles: 후보 MainTitle 목록

        Returns:
            (best_title_id, best_score) 튜플.
            매칭 후보가 없으면 (None, 0.0)
        """
        best_title_id: Optional[int] = None
        best_score: float = 0.0

        for title in main_titles:
            score = self.similarity_service.calculate_similarity_v2(
                post_title, title.title
            )

            if score > best_score:
                best_score = score
                best_title_id = title.id

        return best_title_id, best_score
