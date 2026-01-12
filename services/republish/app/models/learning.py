"""
학습 데이터 모델
- FilterLearningData: 필터링 학습 데이터
- SimilarityLearningData: 유사도 학습 데이터
"""
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, Float, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


def generate_title_hash(title: str) -> str:
    """제목 해시 생성"""
    return hashlib.sha256(title.encode()).hexdigest()


def generate_pair_hash(title_a: str, title_b: str) -> str:
    """제목 쌍 해시 생성 (순서 무관)"""
    sorted_titles = sorted([title_a, title_b])
    combined = f"{sorted_titles[0]}||{sorted_titles[1]}"
    return hashlib.sha256(combined.encode()).hexdigest()


class FilterLearningData(Base):
    """필터링 학습 데이터 - 사용자 필터링/승인 기록"""
    __tablename__ = "filter_learning_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 제목 정보
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    title_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 필터링 정보
    filter_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    filter_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    keywords_detected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 사용자 판단: filtered | approved | auto_filtered
    user_action: Mapped[str] = mapped_column(String(50), nullable=False)
    # 학습 메트릭
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_trained: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_filter_learning_action', 'user_action'),
        Index('ix_filter_learning_type', 'filter_type'),
    )

    def __repr__(self) -> str:
        return f"<FilterLearningData(id={self.id}, action='{self.user_action}')>"

    @classmethod
    def create_hash(cls, title: str) -> str:
        """제목 해시 생성"""
        return generate_title_hash(title)


class SimilarityLearningData(Base):
    """유사도 학습 데이터 - 유사/다름 판단 기록"""
    __tablename__ = "similarity_learning_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 비교 제목
    title_a: Mapped[str] = mapped_column(String(500), nullable=False)
    title_b: Mapped[str] = mapped_column(String(500), nullable=False)
    pair_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 유사도 정보
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    similarity_algorithm: Mapped[str] = mapped_column(String(50), default="combined")
    # 공통 요소
    common_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    common_patterns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 사용자 판단: matched | rejected | grouped | separated
    is_similar: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_action: Mapped[str] = mapped_column(String(50), nullable=False)
    # 학습 메트릭
    is_trained: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_similarity_learning_action', 'user_action'),
        Index('ix_similarity_learning_score', 'similarity_score'),
    )

    def __repr__(self) -> str:
        return f"<SimilarityLearningData(id={self.id}, similar={self.is_similar})>"

    @classmethod
    def create_pair_hash(cls, title_a: str, title_b: str) -> str:
        """제목 쌍 해시 생성 (순서 무관)"""
        return generate_pair_hash(title_a, title_b)
