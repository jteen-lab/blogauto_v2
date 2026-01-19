"""
콘텐츠 필터 모델

Features:
- 부적절한 키워드/제목 차단 규칙
- 시스템 기본 필터 + 사용자 추가 필터
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ContentFilter(Base):
    """
    콘텐츠 필터 규칙

    filter_type:
    - keyword: 키워드 포함 시 차단
    - pattern: 정규식 패턴 매칭 시 차단
    - domain: 특정 도메인 차단

    target_type:
    - keyword: 키워드 수집 시 적용
    - title: 제목 수집 시 적용
    - both: 둘 다 적용
    """
    __tablename__ = "content_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="필터 이름"
    )
    filter_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="keyword",
        comment="필터 타입 (keyword|pattern|domain)"
    )
    filter_value: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="필터 값"
    )
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="both",
        comment="적용 대상 (keyword|title|both)"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="필터 설명"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="시스템 기본 필터 여부"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="활성 상태"
    )
    match_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="매칭 횟수"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ContentFilter(id={self.id}, name='{self.name}')>"

    def increment_match(self) -> None:
        """매칭 횟수 증가"""
        self.match_count += 1
