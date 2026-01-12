"""
블로그 URL 수집 이력 모델
- 중복 수집 방지 (보류 기간 관리)
- 연속 에러 시 자동 비활성화
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class BlogUrlHistory(Base):
    """블로그 URL 수집 이력 - 중복 수집 방지 및 보류 기간 관리"""
    __tablename__ = "blog_url_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 블로그 정보
    blog_url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True, index=True)
    blog_platform: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    blog_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # 수집 통계
    total_posts_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_posts_count: Mapped[int] = mapped_column(Integer, default=0)
    collection_count: Mapped[int] = mapped_column(Integer, default=0)
    # 수집 일정
    last_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    hold_days: Mapped[int] = mapped_column(Integer, default=30)
    next_collection_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_blog_url_next_collection', 'next_collection_date', 'is_active'),
        Index('ix_blog_url_platform', 'blog_platform'),
    )

    def __repr__(self) -> str:
        return f"<BlogUrlHistory(id={self.id}, url='{self.blog_url[:50]}...')>"

    def update_collection(self, posts_count: int) -> None:
        """수집 완료 후 이력 갱신"""
        self.collected_posts_count += posts_count
        self.collection_count += 1
        self.last_collected_at = datetime.now()
        self.next_collection_date = datetime.now() + timedelta(days=self.hold_days)
        self.last_error = None
        self.error_count = 0

    def record_error(self, error_message: str) -> None:
        """에러 기록 (연속 5회 이상 시 비활성화)"""
        self.last_error = error_message[:500]
        self.error_count += 1
        if self.error_count >= 5:
            self.is_active = False

    @property
    def can_collect(self) -> bool:
        """수집 가능 여부"""
        return self.is_active and datetime.now() >= self.next_collection_date
