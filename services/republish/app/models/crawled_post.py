"""
크롤링 포스트 모델

블로그에서 크롤링한 기존 포스트 정보를 저장하고
메인 타이틀과의 유사도 매칭 결과를 관리합니다.

Features:
- 블로그별 크롤링 포스트 저장
- MainTitle과의 유사도 매칭 (matched/unmatched 2단계)
- 발행 시 자동 CrawledPost 생성
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from ..core.database import Base

if TYPE_CHECKING:
    from .blog import Blog
    from .title import MainTitle


class CrawledPost(Base):
    """
    크롤링 포스트 모델

    블로그에서 크롤링한 포스트 또는 발행 후 생성된 포스트 기록
    매칭 상태: pending(대기) | matched(매칭됨) | unmatched(미매칭)
    """
    __tablename__ = "crawled_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 블로그 연결
    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="블로그 ID"
    )

    # 포스트 정보
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="포스트 제목"
    )
    url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="포스트 URL"
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="발행 일시"
    )

    # 매칭 정보 (2단계: matched/unmatched)
    match_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        comment="매칭 상태: pending | matched | unmatched"
    )
    matched_main_title_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("main_titles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="매칭된 메인 타이틀 ID"
    )
    match_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="유사도 점수 (0.0 ~ 100.0)"
    )

    # 생성 이력 연결 (nullable - 수동 추가 글은 null)
    generation_history_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("generation_histories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="생성 이력 FK (자동 생성된 글만)",
    )

    # 소스 정보
    source: Mapped[str] = mapped_column(
        String(20),
        default="crawled",
        comment="소스: crawled(크롤링) | published(발행)",
    )

    # 타임스탬프
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="크롤링 일시"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 관계
    blog: Mapped["Blog"] = relationship("Blog", back_populates="crawled_posts")
    matched_main_title: Mapped[Optional["MainTitle"]] = relationship(
        "MainTitle",
        back_populates="matched_crawled_posts"
    )

    __table_args__ = (
        Index('ix_crawled_post_blog_status', 'blog_id', 'match_status'),
        Index('ix_crawled_post_blog_title', 'blog_id', 'title'),
    )

    def __repr__(self) -> str:
        return f"<CrawledPost(id={self.id}, title='{self.title[:30]}...', status={self.match_status})>"

    def mark_matched(self, main_title_id: int, score: float) -> None:
        """매칭 처리"""
        self.match_status = "matched"
        self.matched_main_title_id = main_title_id
        self.match_score = score
        self.updated_at = datetime.now()

    def mark_unmatched(self, score: Optional[float] = None) -> None:
        """미매칭 처리"""
        self.match_status = "unmatched"
        self.matched_main_title_id = None
        self.match_score = score
        self.updated_at = datetime.now()

    @property
    def is_matched(self) -> bool:
        """매칭 여부"""
        return self.match_status == "matched"

    @property
    def is_from_publish(self) -> bool:
        """발행으로 생성된 포스트 여부"""
        return self.source == "published"
