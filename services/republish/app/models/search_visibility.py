"""검색 노출 원장 — 발행 URL 1건당 색인 관련 상태를 한 행에 모은다.

세 기능이 같은 행을 갱신한다.
    - S1 IndexNow: 발행 직후 제출 결과(응답코드까지)
    - S2 사이트맵 신선도: 사이트맵에 URL이 들어갔는지
    - S6 색인 점검: 검색엔진이 실제로 색인했는지(GSC URL Inspection)

근거: docs/plans/search_visibility_plan.md §4.1, docs/flowcharts/search_visibility.md
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..core.database import Base

# --- indexnow_status ---
IN_PENDING = "pending"
IN_OK = "ok"
IN_FAILED = "failed"
IN_SKIPPED = "skipped"

# --- sitemap_state ---
SM_UNKNOWN = "unknown"
SM_PRESENT = "present"
SM_MISSING = "missing"

# --- index_state ---
IX_UNKNOWN = "unknown"
IX_INDEXED = "indexed"
IX_NOT_INDEXED = "not_indexed"
IX_ERROR = "error"

# 사이트맵 연속 누락이 이 횟수를 넘으면 화면에 경고를 띄운다.
MISS_STREAK_WARN = 3


def utcnow() -> datetime:
    """timezone-aware 현재 시각.

    crawled_posts.published_at 이 aware 라서 여기도 aware 로 통일한다.
    naive 와 섞으면 asyncpg 가 INSERT 를 거부하고, 기간 비교도 어긋난다.
    """
    return datetime.now(timezone.utc)


class SearchVisibilityUrl(Base):
    """발행된 URL 1건의 검색 노출 상태."""

    __tablename__ = "search_visibility_urls"

    id = Column(Integer, primary_key=True)
    blog_id = Column(
        Integer, ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    crawled_post_id = Column(
        Integer, ForeignKey("crawled_posts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    url = Column(String(1000), nullable=False, comment="발행된 정식 URL")
    title = Column(String(500), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # --- S1 IndexNow ---
    indexnow_status = Column(
        String(20), default=IN_PENDING, nullable=False, index=True,
        comment="pending/ok/failed/skipped",
    )
    indexnow_status_code = Column(Integer, nullable=True, comment="HTTP 응답 코드")
    indexnow_error = Column(Text, nullable=True, comment="실패/스킵 사유")
    indexnow_attempts = Column(Integer, default=0, nullable=False)
    indexnow_submitted_at = Column(
        DateTime(timezone=True), nullable=True)

    # --- S2 사이트맵 ---
    sitemap_state = Column(
        String(20), default=SM_UNKNOWN, nullable=False, index=True,
        comment="unknown/present/missing",
    )
    sitemap_checked_at = Column(
        DateTime(timezone=True), nullable=True)
    sitemap_miss_streak = Column(
        Integer, default=0, nullable=False, comment="연속 누락 횟수",
    )

    # --- S6 색인 ---
    index_state = Column(
        String(20), default=IX_UNKNOWN, nullable=False, index=True,
        comment="unknown/indexed/not_indexed/error",
    )
    index_checked_at = Column(
        DateTime(timezone=True), nullable=True)
    index_detail = Column(
        JSONB, nullable=True,
        comment="coverageState·lastCrawlTime·verdict 등 원본 판정",
    )

    created_at = Column(
        DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False,
    )

    blog = relationship("Blog", backref="search_visibility_urls")

    __table_args__ = (
        UniqueConstraint("blog_id", "url", name="uq_svu_blog_url"),
        Index("ix_svu_blog_indexnow", "blog_id", "indexnow_status"),
        Index("ix_svu_blog_index_state", "blog_id", "index_state"),
        Index("ix_svu_blog_sitemap", "blog_id", "sitemap_state"),
    )

    def __repr__(self) -> str:
        return (
            f"<SearchVisibilityUrl(id={self.id}, blog_id={self.blog_id}, "
            f"index={self.index_state}, sitemap={self.sitemap_state})>"
        )
