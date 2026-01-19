"""
수집된 URL 모델 정의

대량 수집 시 검색 결과에서 추출한 블로그/사이트 URL을 저장합니다.
수집 주기마다 URL을 축적하고, 별도 주기에 제목을 수집합니다.

수집 흐름:
1. 키워드 검색 → URL 수집 및 저장 (CollectedUrl)
2. 수집 주기마다 URL 1~3개씩 꺼내서 제목 수집
3. 제목 수집 완료된 URL은 is_processed=True로 표시
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


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

    # 유니크 제약조건: 같은 도메인은 중복 저장 방지
    __table_args__ = (
        UniqueConstraint('domain', name='uq_collected_url_domain'),
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
