"""
카테고리 관리 비즈니스 로직 (Async Optimized)

Features:
- 3계층 카테고리 CRUD 작업
- 블로그-카테고리 연결 관리
- 계층적 데이터 조회
- 보안 및 권한 검증
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, asc, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from ..models.category import Topic, SubTopic, Keyword, BlogCategory
from ..models.user import User
from ..models.blog import Blog
from ..schemas.category import (
    TopicCreateRequest, TopicUpdateRequest, TopicResponse,
    SubTopicCreateRequest, SubTopicUpdateRequest, SubTopicResponse,
    KeywordCreateRequest, KeywordUpdateRequest, KeywordResponse,
    BlogCategoryCreateRequest, BlogCategoryUpdateRequest, BlogCategoryResponse,
    CategoryStatsResponse
)
from ..core.logger import get_logger

logger = get_logger("category_service", "category.log")


class CategoryService:
    """카테고리 서비스 클래스"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ===============================
    # Topic (주제) 관련 메서드
    # ===============================

    async def create_topic(self, user: User, request: TopicCreateRequest) -> TopicResponse:
        """
        주제 생성

        Args:
            user: 사용자 객체
            request: 주제 생성 요청

        Returns:
            생성된 주제 정보

        Raises:
            HTTPException: 생성 실패시
        """
        logger.info(f"주제 생성 시도 | 사용자={user.id} | 이름={request.name}")

        # 중복 이름 확인
        await self._check_duplicate_topic_name(user.id, request.name)

        try:
            topic = Topic(
                user_id=user.id,
                name=request.name,
                description=request.description,
                order=request.order
            )

            self.db.add(topic)
            await self.db.commit()
            await self.db.refresh(topic)

            logger.info(f"주제 생성 완료 | 주제ID={topic.id} | 사용자={user.id}")

            # 통계 정보 추가
            topic_data = topic.to_dict()
            topic_data.update({
                "subtopic_count": 0,
                "keyword_count": 0
            })

            return TopicResponse(**topic_data)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"주제 생성 실패 | 사용자={user.id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="주제 생성 중 오류가 발생했습니다"
            )

    async def get_user_topics(self, user: User, include_deleted: bool = False) -> List[TopicResponse]:
        """
        사용자 주제 목록 조회

        Args:
            user: 사용자 객체
            include_deleted: 삭제된 항목 포함 여부

        Returns:
            주제 목록
        """
        query = select(Topic).where(Topic.user_id == user.id)

        if not include_deleted:
            query = query.where(Topic.is_deleted == False)

        query = query.order_by(asc(Topic.name))

        result = await self.db.execute(query)
        topics = result.scalars().all()

        # 통계 정보 추가
        topic_responses = []
        for topic in topics:
            topic_data = topic.to_dict()

            # 하위 항목 개수 조회
            subtopic_count = await self._count_subtopics(topic.id)
            keyword_count = await self._count_keywords_by_topic(topic.id)

            topic_data.update({
                "subtopic_count": subtopic_count,
                "keyword_count": keyword_count
            })

            topic_responses.append(TopicResponse(**topic_data))

        logger.info(f"주제 목록 조회 | 사용자={user.id} | 개수={len(topics)}")

        return topic_responses

    async def get_topic_by_id(self, user: User, topic_id: int) -> TopicResponse:
        """주제 상세 조회"""
        topic = await self._get_user_topic(user, topic_id)
        topic_data = topic.to_dict()

        # 통계 정보 추가
        subtopic_count = await self._count_subtopics(topic.id)
        keyword_count = await self._count_keywords_by_topic(topic.id)

        topic_data.update({
            "subtopic_count": subtopic_count,
            "keyword_count": keyword_count
        })

        return TopicResponse(**topic_data)

    async def update_topic(self, user: User, topic_id: int, request: TopicUpdateRequest) -> TopicResponse:
        """주제 수정"""
        topic = await self._get_user_topic(user, topic_id)

        logger.info(f"주제 수정 시도 | 주제ID={topic_id} | 사용자={user.id}")

        try:
            # 변경된 필드 추적
            changed_fields = []

            if request.name is not None:
                # 중복 이름 확인 (본인 제외)
                await self._check_duplicate_topic_name(user.id, request.name, topic_id)
                topic.name = request.name
                changed_fields.append("name")

            if request.description is not None:
                topic.description = request.description
                changed_fields.append("description")

            if request.order is not None:
                topic.order = request.order
                changed_fields.append("order")

            await self.db.commit()
            await self.db.refresh(topic)

            logger.info(f"주제 수정 완료 | 주제ID={topic_id} | 변경필드={changed_fields}")

            # 응답 데이터 생성
            topic_data = topic.to_dict()
            subtopic_count = await self._count_subtopics(topic.id)
            keyword_count = await self._count_keywords_by_topic(topic.id)

            topic_data.update({
                "subtopic_count": subtopic_count,
                "keyword_count": keyword_count
            })

            return TopicResponse(**topic_data)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"주제 수정 실패 | 주제ID={topic_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="주제 수정 중 오류가 발생했습니다"
            )

    async def delete_topic(self, user: User, topic_id: int) -> dict:
        """주제 삭제 (소프트 삭제)"""
        topic = await self._get_user_topic(user, topic_id)

        logger.info(f"주제 삭제 시도 | 주제ID={topic_id} | 사용자={user.id}")

        try:
            # 연관된 하위 항목들도 소프트 삭제
            await self._soft_delete_subtopics_by_topic(topic_id)

            topic.soft_delete()
            await self.db.commit()

            logger.info(f"주제 삭제 완료 | 주제ID={topic_id}")

            return {"message": f"주제 '{topic.name}'이 삭제되었습니다"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"주제 삭제 실패 | 주제ID={topic_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="주제 삭제 중 오류가 발생했습니다"
            )

    # ===============================
    # SubTopic (하위 주제) 관련 메서드
    # ===============================

    async def create_subtopic(self, user: User, request: SubTopicCreateRequest) -> SubTopicResponse:
        """하위 주제 생성"""
        # 상위 주제 검증
        topic = await self._get_user_topic(user, request.topic_id)

        logger.info(f"하위 주제 생성 시도 | 사용자={user.id} | 이름={request.name} | 상위주제={request.topic_id}")

        try:
            subtopic = SubTopic(
                topic_id=request.topic_id,
                name=request.name,
                description=request.description,
                order=request.order
            )

            self.db.add(subtopic)
            await self.db.commit()
            await self.db.refresh(subtopic)

            logger.info(f"하위 주제 생성 완료 | 하위주제ID={subtopic.id} | 사용자={user.id}")

            # 응답 데이터 생성
            subtopic_data = subtopic.to_dict()
            subtopic_data.update({
                "topic_name": topic.name,
                "keyword_count": 0
            })

            return SubTopicResponse(**subtopic_data)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"하위 주제 생성 실패 | 사용자={user.id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="하위 주제 생성 중 오류가 발생했습니다"
            )

    async def get_subtopics_by_topic(self, user: User, topic_id: int, include_deleted: bool = False) -> List[SubTopicResponse]:
        """주제별 하위 주제 목록 조회"""
        # 주제 검증
        topic = await self._get_user_topic(user, topic_id)

        query = select(SubTopic).where(SubTopic.topic_id == topic_id)

        if not include_deleted:
            query = query.where(SubTopic.is_deleted == False)

        query = query.order_by(asc(SubTopic.name))

        result = await self.db.execute(query)
        subtopics = result.scalars().all()

        # 응답 데이터 생성
        subtopic_responses = []
        for subtopic in subtopics:
            subtopic_data = subtopic.to_dict()
            keyword_count = await self._count_keywords_by_subtopic(subtopic.id)

            subtopic_data.update({
                "topic_name": topic.name,
                "keyword_count": keyword_count
            })

            subtopic_responses.append(SubTopicResponse(**subtopic_data))

        return subtopic_responses

    # ===============================
    # Keyword (키워드) 관련 메서드
    # ===============================

    async def create_keyword(self, user: User, request: KeywordCreateRequest) -> KeywordResponse:
        """키워드 생성"""
        # 상위 하위주제 검증 (그리고 간접적으로 사용자 권한도 검증)
        subtopic = await self._get_user_subtopic(user, request.subtopic_id)

        logger.info(f"키워드 생성 시도 | 사용자={user.id} | 이름={request.name} | 하위주제={request.subtopic_id}")

        # 전역 키워드 중복 검사 (모든 하위주제에서)
        await self._check_global_duplicate_keyword_name(user.id, request.name)

        try:
            keyword = Keyword(
                subtopic_id=request.subtopic_id,
                name=request.name,
                description=request.description,
                order=request.order,
                search_volume=request.search_volume,
                difficulty=request.difficulty,
                priority=request.priority
            )

            self.db.add(keyword)
            await self.db.commit()
            await self.db.refresh(keyword)

            logger.info(f"키워드 생성 완료 | 키워드ID={keyword.id} | 사용자={user.id}")

            # 응답 데이터 생성 (상위 정보 포함)
            return KeywordResponse(
                id=keyword.id,
                subtopic_id=keyword.subtopic_id,
                name=keyword.name,
                description=keyword.description,
                order=keyword.order,
                search_volume=keyword.search_volume,
                difficulty=keyword.difficulty,
                priority=keyword.priority,
                is_deleted=keyword.is_deleted,
                created_at=keyword.created_at,
                updated_at=keyword.updated_at
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"키워드 생성 실패 | 사용자={user.id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="키워드 생성 중 오류가 발생했습니다"
            )

    async def get_keywords_by_subtopic(self, user: User, subtopic_id: int, include_deleted: bool = False) -> List[KeywordResponse]:
        """하위주제별 키워드 목록 조회"""
        # 하위주제 검증
        subtopic = await self._get_user_subtopic(user, subtopic_id)

        query = select(Keyword).where(Keyword.subtopic_id == subtopic_id)

        if not include_deleted:
            query = query.where(Keyword.is_deleted == False)

        query = query.order_by(asc(Keyword.name))

        result = await self.db.execute(query)
        keywords = result.scalars().all()

        # 응답 데이터 생성
        keyword_responses = []
        for keyword in keywords:
            keyword_responses.append(KeywordResponse(
                id=keyword.id,
                subtopic_id=keyword.subtopic_id,
                name=keyword.name,
                description=keyword.description,
                order=keyword.order,
                search_volume=keyword.search_volume,
                difficulty=keyword.difficulty,
                priority=keyword.priority,
                is_deleted=keyword.is_deleted,
                created_at=keyword.created_at,
                updated_at=keyword.updated_at
            ))

        return keyword_responses

    # ===============================
    # 계층적 조회 메서드
    # ===============================


    async def get_category_stats(self, user: User) -> CategoryStatsResponse:
        """카테고리 통계 조회"""
        # 주제 수
        topic_count_query = select(func.count(Topic.id)).where(
            and_(Topic.user_id == user.id, Topic.is_deleted == False)
        )
        topic_result = await self.db.execute(topic_count_query)
        total_topics = topic_result.scalar() or 0

        # 하위 주제 수
        subtopic_count_query = select(func.count(SubTopic.id)).join(Topic).where(
            and_(Topic.user_id == user.id, Topic.is_deleted == False, SubTopic.is_deleted == False)
        )
        subtopic_result = await self.db.execute(subtopic_count_query)
        total_subtopics = subtopic_result.scalar() or 0

        # 키워드 수
        keyword_count_query = select(func.count(Keyword.id)).join(SubTopic).join(Topic).where(
            and_(
                Topic.user_id == user.id,
                Topic.is_deleted == False,
                SubTopic.is_deleted == False,
                Keyword.is_deleted == False
            )
        )
        keyword_result = await self.db.execute(keyword_count_query)
        total_keywords = keyword_result.scalar() or 0

        # 블로그 연결 수
        blog_connection_query = select(func.count(BlogCategory.id)).join(Blog).where(
            Blog.user_id == user.id
        )
        blog_connection_result = await self.db.execute(blog_connection_query)
        total_blog_connections = blog_connection_result.scalar() or 0

        return CategoryStatsResponse(
            total_topics=total_topics,
            total_subtopics=total_subtopics,
            total_keywords=total_keywords,
            total_blog_connections=total_blog_connections
        )

    # ===============================
    # 내부 헬퍼 메서드
    # ===============================

    async def _get_user_topic(self, user: User, topic_id: int) -> Topic:
        """사용자 주제 조회"""
        query = select(Topic).where(
            and_(
                Topic.id == topic_id,
                Topic.user_id == user.id,
                Topic.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        topic = result.scalar_one_or_none()

        if not topic:
            logger.warning(f"주제 없음 | 주제ID={topic_id} | 사용자={user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="주제를 찾을 수 없습니다"
            )

        return topic

    async def _get_user_subtopic(self, user: User, subtopic_id: int) -> SubTopic:
        """사용자 하위주제 조회 (상위 주제 포함)"""
        query = select(SubTopic).options(selectinload(SubTopic.topic)).join(Topic).where(
            and_(
                SubTopic.id == subtopic_id,
                Topic.user_id == user.id,
                Topic.is_deleted == False,
                SubTopic.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        subtopic = result.scalar_one_or_none()

        if not subtopic:
            logger.warning(f"하위주제 없음 | 하위주제ID={subtopic_id} | 사용자={user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="하위 주제를 찾을 수 없습니다"
            )

        return subtopic

    async def _check_duplicate_topic_name(self, user_id: int, name: str, exclude_id: Optional[int] = None) -> None:
        """주제명 중복 확인"""
        query = select(Topic).where(
            and_(
                Topic.user_id == user_id,
                Topic.name == name,
                Topic.is_deleted == False
            )
        )

        if exclude_id:
            query = query.where(Topic.id != exclude_id)

        result = await self.db.execute(query)
        existing_topic = result.scalar_one_or_none()

        if existing_topic:
            logger.warning(f"주제명 중복 | 사용자={user_id} | 이름={name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 존재하는 주제명입니다"
            )

    async def _count_subtopics(self, topic_id: int) -> int:
        """주제별 하위주제 개수"""
        query = select(func.count(SubTopic.id)).where(
            and_(SubTopic.topic_id == topic_id, SubTopic.is_deleted == False)
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_keywords_by_topic(self, topic_id: int) -> int:
        """주제별 키워드 개수"""
        query = select(func.count(Keyword.id)).join(SubTopic).where(
            and_(
                SubTopic.topic_id == topic_id,
                SubTopic.is_deleted == False,
                Keyword.is_deleted == False
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_keywords_by_subtopic(self, subtopic_id: int) -> int:
        """하위주제별 키워드 개수"""
        query = select(func.count(Keyword.id)).where(
            and_(Keyword.subtopic_id == subtopic_id, Keyword.is_deleted == False)
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _soft_delete_subtopics_by_topic(self, topic_id: int) -> None:
        """주제별 하위주제 소프트 삭제"""
        # 하위주제와 연관된 키워드들 먼저 삭제
        subtopics_query = select(SubTopic).where(
            and_(SubTopic.topic_id == topic_id, SubTopic.is_deleted == False)
        )
        subtopics_result = await self.db.execute(subtopics_query)
        subtopics = subtopics_result.scalars().all()

        for subtopic in subtopics:
            # 키워드들 소프트 삭제
            await self._soft_delete_keywords_by_subtopic(subtopic.id)
            # 하위주제 소프트 삭제
            subtopic.soft_delete()

    async def _soft_delete_keywords_by_subtopic(self, subtopic_id: int) -> None:
        """하위주제별 키워드 소프트 삭제"""
        keywords_query = select(Keyword).where(
            and_(Keyword.subtopic_id == subtopic_id, Keyword.is_deleted == False)
        )
        keywords_result = await self.db.execute(keywords_query)
        keywords = keywords_result.scalars().all()

        for keyword in keywords:
            keyword.soft_delete()

    # ===============================
    # 하위 주제 CRUD 메서드
    # ===============================

    async def update_subtopic(self, user: User, subtopic_id: int, request: SubTopicUpdateRequest) -> SubTopicResponse:
        """하위 주제 수정"""
        try:
            # 하위 주제 조회
            subtopic = await self._get_user_subtopic(user, subtopic_id)

            # 중복 확인 (같은 주제 내에서)
            await self._check_duplicate_subtopic_name(subtopic.topic_id, request.name, exclude_id=subtopic_id)

            # 업데이트
            subtopic.name = request.name
            subtopic.description = request.description
            subtopic.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(subtopic)

            # 키워드 개수 계산
            keyword_count = await self._count_keywords_by_subtopic(subtopic.id)

            logger.info(f"하위 주제 수정 성공 | 하위주제ID={subtopic.id} | 사용자={user.id}")

            return SubTopicResponse(
                id=subtopic.id,
                topic_id=subtopic.topic_id,
                name=subtopic.name,
                description=subtopic.description,
                order=subtopic.order,
                is_deleted=subtopic.is_deleted,
                created_at=subtopic.created_at,
                updated_at=subtopic.updated_at,
                topic_name=subtopic.topic.name if subtopic.topic else None,
                keyword_count=keyword_count
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"하위 주제 수정 실패 | 하위주제ID={subtopic_id} | 사용자={user.id} | 오류={e}")
            raise

    async def delete_subtopic(self, user: User, subtopic_id: int) -> dict:
        """하위 주제 삭제 (소프트 삭제)"""
        try:
            # 하위 주제 조회
            subtopic = await self._get_user_subtopic(user, subtopic_id)

            # 연관된 키워드들 소프트 삭제
            await self._soft_delete_keywords_by_subtopic(subtopic_id)

            # 하위 주제 소프트 삭제
            subtopic.soft_delete()

            await self.db.commit()

            logger.info(f"하위 주제 삭제 성공 | 하위주제ID={subtopic_id} | 사용자={user.id}")

            return {"message": "하위 주제가 삭제되었습니다", "subtopic_id": subtopic_id}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"하위 주제 삭제 실패 | 하위주제ID={subtopic_id} | 사용자={user.id} | 오류={e}")
            raise

    # ===============================
    # 키워드 CRUD 메서드
    # ===============================

    async def update_keyword(self, user: User, keyword_id: int, request: KeywordUpdateRequest) -> KeywordResponse:
        """키워드 수정"""
        try:
            # 키워드 조회
            keyword = await self._get_user_keyword(user, keyword_id)

            # 전역 중복 확인 (모든 하위주제에서)
            await self._check_global_duplicate_keyword_name(user.id, request.name, exclude_id=keyword_id)

            # 업데이트
            keyword.name = request.name
            keyword.description = request.description
            keyword.search_volume = request.search_volume
            keyword.difficulty = request.difficulty
            if request.priority is not None:
                keyword.priority = request.priority
            keyword.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(keyword)

            logger.info(f"키워드 수정 성공 | 키워드ID={keyword.id} | 사용자={user.id}")

            return KeywordResponse(
                id=keyword.id,
                subtopic_id=keyword.subtopic_id,
                name=keyword.name,
                description=keyword.description,
                order=keyword.order,
                search_volume=keyword.search_volume,
                difficulty=keyword.difficulty,
                priority=keyword.priority,
                is_deleted=keyword.is_deleted,
                created_at=keyword.created_at,
                updated_at=keyword.updated_at
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"키워드 수정 실패 | 키워드ID={keyword_id} | 사용자={user.id} | 오류={e}")
            raise

    async def delete_keyword(self, user: User, keyword_id: int) -> dict:
        """키워드 삭제 (소프트 삭제)"""
        try:
            # 키워드 조회
            keyword = await self._get_user_keyword(user, keyword_id)

            # 소프트 삭제
            keyword.soft_delete()

            await self.db.commit()

            logger.info(f"키워드 삭제 성공 | 키워드ID={keyword_id} | 사용자={user.id}")

            return {"message": "키워드가 삭제되었습니다", "keyword_id": keyword_id}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"키워드 삭제 실패 | 키워드ID={keyword_id} | 사용자={user.id} | 오류={e}")
            raise

    # ===============================
    # 추가 헬퍼 메서드
    # ===============================

    async def _get_user_keyword(self, user: User, keyword_id: int) -> Keyword:
        """사용자 키워드 조회 (상위 구조 포함)"""
        query = select(Keyword).options(selectinload(Keyword.subtopic).selectinload(SubTopic.topic)).join(SubTopic).join(Topic).where(
            and_(
                Keyword.id == keyword_id,
                Topic.user_id == user.id,
                Topic.is_deleted == False,
                SubTopic.is_deleted == False,
                Keyword.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        keyword = result.scalar_one_or_none()

        if not keyword:
            logger.warning(f"키워드 없음 | 키워드ID={keyword_id} | 사용자={user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="키워드를 찾을 수 없습니다"
            )

        return keyword

    async def _check_duplicate_subtopic_name(self, topic_id: int, name: str, exclude_id: Optional[int] = None) -> None:
        """하위 주제명 중복 확인"""
        query = select(SubTopic).where(
            and_(
                SubTopic.topic_id == topic_id,
                SubTopic.name == name,
                SubTopic.is_deleted == False
            )
        )

        if exclude_id:
            query = query.where(SubTopic.id != exclude_id)

        result = await self.db.execute(query)
        existing_subtopic = result.scalar_one_or_none()

        if existing_subtopic:
            logger.warning(f"하위 주제명 중복 | 주제ID={topic_id} | 이름={name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 존재하는 하위 주제명입니다"
            )

    async def _check_duplicate_keyword_name(self, subtopic_id: int, name: str, exclude_id: Optional[int] = None) -> None:
        """키워드명 중복 확인 (동일 하위주제 내)"""
        query = select(Keyword).where(
            and_(
                Keyword.subtopic_id == subtopic_id,
                Keyword.name == name,
                Keyword.is_deleted == False
            )
        )

        if exclude_id:
            query = query.where(Keyword.id != exclude_id)

        result = await self.db.execute(query)
        existing_keyword = result.scalar_one_or_none()

        if existing_keyword:
            logger.warning(f"키워드명 중복 | 하위주제ID={subtopic_id} | 이름={name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 존재하는 키워드명입니다"
            )

    async def _check_global_duplicate_keyword_name(self, user_id: int, name: str, exclude_id: Optional[int] = None) -> None:
        """키워드명 전역 중복 확인 (모든 하위주제에서)"""
        # 사용자의 모든 주제 > 하위주제 > 키워드를 검사
        query = (
            select(Keyword, SubTopic, Topic)
            .join(SubTopic, Keyword.subtopic_id == SubTopic.id)
            .join(Topic, SubTopic.topic_id == Topic.id)
            .where(
                and_(
                    Topic.user_id == user_id,
                    Keyword.name == name,
                    Keyword.is_deleted == False,
                    SubTopic.is_deleted == False,
                    Topic.is_deleted == False
                )
            )
        )

        if exclude_id:
            query = query.where(Keyword.id != exclude_id)

        result = await self.db.execute(query)
        existing = result.first()

        if existing:
            keyword, subtopic, topic = existing
            logger.warning(f"키워드명 전역 중복 | 이름={name} | 기존위치={topic.name} > {subtopic.name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"이미 '{topic.name} > {subtopic.name}'에 동일한 키워드가 존재합니다"
            )