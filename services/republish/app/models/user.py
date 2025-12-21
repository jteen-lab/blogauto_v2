"""
사용자 모델 정의

Features:
- SQLAlchemy ORM 모델
- 이메일 기반 인증
- 사용자 등급 관리
- 타임스탬프 자동 관리
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from typing import Optional

from ..core.database import Base

class UserTier(str, Enum):
    """사용자 등급"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class User(Base):
    """사용자 모델"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # 사용자 정보
    full_name = Column(String(100), nullable=True)
    tier = Column(SQLEnum(UserTier), default=UserTier.FREE, nullable=False)

    # 계정 상태
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # 관계 설정
    blogs = relationship("Blog", back_populates="user", lazy="dynamic")
    topics = relationship("Topic", back_populates="user", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, tier={self.tier.value})>"

    def __str__(self) -> str:
        return f"User #{self.id} ({self.email})"

    @property
    def is_free_user(self) -> bool:
        """무료 사용자 여부"""
        return self.tier == UserTier.FREE

    @property
    def is_pro_user(self) -> bool:
        """프로 사용자 여부"""
        return self.tier == UserTier.PRO

    @property
    def is_enterprise_user(self) -> bool:
        """엔터프라이즈 사용자 여부"""
        return self.tier == UserTier.ENTERPRISE

    @property
    def display_name(self) -> str:
        """표시 이름"""
        return self.full_name if self.full_name else self.email.split("@")[0]

    def update_last_login(self) -> None:
        """마지막 로그인 시간 업데이트"""
        self.last_login_at = datetime.utcnow()

    def activate(self) -> None:
        """계정 활성화"""
        self.is_active = True

    def deactivate(self) -> None:
        """계정 비활성화"""
        self.is_active = False

    def verify(self) -> None:
        """이메일 인증"""
        self.is_verified = True

    def upgrade_tier(self, new_tier: UserTier) -> None:
        """등급 업그레이드"""
        tier_order = {UserTier.FREE: 0, UserTier.PRO: 1, UserTier.ENTERPRISE: 2}

        if tier_order[new_tier] > tier_order[self.tier]:
            self.tier = new_tier

    def downgrade_tier(self, new_tier: UserTier) -> None:
        """등급 다운그레이드"""
        tier_order = {UserTier.FREE: 0, UserTier.PRO: 1, UserTier.ENTERPRISE: 2}

        if tier_order[new_tier] < tier_order[self.tier]:
            self.tier = new_tier

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (비밀번호 제외)"""
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "tier": self.tier.value,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "is_superuser": self.is_superuser,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
            "display_name": self.display_name
        }