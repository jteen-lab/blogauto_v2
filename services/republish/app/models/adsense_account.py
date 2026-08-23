"""애드센스 계정·사이트 상태 모델 (다중 계정 지원).

블로그의 승인 여부는 blogauto 내부 설정이 아니라 **애드센스 사이트 목록의 실제
상태**를 1차 기준으로 판정한다. 계정이 여러 개일 수 있으므로 계정별로 토큰을
보관하고, 동기화한 사이트 목록을 캐시해 둔다.

계획서: docs/plans/adsense_status_automation_plan.md
"""
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class AdsenseAccount(Base):
    """애드센스 계정(다중 등록 가능)."""
    __tablename__ = "adsense_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    label = Column(String(100), nullable=False, comment="계정 별칭(사용자 구분용)")
    google_email = Column(String(255), nullable=True, comment="계정 이메일(참고용)")

    # 인증
    refresh_token_encrypted = Column(Text, nullable=False, comment="암호화된 refresh token")

    # 최초 조회 시 확인되는 애드센스 계정 리소스명 (accounts/pub-XXXXXXXX)
    account_resource = Column(String(120), nullable=True, comment="accounts/pub-...")

    is_active = Column(Boolean, default=True, nullable=False)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    sites = relationship(
        "AdsenseSite", back_populates="account", cascade="all, delete-orphan"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "google_email": self.google_email,
            "account_resource": self.account_resource,
            "is_active": self.is_active,
            "last_synced_at": (
                self.last_synced_at.isoformat() if self.last_synced_at else None
            ),
            "last_sync_error": self.last_sync_error,
            "site_count": len(self.sites) if self.sites is not None else 0,
        }


class AdsenseSite(Base):
    """애드센스 계정에 등록된 사이트와 그 상태(동기화 캐시).

    state 원문(READY/GETTING_READY/REQUIRES_REVIEW/NEEDS_ATTENTION)을 그대로
    보관한다. 표시용 분류는 조회 시점에 계산한다 — 규칙이 바뀌어도 재동기화가
    필요 없게 하기 위함.
    """
    __tablename__ = "adsense_sites"
    __table_args__ = (
        UniqueConstraint("account_id", "domain", name="uq_adsense_site_domain"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(
        Integer, ForeignKey("adsense_accounts.id"), nullable=False, index=True
    )

    domain = Column(String(255), nullable=False, index=True, comment="사이트 도메인")
    state = Column(String(40), nullable=True, comment="애드센스 원문 state")
    site_resource = Column(String(200), nullable=True, comment="accounts/*/sites/*")

    synced_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("AdsenseAccount", back_populates="sites")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "domain": self.domain,
            "state": self.state,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }
