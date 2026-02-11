"""
도메인 블랙리스트 모델

크롤링 시 본문 추출에 반복 실패하는 도메인을 자동으로 등록하여
다음 참조자료 수집 시 해당 도메인을 건너뛸 수 있도록 합니다.

Features:
- 크롤링 실패 도메인 자동 등록/카운트 증가
- FAIL_THRESHOLD(3회) 이상 실패 시 자동 차단
- 사용자가 수동으로 해제(is_active=False) 가능
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Boolean, DateTime, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class DomainBlacklist(Base):
    """
    크롤링 실패 도메인 블랙리스트

    특정 도메인에서 반복적으로 본문 추출에 실패하면
    자동으로 등록되어 이후 크롤링 대상에서 제외됩니다.
    """
    __tablename__ = "domain_blacklist"

    # 실패 임계값: 이 횟수 이상 실패하면 블랙리스트 활성
    FAIL_THRESHOLD = 3

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    domain: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="블랙리스트 도메인"
    )

    fail_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="누적 실패 횟수"
    )

    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="마지막 실패 시간"
    )

    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="content_extraction_failed",
        comment="차단 사유: content_extraction_failed | blocked | timeout"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="블랙리스트 활성 여부 (False: 사용자 해제)"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="최초 등록 시간"
    )

    __table_args__ = (
        Index('ix_domain_blacklist_active', 'is_active', 'fail_count'),
    )

    def __repr__(self) -> str:
        return (
            f"<DomainBlacklist(domain='{self.domain}', "
            f"fail_count={self.fail_count}, active={self.is_active})>"
        )

    @property
    def is_blocked(self) -> bool:
        """임계값 이상 실패하고 활성 상태인지 확인"""
        return self.is_active and self.fail_count >= self.FAIL_THRESHOLD

    def increment_fail(self, reason: str = "content_extraction_failed") -> None:
        """실패 카운트 증가"""
        self.fail_count += 1
        self.last_failed_at = datetime.now()
        self.reason = reason

    def deactivate(self) -> None:
        """사용자가 수동으로 블랙리스트 해제"""
        self.is_active = False

    def reactivate(self) -> None:
        """블랙리스트 재활성화"""
        self.is_active = True
