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
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
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
        comment="모듈 타입 ID"
    )
    name = Column(String(255), nullable=False, comment="모듈 이름")
    description = Column(Text, nullable=True, comment="모듈 설명")

    # 스케줄 설정 (기존 republish_profiles에서 이전)
    schedule_matrix = Column(JSONB, nullable=True, comment="7x24 스케줄 매트릭스")
    manual_interval_minutes = Column(Integer, nullable=True, comment="수동 간격(분)")

    # 기존 republish_profile 설정들
    min_post_count = Column(Integer, default=10, comment="활성화 최소 포스트 수")
    interval_mode = Column(String(10), default="manual", comment="간격 모드")
    auto_daily_count = Column(Integer, nullable=True, comment="자동 모드 일일 목표")

    # 불규칙 간격 설정
    jitter_enabled = Column(Boolean, default=True, comment="불규칙 간격 활성화")
    jitter_min_percent = Column(Integer, default=-20, comment="최소 변동률(%)")
    jitter_max_percent = Column(Integer, default=30, comment="최대 변동률(%)")

    # 활성 시간대 설정
    active_hours_start = Column(String(5), default="09:00", comment="활성 시간 시작")
    active_hours_end = Column(String(5), default="22:00", comment="활성 시간 종료")
    blackout_days = Column(JSONB, default=list, comment="제외 요일")

    # 기타 설정
    cooldown_days = Column(Integer, default=7, comment="동일 포스트 재발행 금지 일수")
    priority = Column(Integer, default=1, comment="우선순위")
    platform_overrides = Column(JSONB, default=dict, comment="플랫폼별 오버라이드")

    # 타입별 추가 설정 (확장성을 위한 JSONB)
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