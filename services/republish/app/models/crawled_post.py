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
from sqlalchemy import Integer, String, Float, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from ..core.database import Base

if TYPE_CHECKING:
    from .blog import Blog
    from .title import MainTitle

# 최대 발행 재시도 횟수
MAX_PUBLISH_ATTEMPTS: int = 3


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

    # 이미지
    image_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="생성된 이미지 URL",
    )

    # 생성된 콘텐츠
    content_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="생성된 HTML 본문",
    )

    # 플랫폼 발행 ID (WordPress post ID, Blogger post ID)
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="플랫폼 발행 후 반환된 포스트 ID",
    )

    # 마지막 리뉴얼 시각 (재발행 리뉴얼 주기 판단 기준, P1)
    last_renewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 리뉴얼(재생성 갱신) 시각. NULL이면 미리뉴얼",
    )

    # 저장 정리 시각 (유예 경과 후 본문/이미지 삭제, P4)
    purged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="본문/이미지 정리 시각. NULL이면 미정리(메타는 항상 보존)",
    )

    # SEO 메타데이터
    seo_meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="SEO 메타: focus_keyphrase, slug, meta_description, generated_by",
    )

    # 소스 정보
    source: Mapped[str] = mapped_column(
        String(20),
        default="crawled",
        comment="소스: crawled(크롤링) | generated(자동생성) | published(발행)",
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

    # 발행 재시도 추적
    publish_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="발행 시도 횟수"
    )
    last_publish_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="마지막 발행 에러 메시지"
    )
    last_publish_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 발행 시도 시각"
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
        Index('ix_crawled_post_blog_source_published',
              'blog_id', 'source', 'published_at'),
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

    @property
    def is_generated(self) -> bool:
        """자동 생성된 포스트 여부"""
        return self.source == "generated"

    @property
    def is_published(self) -> bool:
        """발행 완료 여부 (published_at이 설정됨)"""
        return self.published_at is not None

    @property
    def is_publish_exhausted(self) -> bool:
        """최대 발행 시도 횟수 초과 여부"""
        return self.publish_attempts >= MAX_PUBLISH_ATTEMPTS

    @property
    def is_publishable(self) -> bool:
        """발행 가능 여부 (생성됨 + 미발행 + 시도 횟수 미초과)"""
        return self.is_generated and not self.is_published and not self.is_publish_exhausted

    def record_publish_failure(self, error: str) -> None:
        """
        발행 실패 기록

        시도 횟수를 증가시키고, 마지막 에러와 시도 시각을 저장합니다.

        Args:
            error: 에러 메시지 (500자까지 저장)
        """
        self.publish_attempts += 1
        self.last_publish_error = error[:500] if error else None
        self.last_publish_attempted_at = datetime.now()
        self.updated_at = datetime.now()

    def mark_published(
        self,
        published_url: Optional[str] = None,
        platform_post_id: Optional[str] = None,
    ) -> None:
        """
        발행 완료 처리

        Args:
            published_url: 발행된 URL (선택)
            platform_post_id: 플랫폼 포스트 ID (선택)
        """
        self.published_at = datetime.now()
        if published_url:
            self.url = published_url
        if platform_post_id:
            self.platform_post_id = platform_post_id
        self.updated_at = datetime.now()
