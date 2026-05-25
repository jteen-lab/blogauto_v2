"""
모듈 모델 - 기존 PublishProfile을 대체

Features:
- 다양한 타입의 모듈 지원 (프롬프트, 생성, 발행, 재발행)
- 기존 재발행 설정 모두 포함
- is_active 필드 제거 (플로우 레벨에서 관리)
- 타입별 추가 설정을 위한 유연한 JSONB 필드
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class Module(Base):
    """모듈 - 기존 PublishProfile 대체"""
    __tablename__ = "modules"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True, comment="사용자 ID")
    module_type_id = Column(
        Integer,
        ForeignKey("module_types.id"),
        nullable=False,
        index=True,
        comment="모듈 타입 ID"
    )
    name = Column(String(255), nullable=False, comment="모듈 이름")
    description = Column(Text, nullable=True, comment="모듈 설명")

    # 타입별 추가 설정 (확장성을 위한 JSONB)
    # Note: 스케줄/간격/jitter/활성시간대 등 레거시 컬럼은
    # 029 마이그레이션에서 제거됨. 모든 스케줄 제어는 Growth Profile에서 담당.
    settings = Column(JSONB, default=dict, comment="타입별 추가 설정")

    # is_active 필드 없음! 플로우 레벨에서 관리

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # 관계
    module_type = relationship("ModuleType", back_populates="modules")
    flow_links = relationship(
        "FlowModule",
        back_populates="module",
        cascade="all, delete-orphan"
    )

    def get_setting(self, key: str, default: Any = None) -> Any:
        """타입별 설정 값 조회"""
        if not self.settings:
            return default
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """타입별 설정 값 설정"""
        if not self.settings:
            self.settings = {}
        self.settings[key] = value

    def __repr__(self) -> str:
        return (
            f"<Module(id={self.id}, name='{self.name}', "
            f"type_id={self.module_type_id})>"
        )