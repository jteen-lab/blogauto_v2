"""
수집된 URL 모델 정의

대량 수집 시 검색 결과에서 추출한 블로그/사이트 URL을 저장합니다.
수집 주기마다 URL을 축적하고, 별도 주기에 제목을 수집합니다.

수집 흐름:
1. 키워드 검색 → URL 수집 및 저장 (CollectedUrl)
2. 수집 주기마다 URL 1~3개씩 꺼내서 제목 수집
3. 제목 수집 완료된 URL은 is_processed=True로 표시

Phase A-041 추가 컬럼 (대량 수집 모듈 분리):
- title: 수집된 포스트 제목 (Phase 2 에서 sitemap → 본문 메타에서 추출)
- title_fetched_at: 제목 수집(또는 마지막 시도) 시각
- title_fetch_status: 제목 수집 상태 (pending|done|failed)

Phase B-042 추가 컬럼 (모듈별 URL 격리):
- source_module_id: 적재한 모듈 ID (nullable, ON DELETE SET NULL)
  레거시(`keyword_collector_service`) 적재 row 는 NULL.
  bulk_collect 모듈이 적재한 row 는 module_id 가 채워진다.
  UNIQUE: (url, source_module_id) → 같은 URL이라도 모듈이 다르면 독립 row.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Boolean, DateTime,
    Text, UniqueConstraint, ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

logger = logging.getLogger(__name__)


class CollectedUrl(Base):
    """
    수집된 URL (블로그/사이트)

    대량 수집 시 키워드 검색 결과에서 추출한 URL을 저장합니다.
    제목 수집은 별도 주기에 1~3개씩 처리합니다.
    """
    __tablename__ = "collected_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # URL 정보
    url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
        comment="블로그/사이트 URL"
    )
    domain: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="도메인 (예: example.tistory.com)"
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unknown",
        comment="플랫폼 (naver|tistory|wordpress|blogger|unknown)"
    )

    # 검색 정보
    search_keyword: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="검색에 사용된 키워드"
    )
    search_title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="검색 결과 제목"
    )

    # 처리 상태
    is_processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        comment="제목 수집 완료 여부"
    )
    process_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="처리 횟수"
    )
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 제목 수집 시각"
    )
    titles_collected: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="수집된 제목 수"
    )

    # 상태 관리
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        comment="활성 상태 (False면 수집 대상에서 제외)"
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="수집 실패 횟수 (3회 이상 실패 시 비활성화)"
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="마지막 에러 메시지"
    )

    # Phase A-041: 제목 수집 결과
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="수집된 포스트 제목 (Phase 2에서 추출)"
    )
    title_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="제목 수집(또는 마지막 시도) 시각"
    )
    title_fetch_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        default="pending",
        comment="제목 수집 상태 (pending|done|failed)"
    )

    # Phase B-042: 모듈별 URL 격리 (bulk_collect 모듈 다수 운영 대비)
    # - NULL 인 row 는 레거시(keyword_collector_service) 또는 collect 모듈 적재.
    # - bulk_collect 모듈이 적재한 row 는 module.id 값을 가진다.
    # - 모듈 삭제 시 SET NULL (URL 자체는 보존, 레거시 풀로 회수).
    source_module_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("modules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="URL을 적재한 모듈 ID (NULL=레거시/일반 collect 모듈)"
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="최초 수집 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 유니크 제약조건 (Phase B-042 변경):
    # - 기존 (domain) UNIQUE 제거 — 한 도메인 다수 URL 허용
    # - 신규 (url, source_module_id) UNIQUE — URL 단위 모듈별 격리
    #   * NULL(레거시) 끼리는 NULLS DISTINCT(기본) 이므로 url 중복 가능 → 의도된 동작
    #   * 모듈이 명시된 경우엔 같은 URL을 모듈별로 분리해서 적재 가능
    # - 도메인은 일반 인덱스(ix_collected_urls_domain) 로 유지 (위 domain 컬럼 정의에 index=True)
    __table_args__ = (
        UniqueConstraint(
            'url', 'source_module_id',
            name='uq_collected_url_url_module',
        ),
        Index(
            'ix_collected_urls_source_module_status',
            'source_module_id', 'title_fetch_status',
        ),
    )

    def __repr__(self) -> str:
        return f"<CollectedUrl(id={self.id}, domain='{self.domain}', platform='{self.platform}')>"

    def mark_processed(self, titles_count: int = 0) -> None:
        """제목 수집 완료 표시"""
        self.is_processed = True
        self.process_count += 1
        self.last_processed_at = datetime.now()
        self.titles_collected += titles_count
        self.error_count = 0  # 성공 시 에러 카운트 초기화

    def mark_error(self, error_message: str) -> None:
        """에러 기록"""
        self.error_count += 1
        self.last_error = error_message
        self.last_processed_at = datetime.now()

        # 3회 이상 실패 시 비활성화
        if self.error_count >= 3:
            self.is_active = False

    def reset_for_recollect(self) -> None:
        """재수집을 위한 상태 초기화"""
        self.is_processed = False
        self.error_count = 0
        self.last_error = None

    def mark_title_fetched(self, title: str) -> None:
        """
        제목 수집 성공 표시

        Args:
            title: 추출된 포스트 제목 (최대 500자, 길면 잘림)
        """
        # 안전을 위해 500자 컷
        safe_title = (title or "").strip()[:500]
        self.title = safe_title or None
        self.title_fetched_at = datetime.now()
        self.title_fetch_status = "done"
        logger.debug(
            "title fetched id=%s domain=%s len=%d",
            self.id, self.domain, len(safe_title),
        )

    def mark_title_failed(self, error: Optional[str] = None) -> None:
        """
        제목 수집 실패 표시

        title 자체는 비우지 않고 (이전 값 보존), 상태와 시각만 갱신.
        error 가 주어지면 last_error 에도 기록하고 error_count 를 1 증가시킨다.

        Args:
            error: 실패 사유 (선택, 길면 잘림)
        """
        self.title_fetch_status = "failed"
        self.title_fetched_at = datetime.now()
        if error:
            self.last_error = error[:1000]
            self.error_count = (self.error_count or 0) + 1
        logger.warning(
            "title fetch failed id=%s domain=%s error=%s",
            self.id, self.domain, (error or "")[:120],
        )
