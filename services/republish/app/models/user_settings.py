"""
사용자 설정 모델

Features:
- AI 서비스 API 키 관리
- Google Blogger 시간당 발행 제한 설정
- 사용자별 1:1 설정 테이블
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from typing import Optional

from ..core.database import Base


class UserSettings(Base):
    """사용자 설정 모델"""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            'blogger_hourly_limit BETWEEN 1 AND 4',
            name='check_blogger_hourly_limit_range'
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # user_id는 단일 사용자 환경에서 기본값 1 사용 (FK 제거로 독립 동작)
    user_id = Column(
        Integer,
        default=1,
        nullable=False,
        index=True
    )

    # AI 서비스 설정
    openai_api_key = Column(String(255), nullable=True)
    claude_api_key = Column(String(255), nullable=True)
    default_ai_model = Column(String(50), default="gpt-4", nullable=False)

    # API 설정
    blogger_hourly_limit = Column(Integer, default=2, nullable=False)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 관계 설정 (FK 제거로 relationship도 제거)
    # user = relationship("User", backref="settings", uselist=False)

    def __repr__(self) -> str:
        return f"<UserSettings(user_id={self.user_id}, model={self.default_ai_model})>"

    @property
    def has_openai_key(self) -> bool:
        """OpenAI API 키 설정 여부"""
        return bool(self.openai_api_key)

    @property
    def has_claude_key(self) -> bool:
        """Claude API 키 설정 여부"""
        return bool(self.claude_api_key)

    @property
    def masked_openai_key(self) -> Optional[str]:
        """마스킹된 OpenAI API 키 (앞 4자 + **** + 뒤 4자)"""
        if not self.openai_api_key:
            return None
        if len(self.openai_api_key) <= 8:
            return "****"
        return f"{self.openai_api_key[:4]}****{self.openai_api_key[-4:]}"

    @property
    def masked_claude_key(self) -> Optional[str]:
        """마스킹된 Claude API 키"""
        if not self.claude_api_key:
            return None
        if len(self.claude_api_key) <= 8:
            return "****"
        return f"{self.claude_api_key[:4]}****{self.claude_api_key[-4:]}"

    def to_dict(self) -> dict:
        """딕셔너리 변환 (API 키 마스킹)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "openai_api_key": self.masked_openai_key,
            "claude_api_key": self.masked_claude_key,
            "default_ai_model": self.default_ai_model,
            "blogger_hourly_limit": self.blogger_hourly_limit,
            "has_openai_key": self.has_openai_key,
            "has_claude_key": self.has_claude_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
