"""시스템 설정 모델 (Key-Value).

Celery 워커 플래그, Rate Limit 수치 등
운영자가 UI에서 관리하는 시스템 설정�� 저장합니다.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from ..core.database import Base


class SystemSettings(Base):
    """시스템 설정 (Key-Value 방식)."""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    key = Column(
        String(100), unique=True, nullable=False, index=True,
        comment="설정 키 (예: use_celery_generation)",
    )
    value = Column(Text, nullable=True, comment="설정 값")
    value_type = Column(
        String(20), default="string",
        comment="값 타입 (string, bool, int, float)",
    )
    category = Column(
        String(50), nullable=False,
        comment="카테고리 (celery, ratelimit, system)",
    )
    description = Column(Text, nullable=True, comment="설정 ���명")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<SystemSettings(key={self.key}, value={self.value})>"
