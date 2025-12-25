"""
Google 계정 인증 정보 모델

Features:
- Google OAuth 토큰 암호화 저장
- 토큰 만료 관리
- 사용자별 Google 계정 연결
- 토큰 갱신 지원
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from ..core.database import Base
from ..core.encryption import encrypt_api_key, decrypt_api_key


class GoogleCredential(Base):
    """Google 계정 인증 정보 모델"""

    __tablename__ = "google_credentials"

    # 기본 정보
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Google 계정 정보
    google_email = Column(String(255), nullable=False, comment="Google 계정 이메일")

    # OAuth 토큰 (암호화 저장)
    access_token_encrypted = Column(String(500), nullable=False, comment="암호화된 액세스 토큰")
    refresh_token_encrypted = Column(String(500), nullable=True, comment="암호화된 리프레시 토큰")

    # 토큰 정보
    token_expiry = Column(DateTime(timezone=True), nullable=True, comment="토큰 만료 시간")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 제약 조건: 사용자당 동일한 Google 이메일은 하나만
    __table_args__ = (
        UniqueConstraint('user_id', 'google_email', name='uq_user_google_email'),
    )

    # 관계 설정
    user = relationship("User", back_populates="google_credentials")
    policy = relationship("GoogleAccountPolicy", back_populates="credential", uselist=False)
    blogs = relationship("Blog", back_populates="google_credential")
    blogger_slots = relationship("BloggerGlobalSlot", back_populates="google_credential")

    def __repr__(self) -> str:
        return f"<GoogleCredential(id={self.id}, user_id={self.user_id}, email={self.google_email})>"

    def __str__(self) -> str:
        return f"Google Account #{self.id} ({self.google_email})"

    @property
    def is_token_expired(self) -> bool:
        """토큰 만료 여부 확인"""
        if not self.token_expiry:
            return True
        return datetime.utcnow() > self.token_expiry

    @property
    def token_expires_in_minutes(self) -> Optional[int]:
        """토큰 만료까지 남은 분수"""
        if not self.token_expiry:
            return None
        delta = self.token_expiry - datetime.utcnow()
        return max(0, int(delta.total_seconds() / 60))

    @property
    def masked_access_token(self) -> str:
        """마스킹된 액세스 토큰 (로그용)"""
        if not self.access_token_encrypted:
            return "없음"
        token_len = len(str(self.access_token_encrypted))
        return "****" + str(self.access_token_encrypted)[-4:] if token_len > 4 else "****"

    def set_tokens(self, access_token: str, refresh_token: Optional[str] = None,
                   expires_in_seconds: Optional[int] = None) -> None:
        """토큰 설정 (암호화하여 저장)"""
        self.access_token_encrypted = encrypt_api_key(access_token)

        if refresh_token:
            self.refresh_token_encrypted = encrypt_api_key(refresh_token)

        if expires_in_seconds:
            self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

    def get_access_token(self) -> str:
        """액세스 토큰 복호화하여 반환"""
        return decrypt_api_key(self.access_token_encrypted)

    def get_refresh_token(self) -> Optional[str]:
        """리프레시 토큰 복호화하여 반환"""
        if not self.refresh_token_encrypted:
            return None
        return decrypt_api_key(self.refresh_token_encrypted)

    def needs_refresh(self, buffer_minutes: int = 5) -> bool:
        """토큰 갱신 필요 여부 (버퍼 시간 포함)"""
        if not self.token_expiry:
            return True
        buffer_time = datetime.utcnow() + timedelta(minutes=buffer_minutes)
        return buffer_time >= self.token_expiry

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (민감 정보 제외)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "google_email": self.google_email,
            "is_token_expired": self.is_token_expired,
            "token_expires_in_minutes": self.token_expires_in_minutes,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }