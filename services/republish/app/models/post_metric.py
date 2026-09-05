"""글별 일일 성과 — 발행한 뒤 실제로 무슨 일이 일어났나.

`SearchVisibilityUrl` 이 URL 단위 발행 이력을 이미 갖고 있다. 거기에
**시계열만** 매단다. 스냅숏(현재값)만 두면 "줄고 있는 중" 을 알 수 없고,
재발행 판정은 추세로 한다.

    GA4   sessions · engaged_sessions · avg_duration   들어와서 무엇을 했나
    GSC   clicks · impressions · position              검색에 몇 번 보였나

둘을 함께 본다. 노출은 유지되는데 세션이 빠지면 제목·설명 문제고,
노출부터 빠지면 순위 문제다. 하나만 보면 구분이 안 된다.

계획서: docs/plans/analytics_integration_plan.md §4
"""
from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Index, Integer,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..core.database import Base


class PostMetricDaily(Base):
    """글 하나의 하루치 성과."""

    __tablename__ = "post_metrics_daily"
    __table_args__ = (
        # 같은 날 두 번 수집해도 행이 겹치지 않게 한다
        UniqueConstraint("url_id", "date", name="uq_post_metric_url_date"),
        Index("ix_post_metric_date", "date"),
        Index("ix_post_metric_blog_date", "blog_id", "date"),
    )

    id = Column(Integer, primary_key=True)
    url_id = Column(
        Integer, ForeignKey("search_visibility_urls.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="발행 URL 행",
    )
    # 블로그별 집계를 URL 조인 없이 하려고 함께 둔다
    blog_id = Column(
        Integer, ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date = Column(Date, nullable=False, comment="지표가 발생한 날(수집일 아님)")

    # GA4
    sessions = Column(Integer, nullable=False, default=0)
    engaged_sessions = Column(Integer, nullable=False, default=0)
    avg_duration = Column(Float, nullable=False, default=0.0,
                          comment="평균 세션 시간(초)")

    # Search Console
    clicks = Column(Integer, nullable=False, default=0)
    impressions = Column(Integer, nullable=False, default=0)
    position = Column(Float, nullable=False, default=0.0,
                      comment="평균 순위. 0 은 노출 없음")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<PostMetricDaily(url={self.url_id}, date={self.date}, "
                f"sessions={self.sessions}, impr={self.impressions})>")
