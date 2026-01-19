"""
카테고리 매칭 서비스

수집된 키워드/제목에서 카테고리 관리(Topic > SubTopic > Keyword)의
키워드를 찾아 자동으로 카테고리를 할당합니다.

Features:
- 키워드 포함 여부 기반 매칭
- Topic/SubTopic 정보 저장 (주제/하위 주제까지만 표시)
- 캐시를 통한 성능 최적화
"""
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.category import Topic, SubTopic, Keyword
from ..core.logger import get_logger

logger = get_logger("category_matcher", "category_matcher.log")


class CategoryMatcherService:
    """카테고리 자동 매칭 서비스"""

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션
        """
        self.db = db
        self._keywords_cache: Optional[List[Dict[str, Any]]] = None

    async def _load_keywords(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        """
        카테고리 관리의 키워드 목록 로드 (캐시 적용)

        Returns:
            키워드 정보 리스트: [
                {
                    "keyword_id": int,
                    "keyword": str,
                    "keyword_lower": str,
                    "subtopic_id": int,
                    "subtopic_name": str,
                    "topic_id": int,
                    "topic_name": str
                }
            ]
        """
        if not force_reload and self._keywords_cache is not None:
            return self._keywords_cache

        try:
            # Topic > SubTopic > Keyword 전체 조회 (삭제되지 않은 것만)
            query = (
                select(Topic)
                .where(Topic.is_deleted == False)
                .options(
                    selectinload(Topic.subtopics)
                    .selectinload(SubTopic.keywords)
                )
            )
            result = await self.db.execute(query)
            topics = result.scalars().all()

            keywords_list = []
            for topic in topics:
                if not topic.subtopics:
                    continue

                for subtopic in topic.subtopics:
                    if subtopic.is_deleted or not subtopic.keywords:
                        continue

                    for keyword in subtopic.keywords:
                        if keyword.is_deleted:
                            continue

                        keywords_list.append({
                            "keyword_id": keyword.id,
                            "keyword": keyword.name,
                            "keyword_lower": keyword.name.lower(),
                            "subtopic_id": subtopic.id,
                            "subtopic_name": subtopic.name,
                            "topic_id": topic.id,
                            "topic_name": topic.name
                        })

            self._keywords_cache = keywords_list
            logger.info(f"[CATEGORY_MATCHER] 키워드 캐시 로드: {len(keywords_list)}개")

            return keywords_list

        except Exception as e:
            logger.error(f"[CATEGORY_MATCHER] 키워드 로드 실패: {e}")
            return []

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._keywords_cache = None

    async def match_category(
        self,
        text: str
    ) -> Optional[Dict[str, Any]]:
        """
        텍스트에서 카테고리 키워드 매칭

        Args:
            text: 검색할 텍스트 (키워드 또는 제목)

        Returns:
            매칭 결과: {
                "topic_id": int,
                "topic_name": str,
                "subtopic_id": int,
                "subtopic_name": str,
                "matched_keyword_id": int,
                "matched_keyword": str,
                "category_path": str  # "주제/하위 주제"
            }
            또는 None (매칭 없음)
        """
        if not text or len(text.strip()) < 2:
            return None

        text_lower = text.lower()
        keywords = await self._load_keywords()

        if not keywords:
            return None

        # 가장 긴 키워드부터 매칭 시도 (더 구체적인 매칭 우선)
        sorted_keywords = sorted(keywords, key=lambda x: len(x["keyword"]), reverse=True)

        for kw in sorted_keywords:
            if kw["keyword_lower"] in text_lower:
                category_path = f"{kw['topic_name']} - {kw['subtopic_name']}"

                logger.debug(
                    f"[CATEGORY_MATCHER] 매칭 성공: '{text[:30]}...' → "
                    f"'{kw['keyword']}' ({category_path})"
                )

                return {
                    "topic_id": kw["topic_id"],
                    "topic_name": kw["topic_name"],
                    "subtopic_id": kw["subtopic_id"],
                    "subtopic_name": kw["subtopic_name"],
                    "matched_keyword_id": kw["keyword_id"],
                    "matched_keyword": kw["keyword"],
                    "category_path": category_path
                }

        return None

    async def match_and_apply_to_keyword(
        self,
        keyword_text: str
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        키워드 텍스트에 카테고리 매칭 후 ID 반환

        Args:
            keyword_text: 키워드 텍스트

        Returns:
            (topic_id, subtopic_id, matched_keyword_id) 튜플
        """
        match = await self.match_category(keyword_text)
        if match:
            return (
                match["topic_id"],
                match["subtopic_id"],
                match["matched_keyword_id"]
            )
        return (None, None, None)

    async def match_and_apply_to_title(
        self,
        title_text: str
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        제목 텍스트에 카테고리 매칭 후 ID 반환

        Args:
            title_text: 제목 텍스트

        Returns:
            (topic_id, subtopic_id, matched_keyword_id) 튜플
        """
        match = await self.match_category(title_text)
        if match:
            return (
                match["topic_id"],
                match["subtopic_id"],
                match["matched_keyword_id"]
            )
        return (None, None, None)

    async def get_category_stats(self) -> Dict[str, Any]:
        """
        카테고리 매칭용 통계 조회

        Returns:
            통계 정보
        """
        keywords = await self._load_keywords()

        # 주제별 키워드 수 집계
        topic_counts: Dict[str, int] = {}
        for kw in keywords:
            topic_name = kw["topic_name"]
            topic_counts[topic_name] = topic_counts.get(topic_name, 0) + 1

        return {
            "total_keywords": len(keywords),
            "topic_counts": topic_counts
        }
