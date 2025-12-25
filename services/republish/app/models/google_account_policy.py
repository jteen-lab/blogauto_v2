"""
Google 계정별 발행 정책 모델

Features:
- Google 계정별 발행 제한 설정
- 시간대별 발행 허용 시간 관리
- 안전 모드 및 간격 제한
- 계정별 정책 커스터마이징
"""
from sqlalchemy import Column, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Any

from ..core.database import Base


class GoogleAccountPolicy(Base):
    """Google 계정별 발행 정책 모델"""

    __tablename__ = "google_account_policies"

    # 기본 정보
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    google_credential_id = Column(
        Integer,
        ForeignKey("google_credentials.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Google 계정 ID (1:1 관계)"
    )

    # 발행 간격 제한
    min_interval_minutes = Column(
        Integer,
        default=30,
        nullable=False,
        comment="최소 발행 간격 (분)"
    )

    # 일일 제한
    max_daily_per_blog = Column(
        Integer,
        default=5,
        nullable=False,
        comment="블로그당 일일 최대 발행 수"
    )
    max_daily_total = Column(
        Integer,
        default=50,
        nullable=False,
        comment="계정 전체 일일 최대 발행 수"
    )

    # 허용 시간대
    allowed_hours_start = Column(
        Integer,
        default=9,
        nullable=False,
        comment="발행 허용 시작 시간 (24시간 형식)"
    )
    allowed_hours_end = Column(
        Integer,
        default=22,
        nullable=False,
        comment="발행 허용 종료 시간 (24시간 형식)"
    )

    # 안전 모드
    safety_mode = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="안전 모드 (더 엄격한 제한)"
    )

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계 설정
    credential = relationship("GoogleCredential", back_populates="policy")

    def __repr__(self) -> str:
        return f"<GoogleAccountPolicy(id={self.id}, credential_id={self.google_credential_id})>"

    def __str__(self) -> str:
        return f"Policy #{self.id} for Credential #{self.google_credential_id}"

    @property
    def is_conservative_policy(self) -> bool:
        """보수적 정책 여부 (안전한 설정)"""
        return (
            self.min_interval_minutes >= 60 and
            self.max_daily_per_blog <= 3 and
            self.max_daily_total <= 30 and
            self.safety_mode
        )

    @property
    def slots_per_hour(self) -> int:
        """시간당 최대 슬롯 수"""
        return max(1, 60 // self.min_interval_minutes)

    @property
    def allowed_hours_range(self) -> tuple:
        """허용 시간 범위 반환"""
        return (self.allowed_hours_start, self.allowed_hours_end)

    @property
    def working_hours_count(self) -> int:
        """일일 작업 시간 수"""
        if self.allowed_hours_end >= self.allowed_hours_start:
            return self.allowed_hours_end - self.allowed_hours_start + 1
        else:
            # 자정을 넘는 경우 (예: 22시~9시)
            return (24 - self.allowed_hours_start) + (self.allowed_hours_end + 1)

    def is_hour_allowed(self, hour: int) -> bool:
        """특정 시간이 허용되는지 확인"""
        if self.allowed_hours_end >= self.allowed_hours_start:
            return self.allowed_hours_start <= hour <= self.allowed_hours_end
        else:
            # 자정을 넘는 경우
            return hour >= self.allowed_hours_start or hour <= self.allowed_hours_end

    def apply_safety_restrictions(self) -> None:
        """안전 모드 제한 적용"""
        if self.safety_mode:
            self.min_interval_minutes = max(self.min_interval_minutes, 45)
            self.max_daily_per_blog = min(self.max_daily_per_blog, 3)
            self.max_daily_total = min(self.max_daily_total, 30)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "google_credential_id": self.google_credential_id,
            "min_interval_minutes": self.min_interval_minutes,
            "max_daily_per_blog": self.max_daily_per_blog,
            "max_daily_total": self.max_daily_total,
            "allowed_hours_start": self.allowed_hours_start,
            "allowed_hours_end": self.allowed_hours_end,
            "safety_mode": self.safety_mode,
            "slots_per_hour": self.slots_per_hour,
            "working_hours_count": self.working_hours_count,
            "is_conservative_policy": self.is_conservative_policy,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def create_default_policy(cls, credential_id: int, safety_mode: bool = True) -> "GoogleAccountPolicy":
        """기본 정책 생성"""
        policy = cls(
            google_credential_id=credential_id,
            min_interval_minutes=30 if not safety_mode else 60,
            max_daily_per_blog=5 if not safety_mode else 3,
            max_daily_total=50 if not safety_mode else 20,
            allowed_hours_start=9,
            allowed_hours_end=22,
            safety_mode=safety_mode
        )

        if safety_mode:
            policy.apply_safety_restrictions()

        return policy