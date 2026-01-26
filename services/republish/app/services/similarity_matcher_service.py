"""
유사도 매칭 서비스

MainTitle과 CrawledPost 간의 유사도를 계산하고
매칭/미매칭 2단계로 분류합니다.

Features:
- 제목 유사도 계산 (Jaccard, 형태소 기반)
- 배치 매칭 처리
- 임계값 기반 2단계 분류 (matched/unmatched)
- 백그라운드 비동기 매칭
"""
import re
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Set
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func

from ..models.blog import Blog
from ..models.crawled_post import CrawledPost
from ..models.title import MainTitle
from ..core.logger import get_logger

logger = get_logger("similarity_matcher", "matching.log")


@dataclass
class MatchResult:
    """매칭 결과"""
    crawled_post_id: int
    main_title_id: Optional[int]
    score: float
    is_matched: bool


@dataclass
class MatchingSummary:
    """매칭 요약"""
    total_crawled: int
    matched_count: int
    unmatched_count: int
    pending_count: int


class SimilarityMatcherService:
    """유사도 매칭 서비스"""

    # 기본 매칭 임계값 (65%)
    DEFAULT_THRESHOLD = 65.0

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def match_blog_posts(
        self,
        blog_id: int,
        threshold: float = DEFAULT_THRESHOLD
    ) -> Tuple[int, int]:
        """
        블로그의 크롤링 포스트와 메인 타이틀 매칭

        Args:
            blog_id: 블로그 ID
            threshold: 매칭 임계값 (기본 65%)

        Returns:
            (매칭된 수, 미매칭 수)
        """
        logger.info(f"유사도 매칭 시작 | 블로그ID={blog_id} | 임계값={threshold}%")

        # 1. 대기 상태인 크롤링 포스트 조회
        pending_posts = await self._get_pending_posts(blog_id)
        if not pending_posts:
            logger.info(f"매칭 대상 없음 | 블로그ID={blog_id}")
            # 매칭 대상이 없어도 상태를 synced로 업데이트
            blog = await self.db.get(Blog, blog_id)
            if blog:
                blog.crawl_status = "synced"
                blog.last_matched_at = datetime.now()
                await self.db.commit()
            return 0, 0

        # 2. 메인 타이틀 조회
        main_titles = await self._get_main_titles()
        if not main_titles:
            logger.warning(f"메인 타이틀 없음 - 모두 미매칭 처리 | 블로그ID={blog_id}")
            await self._mark_all_unmatched(pending_posts)
            return 0, len(pending_posts)

        # 3. 메인 타이틀 토큰 캐시 생성
        title_tokens = self._tokenize_titles(main_titles)

        # 4. 배치 매칭 처리
        matched_count = 0
        unmatched_count = 0

        for post in pending_posts:
            result = await self._find_best_match(
                post,
                main_titles,
                title_tokens,
                threshold
            )

            if result.is_matched:
                post.mark_matched(result.main_title_id, result.score)
                matched_count += 1
            else:
                post.mark_unmatched(result.score if result.score > 0 else None)
                unmatched_count += 1

        # 5. 커밋 및 블로그 상태 업데이트
        blog = await self.db.get(Blog, blog_id)
        if blog:
            blog.matched_count = await self._get_matched_count(blog_id)
            blog.last_matched_at = datetime.now()
            blog.crawl_status = "synced"

        await self.db.commit()

        logger.info(f"유사도 매칭 완료 | 블로그ID={blog_id} | 매칭={matched_count} | 미매칭={unmatched_count}")

        return matched_count, unmatched_count

    async def _get_pending_posts(self, blog_id: int) -> List[CrawledPost]:
        """대기 상태 포스트 조회"""
        result = await self.db.execute(
            select(CrawledPost).where(
                and_(
                    CrawledPost.blog_id == blog_id,
                    CrawledPost.match_status == "pending"
                )
            )
        )
        return list(result.scalars().all())

    async def _get_main_titles(self) -> List[MainTitle]:
        """사용 가능한 메인 타이틀 조회"""
        result = await self.db.execute(
            select(MainTitle).where(
                MainTitle.status.in_(["available", "matched", "used"])
            )
        )
        return list(result.scalars().all())

    def _tokenize_titles(
        self,
        titles: List[MainTitle]
    ) -> Dict[int, Set[str]]:
        """메인 타이틀 토큰화 (캐시용)"""
        tokens = {}
        for title in titles:
            tokens[title.id] = self._tokenize(title.title)
        return tokens

    async def _find_best_match(
        self,
        post: CrawledPost,
        main_titles: List[MainTitle],
        title_tokens: Dict[int, Set[str]],
        threshold: float
    ) -> MatchResult:
        """
        크롤링 포스트에 대한 최적 매칭 찾기

        Returns:
            MatchResult: 매칭 결과
        """
        post_tokens = self._tokenize(post.title)

        best_match_id = None
        best_score = 0.0

        for title in main_titles:
            title_token_set = title_tokens.get(title.id, set())

            # Jaccard 유사도 계산
            score = self._calculate_jaccard_similarity(post_tokens, title_token_set)

            if score > best_score:
                best_score = score
                best_match_id = title.id

        # 점수를 백분율로 변환
        score_percent = best_score * 100

        return MatchResult(
            crawled_post_id=post.id,
            main_title_id=best_match_id if score_percent >= threshold else None,
            score=score_percent,
            is_matched=score_percent >= threshold
        )

    def _tokenize(self, text: str) -> Set[str]:
        """
        텍스트 토큰화

        한글 형태소 분석기가 없으므로 단순 토큰화 사용:
        - 공백 기준 분리
        - 특수문자 제거
        - 소문자 변환
        - 2자 이상 토큰만 유지
        """
        # 특수문자 제거 및 공백 분리
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.lower().split()

        # 2자 이상 토큰만 유지 (조사/접속사 등 제거 효과)
        return {token for token in tokens if len(token) >= 2}

    def _calculate_jaccard_similarity(
        self,
        set1: Set[str],
        set2: Set[str]
    ) -> float:
        """
        Jaccard 유사도 계산

        J(A,B) = |A ∩ B| / |A ∪ B|
        """
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    async def _mark_all_unmatched(self, posts: List[CrawledPost]) -> None:
        """모든 포스트를 미매칭으로 처리"""
        for post in posts:
            post.mark_unmatched()
        await self.db.commit()

    async def _get_matched_count(self, blog_id: int) -> int:
        """블로그의 매칭된 포스트 수 조회"""
        result = await self.db.execute(
            select(func.count(CrawledPost.id)).where(
                and_(
                    CrawledPost.blog_id == blog_id,
                    CrawledPost.match_status == "matched"
                )
            )
        )
        return result.scalar() or 0

    async def get_matching_summary(self, blog_id: int) -> MatchingSummary:
        """
        블로그의 매칭 요약 정보 조회

        Args:
            blog_id: 블로그 ID

        Returns:
            MatchingSummary: 매칭 요약
        """
        result = await self.db.execute(
            select(
                CrawledPost.match_status,
                func.count(CrawledPost.id)
            ).where(
                CrawledPost.blog_id == blog_id
            ).group_by(CrawledPost.match_status)
        )

        counts = {row[0]: row[1] for row in result.fetchall()}

        return MatchingSummary(
            total_crawled=sum(counts.values()),
            matched_count=counts.get("matched", 0),
            unmatched_count=counts.get("unmatched", 0),
            pending_count=counts.get("pending", 0)
        )

    async def get_matching_pairs(
        self,
        blog_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        블로그의 매칭 페어 조회

        Args:
            blog_id: 블로그 ID
            limit: 조회 개수
            offset: 시작 위치

        Returns:
            매칭 페어 목록 (크롤링 포스트 + 매칭된 메인 타이틀)
        """
        result = await self.db.execute(
            select(CrawledPost, MainTitle)
            .outerjoin(MainTitle, CrawledPost.matched_main_title_id == MainTitle.id)
            .where(CrawledPost.blog_id == blog_id)
            .order_by(CrawledPost.match_status.desc(), CrawledPost.crawled_at.desc())
            .offset(offset)
            .limit(limit)
        )

        pairs = []
        for cp, mt in result.fetchall():
            pairs.append({
                "crawled_post": {
                    "id": cp.id,
                    "title": cp.title,
                    "url": cp.url,
                    "match_status": cp.match_status,
                    "match_score": cp.match_score,
                    "crawled_at": cp.crawled_at
                },
                "main_title": {
                    "id": mt.id,
                    "title": mt.title,
                    "status": mt.status
                } if mt else None
            })

        return pairs

    async def rematch_post(
        self,
        crawled_post_id: int,
        main_title_id: Optional[int],
        score: float = 100.0
    ) -> bool:
        """
        수동 매칭 조정

        Args:
            crawled_post_id: 크롤링 포스트 ID
            main_title_id: 매칭할 메인 타이틀 ID (None이면 미매칭)
            score: 점수 (수동 매칭은 100%)

        Returns:
            성공 여부
        """
        post = await self.db.get(CrawledPost, crawled_post_id)
        if not post:
            return False

        if main_title_id:
            post.mark_matched(main_title_id, score)
        else:
            post.mark_unmatched()

        await self.db.commit()

        logger.info(
            f"수동 매칭 조정 | 포스트ID={crawled_post_id} | "
            f"타이틀ID={main_title_id} | 점수={score}"
        )

        return True
