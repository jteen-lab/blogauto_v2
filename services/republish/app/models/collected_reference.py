"""
참조자료 수집 모델 정의

자료 수집 모듈을 위한 데이터베이스 모델입니다.
검색 → 크롤링 → 요약의 참조자료 수집 워크플로우를 지원합니다.

테이블:
- CollectedReference: 참조자료 수집 결과 (검색어별 수집 세션)
- CrawlLog: 개별 URL 크롤링 상세 로그

Features:
- 검색어 기반 참조자료 수집
- 크롤링 성공/실패 추적
- 선택된 참조자료 JSONB 저장
- MainTitle과의 선택적 연결
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Integer, String, Text, DateTime, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..core.database import Base

if TYPE_CHECKING:
    from .title import MainTitle


class CollectedReference(Base):
    """
    참조자료 수집 결과

    검색어별 수집 세션을 관리합니다.
    상태: pending(대기) | collecting(수집중) | completed(완료) | failed(실패)
    """
    __tablename__ = "collected_references"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # 제목 연결 (선택적 - 직접 검색도 가능)
    title_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("main_titles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="연결된 메인 타이틀 ID"
    )

    # 검색 정보
    search_query: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="검색어"
    )

    # 수집 통계
    total_searched: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="검색 결과 수"
    )
    total_crawled: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="크롤링 성공 수"
    )
    total_failed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="크롤링 실패 수"
    )

    # 선택된 참조자료 (JSONB)
    # 형식: [{"url": str, "title": str, "summary": str, "selected_at": str}, ...]
    selected_references: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="선택된 참조자료 JSON"
    )

    # 상태 관리
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        comment="상태: pending | collecting | completed | failed"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="실패 시 에러 메시지"
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="생성 시간"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="완료 시간"
    )

    # 관계
    title: Mapped[Optional["MainTitle"]] = relationship(
        "MainTitle",
        lazy="selectin"
    )
    crawl_logs: Mapped[List["CrawlLog"]] = relationship(
        "CrawlLog",
        back_populates="reference",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    __table_args__ = (
        Index('ix_collected_ref_status_created', 'status', 'created_at'),
        Index('ix_collected_ref_title_status', 'title_id', 'status'),
    )

    def __repr__(self) -> str:
        return f"<CollectedReference(id={self.id}, query='{self.search_query[:30]}...', status={self.status})>"

    def mark_collecting(self) -> None:
        """수집 시작 상태로 변경"""
        self.status = "collecting"

    def mark_completed(self, selected_refs: Optional[List[dict]] = None) -> None:
        """수집 완료 처리"""
        self.status = "completed"
        self.completed_at = datetime.now()
        if selected_refs:
            self.selected_references = selected_refs

    def mark_failed(self, error_message: str) -> None:
        """수집 실패 처리"""
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = datetime.now()

    def update_stats(self, searched: int = 0, crawled: int = 0, failed: int = 0) -> None:
        """통계 업데이트"""
        self.total_searched = searched
        self.total_crawled = crawled
        self.total_failed = failed

    @property
    def is_completed(self) -> bool:
        """완료 여부"""
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        """실패 여부"""
        return self.status == "failed"

    @property
    def selected_count(self) -> int:
        """선택된 참조자료 수"""
        if self.selected_references:
            return len(self.selected_references)
        return 0


class CrawlLog(Base):
    """
    크롤링 상세 로그

    개별 URL의 크롤링 결과를 기록합니다.
    상태: success(성공) | failed(실패) | timeout(타임아웃) | blocked(차단) | skipped(스킵)
    """
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    # 참조자료 연결
    reference_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("collected_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="참조자료 수집 ID"
    )

    # URL 정보
    url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="크롤링 URL"
    )
    domain: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="도메인"
    )

    # 크롤링 결과
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="상태: success | failed | timeout | blocked | skipped"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="에러 메시지"
    )

    # 콘텐츠 정보
    content_length: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="크롤링된 콘텐츠 길이"
    )
    crawl_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="크롤링 소요 시간(ms)"
    )

    # 타임스탬프
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="크롤링 시간"
    )

    # 관계
    reference: Mapped["CollectedReference"] = relationship(
        "CollectedReference",
        back_populates="crawl_logs"
    )

    __table_args__ = (
        Index('ix_crawl_log_ref_status', 'reference_id', 'status'),
        Index('ix_crawl_log_domain', 'domain'),
    )

    def __repr__(self) -> str:
        return f"<CrawlLog(id={self.id}, url='{self.url[:50]}...', status={self.status})>"

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.status == "success"

    @classmethod
    def create_success(
        cls,
        reference_id: int,
        url: str,
        domain: str,
        content_length: int,
        duration_ms: int
    ) -> "CrawlLog":
        """성공 로그 생성"""
        return cls(
            reference_id=reference_id,
            url=url,
            domain=domain,
            status="success",
            content_length=content_length,
            crawl_duration_ms=duration_ms
        )

    @classmethod
    def create_failed(
        cls,
        reference_id: int,
        url: str,
        domain: str,
        status: str,
        error_message: str
    ) -> "CrawlLog":
        """실패 로그 생성"""
        return cls(
            reference_id=reference_id,
            url=url,
            domain=domain,
            status=status,
            error_message=error_message
        )
