"""
블로그 발행 비중 전략 모델

Features:
- 수동/자동 비중 조절
- 누적 포스트 수 기반 자동 비중 변경
- 신규 발행 우선 정책
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class BlogPublishStrategy(Base):
    """블로그 발행 비중 전략"""
    __tablename__ = "blog_publish_strategies"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, unique=True, index=True)

    # 비중 조절 모드
    strategy_mode = Column(String(10), default="auto", comment="비중 모드: auto/manual")

    # 수동 비중 설정
    publish_weight = Column(Integer, default=70, comment="신규 발행 비중 (0-100)")
    republish_weight = Column(Integer, default=30, comment="재발행 비중 (0-100)")

    # 자동 비중 조절 규칙
    auto_rules = Column(JSON, default=[
        {"min": 0, "max": 50, "publish": 100, "republish": 0},
        {"min": 51, "max": 100, "publish": 80, "republish": 20},
        {"min": 101, "max": 200, "publish": 50, "republish": 50},
        {"min": 201, "max": None, "publish": 30, "republish": 70}
    ], comment="자동 비중 조절 규칙")

    # 신규 발행 우선 정책
    min_daily_publish_for_skip = Column(Integer, default=1, comment="재발행 보류 기준 일일 신규 발행 수")

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    blog = relationship("Blog", back_populates="publish_strategy")

    def get_weights_by_post_count(self, total_posts: int) -> dict:
        """포스트 수에 따른 비중 반환"""
        if self.strategy_mode == "manual":
            return {
                "publish": self.publish_weight,
                "republish": self.republish_weight
            }

        # 자동 모드: 규칙에 따라 비중 결정
        for rule in self.auto_rules:
            min_posts = rule["min"]
            max_posts = rule["max"]

            if max_posts is None:  # 무제한 구간
                if total_posts >= min_posts:
                    return {
                        "publish": rule["publish"],
                        "republish": rule["republish"]
                    }
            else:  # 제한된 구간
                if min_posts <= total_posts <= max_posts:
                    return {
                        "publish": rule["publish"],
                        "republish": rule["republish"]
                    }

        # 기본값 (규칙에 맞지 않는 경우)
        return {"publish": 70, "republish": 30}

    def should_skip_republish_today(self, daily_publish_count: int) -> bool:
        """오늘 재발행을 보류해야 하는지 판단"""
        return daily_publish_count >= self.min_daily_publish_for_skip

    def __repr__(self) -> str:
        return f"<BlogPublishStrategy(blog_id={self.blog_id}, mode={self.strategy_mode})>"