"""
재발행 프로파일 모델

Features:
- 포스트 범위 기반 재발행 설정
- 간격 설정 (수동/자동)
- 불규칙 간격(Jitter) 적용
- 활성 시간대 및 제외 요일 설정
- 플랫폼별 제한 오버라이드
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class PublishProfile(Base):
    """재발행 프로파일"""
    __tablename__ = "publish_profiles"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="프로파일 이름")

    # 포스트 범위 설정
    min_post_count = Column(Integer, default=10, comment="활성화 최소 포스트 수")
    post_range_start = Column(Integer, default=1, comment="포스트 범위 시작")
    post_range_end = Column(Integer, nullable=True, comment="포스트 범위 끝 (None=무제한)")

    # 간격 설정
    interval_mode = Column(String(10), default="manual", comment="간격 모드: manual/auto")
    manual_interval_minutes = Column(Integer, nullable=True, comment="수동 간격(분)")
    auto_daily_count = Column(Integer, nullable=True, comment="자동 모드 일일 목표 횟수")

    # 불규칙 간격 설정
    jitter_enabled = Column(Boolean, default=True, comment="불규칙 간격 활성화")
    jitter_min_percent = Column(Integer, default=-20, comment="최소 변동률(%)")
    jitter_max_percent = Column(Integer, default=30, comment="최대 변동률(%)")

    # 활성 시간대 설정
    active_hours_start = Column(String(5), default="09:00", comment="활성 시간 시작")
    active_hours_end = Column(String(5), default="22:00", comment="활성 시간 종료")
    blackout_days = Column(JSON, default=[], comment="제외 요일 [0=월요일, 6=일요일]")

    # 쿨다운 설정
    cooldown_days = Column(Integer, default=7, comment="동일 포스트 재발행 금지 일수")

    # 우선순위
    priority = Column(Integer, default=1, comment="우선순위 (1=최우선)")

    # 플랫폼별 제한 오버라이드
    platform_overrides = Column(JSON, default={}, comment="플랫폼별 설정 오버라이드")

    # 상태 및 메타
    is_active = Column(Boolean, default=True, comment="활성 상태")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    blog_links = relationship("BlogProfileLink", back_populates="profile")

    @property
    def calculated_interval_minutes(self) -> int:
        """자동 모드일 때 간격 계산"""
        if self.interval_mode == "auto" and self.auto_daily_count:
            # 24시간 = 1440분 / 일일 목표 횟수
            return max(5, int(1440 / self.auto_daily_count))
        return self.manual_interval_minutes or 60

    def __repr__(self) -> str:
        return f"<PublishProfile(id={self.id}, name='{self.name}', range={self.post_range_start}-{self.post_range_end})>"