"""
키워드 모델 정의

Features:
- KeywordCategory: 계층형 키워드 카테고리
- CollectedKeyword: 수집된 연관 키워드
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Float, ForeignKey, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..core.database import Base

if TYPE_CHECKING:
    pass


class KeywordCategory(Base):
    """
    키워드 카테고리

    계층 구조를 지원하며 키워드 분류에 사용됩니다.
    예: 건강 > 반려동물 > 강아지
    """
    __tablename__ = "keyword_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="카테고리명")
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("keyword_categories.id"),
        nullable=True,
        comment="상위 카테고리 ID"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="카테고리 설명"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="활성 상태")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 자기참조 관계 (계층 구조)
    parent: Mapped[Optional["KeywordCategory"]] = relationship(
        "KeywordCategory",
        remote_side=[id],
        backref="children"
    )

    # 하위 관계
    collected_keywords: Mapped[List["CollectedKeyword"]] = relationship(
        "CollectedKeyword",
        back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<KeywordCategory(id={self.id}, name='{self.name}')>"


class CollectedKeyword(Base):
    """
    수집된 연관 키워드

    시드 키워드를 기반으로 API에서 확장 수집한 키워드입니다.
    이 키워드로 제목을 수집합니다.
    """
    __tablename__ = "collected_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    keyword: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="수집된 키워드"
    )
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="수집 소스 (google_trends|naver_datalab|naver_ads)"
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("keyword_categories.id"),
        nullable=True,
        comment="카테고리 ID"
    )
    search_volume: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="검색량"
    )
    competition: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="경쟁도 (0.0~1.0)"
    )
    is_processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="제목 수집 완료 여부"
    )
    process_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="처리 횟수"
    )
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 처리 시각"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # 관계
    category: Mapped[Optional["KeywordCategory"]] = relationship(
        "KeywordCategory",
        back_populates="collected_keywords"
    )

    # 유니크 제약조건: keyword + source + created_at 날짜 기준 (같은 날 같은 소스에서 중복 방지)
    # seed_keyword_id가 NULL일 수 있으므로 다른 조합 사용
    __table_args__ = (
        UniqueConstraint('keyword', 'source', name='uq_collected_keyword_source'),
    )

    def __repr__(self) -> str:
        return f"<CollectedKeyword(id={self.id}, keyword='{self.keyword}')>"

    def mark_processed(self) -> None:
        """처리 완료 표시"""
        self.is_processed = True
        self.process_count += 1
        self.last_processed_at = datetime.now()
