"""페이지별 일일 유입 — 블로그의 **모든** 방문 페이지, 유입 경로별.

`PostMetricDaily` 는 블로그오토가 발행한 글만 담는다(재발행 판정용). 그래서
블로그오토 이전에 쓴 옛 글과 첫 화면의 방문이 통째로 빠졌다 — 인생꿀팁 방문의
9할이 바로 그 옛 글이다. 여기는 경로(path) 단위로 전부 적는다.

    sessions                    전체 방문
    naver/google/direct/other   유입 경로별 방문(합 = sessions)

순서도: docs/flowcharts/analytics_sources.md
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..core.database import Base


class PageMetricDaily(Base):
    """블로그 한 페이지의 하루치 유입."""

    __tablename__ = "page_metrics_daily"
    __table_args__ = (
        UniqueConstraint("blog_id", "path", "date",
                         name="uq_page_metric_blog_path_date"),
        Index("ix_page_metric_blog_date", "blog_id", "date"),
    )

    id = Column(Integer, primary_key=True)
    blog_id = Column(
        Integer, ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    date = Column(Date, nullable=False, comment="지표가 발생한 날")
    path = Column(String(1000), nullable=False, comment="방문 페이지 경로(소문자)")
    crawled_post_id = Column(
        Integer, ForeignKey("crawled_posts.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="주소가 맞는 글(옛 글 포함)",
    )
    is_autopost = Column(Boolean, nullable=False, default=False,
                         comment="블로그오토 발행 글인가")

    sessions = Column(Integer, nullable=False, default=0)
    engaged_sessions = Column(Integer, nullable=False, default=0)
    avg_duration = Column(Float, nullable=False, default=0.0,
                          comment="평균 세션 시간(초, 세션 가중)")
    naver_sessions = Column(Integer, nullable=False, default=0)
    google_sessions = Column(Integer, nullable=False, default=0)
    direct_sessions = Column(Integer, nullable=False, default=0)
    other_sessions = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return (f"<PageMetricDaily(blog={self.blog_id}, {self.date}, "
                f"{self.path}, sessions={self.sessions})>")
