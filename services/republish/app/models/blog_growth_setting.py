"""
블로그 성장 단계별 설정 모델

설계 문서: generation_module_workplan.md - Phase 1 - 1.2.2

성장 단계 기준:
- 급성장기: 발행된 글 수 <= rapid_growth_threshold (기본 50)
- 성장기: 발행된 글 수 <= growth_threshold (기본 150)
- 안정기: 그 외
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..core.database import Base

if TYPE_CHECKING:
    from .blog import Blog


class BlogGrowthSetting(Base):
    """블로그 성장 단계별 설정"""

    __tablename__ = "blog_growth_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # 급성장기 설정 (발행글 수 <= rapid_growth_threshold)
    rapid_growth_threshold: Mapped[int] = mapped_column(
        Integer, default=50, comment="급성장기 기준 (이 수 이하)"
    )
    rapid_growth_inventory: Mapped[int] = mapped_column(
        Integer, default=10, comment="급성장기 재고 기준값"
    )

    # 성장기 설정 (발행글 수 <= growth_threshold)
    growth_threshold: Mapped[int] = mapped_column(
        Integer, default=150, comment="성장기 기준 (이 수 이하)"
    )
    growth_inventory: Mapped[int] = mapped_column(
        Integer, default=5, comment="성장기 재고 기준값"
    )

    # 안정기 설정 (그 외)
    stable_inventory: Mapped[int] = mapped_column(
        Integer, default=2, comment="안정기 재고 기준값"
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    blog: Mapped["Blog"] = relationship("Blog", back_populates="growth_setting")

    def get_inventory_threshold(self, current_post_count: int) -> int:
        """
        현재 발행글 수에 따른 재고 기준값 반환

        Args:
            current_post_count: 현재 발행된 글 수

        Returns:
            재고 기준값
        """
        if current_post_count <= self.rapid_growth_threshold:
            return self.rapid_growth_inventory
        elif current_post_count <= self.growth_threshold:
            return self.growth_inventory
        else:
            return self.stable_inventory

    def get_growth_stage(self, current_post_count: int) -> str:
        """
        현재 발행글 수에 따른 성장 단계 반환

        Args:
            current_post_count: 현재 발행된 글 수

        Returns:
            성장 단계 ("rapid_growth", "growth", "stable")
        """
        if current_post_count <= self.rapid_growth_threshold:
            return "rapid_growth"
        elif current_post_count <= self.growth_threshold:
            return "growth"
        else:
            return "stable"

    def __repr__(self) -> str:
        """문자열 표현"""
        return (
            f"<BlogGrowthSetting(blog_id={self.blog_id}, "
            f"rapid={self.rapid_growth_inventory}, "
            f"growth={self.growth_inventory}, "
            f"stable={self.stable_inventory})>"
        )
