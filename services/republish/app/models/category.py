"""
카테고리 관리 모델

Features:
- 3계층 카테고리 구조 (Topic > SubTopic > Keyword)
- 블로그별 카테고리 연결
- 소프트 삭제 지원
- 사용자 전용 카테고리 관리
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Dict, Any

from ..core.database import Base


class Topic(Base):
    """주제 (1차 카테고리) 모델"""
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="주제명")
    description = Column(Text, nullable=True, comment="주제 설명")
    order = Column(Integer, default=0, comment="정렬 순서")

    # 소프트 삭제
    is_deleted = Column(Boolean, default=False, index=True)

    # 시간 정보
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    user = relationship("User", back_populates="topics")
    subtopics = relationship("SubTopic", back_populates="topic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Topic(id={self.id}, name='{self.name}', user_id={self.user_id})>"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None
        }

    def soft_delete(self):
        """소프트 삭제"""
        self.is_deleted = True
        self.deleted_at = func.now()


class SubTopic(Base):
    """하위 주제 (2차 카테고리) 모델"""
    __tablename__ = "subtopics"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="하위 주제명")
    description = Column(Text, nullable=True, comment="하위 주제 설명")
    order = Column(Integer, default=0, comment="정렬 순서")

    # 소프트 삭제
    is_deleted = Column(Boolean, default=False, index=True)

    # 시간 정보
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    topic = relationship("Topic", back_populates="subtopics")
    keywords = relationship("Keyword", back_populates="subtopic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SubTopic(id={self.id}, name='{self.name}', topic_id={self.topic_id})>"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None
        }

    def soft_delete(self):
        """소프트 삭제"""
        self.is_deleted = True
        self.deleted_at = func.now()


class Keyword(Base):
    """키워드 (3차 카테고리) 모델"""
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    subtopic_id = Column(Integer, ForeignKey("subtopics.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="키워드명")
    description = Column(Text, nullable=True, comment="키워드 설명")
    order = Column(Integer, default=0, comment="정렬 순서")

    # 추가 속성
    search_volume = Column(Integer, default=0, comment="검색량 (선택사항)")
    difficulty = Column(Integer, default=0, comment="난이도 (1-10)")

    # 소프트 삭제
    is_deleted = Column(Boolean, default=False, index=True)

    # 시간 정보
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # 관계
    subtopic = relationship("SubTopic", back_populates="keywords")

    def __repr__(self):
        return f"<Keyword(id={self.id}, name='{self.name}', subtopic_id={self.subtopic_id})>"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "subtopic_id": self.subtopic_id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "search_volume": self.search_volume,
            "difficulty": self.difficulty,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None
        }

    def soft_delete(self):
        """소프트 삭제"""
        self.is_deleted = True
        self.deleted_at = func.now()


class BlogCategory(Base):
    """블로그-카테고리 연결 모델"""
    __tablename__ = "blog_categories"

    id = Column(Integer, primary_key=True, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, index=True)

    # 카테고리 연결 (선택적 - 하나 이상 필수)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True, index=True)
    subtopic_id = Column(Integer, ForeignKey("subtopics.id"), nullable=True, index=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=True, index=True)

    # 추가 설정
    priority = Column(Integer, default=1, comment="우선순위 (1-10)")
    is_active = Column(Boolean, default=True, comment="활성화 상태")

    # 시간 정보
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계
    blog = relationship("Blog")
    topic = relationship("Topic")
    subtopic = relationship("SubTopic")
    keyword = relationship("Keyword")

    def __repr__(self):
        return f"<BlogCategory(blog_id={self.blog_id}, topic_id={self.topic_id}, subtopic_id={self.subtopic_id}, keyword_id={self.keyword_id})>"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "blog_id": self.blog_id,
            "topic_id": self.topic_id,
            "subtopic_id": self.subtopic_id,
            "keyword_id": self.keyword_id,
            "priority": self.priority,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @property
    def category_path(self) -> str:
        """카테고리 경로 문자열 생성"""
        parts = []
        if self.topic and hasattr(self.topic, 'name'):
            parts.append(self.topic.name)
        if self.subtopic and hasattr(self.subtopic, 'name'):
            parts.append(self.subtopic.name)
        if self.keyword and hasattr(self.keyword, 'name'):
            parts.append(self.keyword.name)
        return " > ".join(parts)