"""
AI API 키 다계정 관리 모델

Features:
- 여러 AI 서비스(OpenAI, Claude, Gemini) API 키 관리
- 우선순위 기반 키 선택
- 사용량 제한 시 자동 키 전환
- 사용 통계 및 오류 추적
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from sqlalchemy.sql import func
from typing import Optional

from ..core.database import Base


class AIApiKey(Base):
    """AI API 키 다계정 관리 모델"""

    __tablename__ = "ai_api_keys"
    __table_args__ = (
        Index('ix_ai_api_keys_user_provider', 'user_id', 'provider'),
        Index('ix_ai_api_keys_priority', 'user_id', 'provider', 'priority'),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 사용자 ID (단일 사용자 환경에서 기본값 1)
    user_id = Column(Integer, default=1, nullable=False, index=True)

    # AI 서비스 제공자 (openai, anthropic, google)
    provider = Column(String(50), nullable=False, index=True)

    # 사용자 정의 라벨 (예: "개인 계정", "회사 계정")
    label = Column(String(100), nullable=False)

    # API 키 (암호화 저장 권장)
    api_key = Column(String(512), nullable=False)

    # 우선순위 (낮을수록 먼저 사용, 0이 최우선)
    priority = Column(Integer, default=0, nullable=False)

    # 활성화 상태
    is_active = Column(Boolean, default=True, nullable=False)

    # 사용 통계
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)

    # 오류 추적
    error_count = Column(Integer, default=0, nullable=False)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error_message = Column(Text, nullable=True)

    # 키 상태 (active, rate_limited, error, disabled)
    status = Column(String(20), default='active', nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 제공자 상수
    PROVIDER_OPENAI = "openai"
    PROVIDER_ANTHROPIC = "anthropic"
    PROVIDER_GOOGLE = "google"
    PROVIDER_NANOBANANA = "nanobanana"

    VALID_PROVIDERS = [
        PROVIDER_OPENAI,
        PROVIDER_ANTHROPIC,
        PROVIDER_GOOGLE,
        PROVIDER_NANOBANANA,
    ]

    # 상태 상수
    STATUS_ACTIVE = "active"
    STATUS_RATE_LIMITED = "rate_limited"
    STATUS_ERROR = "error"
    STATUS_DISABLED = "disabled"

    VALID_STATUSES = [STATUS_ACTIVE, STATUS_RATE_LIMITED, STATUS_ERROR, STATUS_DISABLED]

    def __repr__(self) -> str:
        return f"<AIApiKey(id={self.id}, provider={self.provider}, label={self.label})>"

    @property
    def masked_api_key(self) -> str:
        """마스킹된 API 키 (앞 4자 + **** + 뒤 4자)"""
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}****{self.api_key[-4:]}"

    @property
    def provider_display_name(self) -> str:
        """제공자 표시 이름"""
        names = {
            self.PROVIDER_OPENAI: "OpenAI",
            self.PROVIDER_ANTHROPIC: "Claude (Anthropic)",
            self.PROVIDER_GOOGLE: "Gemini (Google)",
            self.PROVIDER_NANOBANANA: "Nano Banana",
        }
        return names.get(self.provider, self.provider)

    @property
    def is_available(self) -> bool:
        """키가 사용 가능한 상태인지 확인"""
        return self.is_active and self.status == self.STATUS_ACTIVE

    def mark_as_used(self) -> None:
        """키 사용 기록"""
        self.last_used_at = func.now()
        self.usage_count += 1

    def mark_rate_limited(self) -> None:
        """사용량 제한 상태로 표시"""
        self.status = self.STATUS_RATE_LIMITED
        self.error_count += 1
        self.last_error_at = func.now()
        self.last_error_message = "Rate limit exceeded"

    def mark_error(self, error_message: str) -> None:
        """오류 상태로 표시"""
        self.status = self.STATUS_ERROR
        self.error_count += 1
        self.last_error_at = func.now()
        self.last_error_message = error_message

    def reset_status(self) -> None:
        """상태 초기화 (활성 상태로 복구)"""
        self.status = self.STATUS_ACTIVE
        self.last_error_message = None

    def to_dict(self) -> dict:
        """딕셔너리 변환 (API 키 마스킹)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_display_name": self.provider_display_name,
            "label": self.label,
            "api_key": self.masked_api_key,
            "priority": self.priority,
            "is_active": self.is_active,
            "is_available": self.is_available,
            "status": self.status,
            "usage_count": self.usage_count,
            "error_count": self.error_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_error_message": self.last_error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
