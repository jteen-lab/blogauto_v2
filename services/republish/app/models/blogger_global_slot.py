"""
Blogger 전역 슬롯 관리 모델

Features:
- Google 계정별 시간 슬롯 예약
- 블로그, 그룹, 프로파일별 슬롯 할당
- 주간 스케줄링 지원
- 슬롯 충돌 방지
"""
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Any, Optional

from ..core.database import Base


class BloggerGlobalSlot(Base):
    """Blogger 전역 슬롯 모델"""

    __tablename__ = "blogger_global_slots"

    # 기본 정보
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    google_credential_id = Column(
        Integer,
        ForeignKey("google_credentials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Google 계정 ID"
    )

    # 시간 슬롯
    day_of_week = Column(
        Integer,
        nullable=False,
        comment="요일 (0=월요일, 6=일요일)"
    )
    hour = Column(
        Integer,
        nullable=False,
        comment="시간 (0-23)"
    )
    minute = Column(
        Integer,
        nullable=False,
        comment="분 (0, 30 등)"
    )

    # 할당 대상 (하나만 설정)
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=True,
        comment="할당된 블로그 ID"
    )
    module_id = Column(
        Integer,
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=True,
        comment="할당된 모듈 ID (새 시스템)"
    )
    flow_id = Column(
        Integer,
        ForeignKey("flows.id", ondelete="CASCADE"),
        nullable=True,
        comment="할당된 플로우 ID (새 시스템)"
    )
    # 레거시 참조 제거됨
    # group_id = Column(Integer, ForeignKey("profile_groups.id", ondelete="CASCADE"), nullable=True)  # 제거됨
    # profile_id = Column(Integer, ForeignKey("publish_profiles.id", ondelete="CASCADE"), nullable=True)  # 제거됨

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 제약 조건: Google 계정별 시간 슬롯은 유일해야 함
    __table_args__ = (
        UniqueConstraint(
            'google_credential_id', 'day_of_week', 'hour', 'minute',
            name='uq_credential_time_slot'
        ),
    )

    # 관계 설정
    google_credential = relationship("GoogleCredential", back_populates="blogger_slots")
    blog = relationship("Blog")
    module = relationship("Module")
    flow = relationship("Flow")
    # 레거시 relationship 제거됨
    # group = relationship("ProfileGroup")  # 제거됨 (Flow 시스템으로 교체)
    # profile = relationship("PublishProfile")  # 제거됨 (Module 시스템으로 교체)

    def __repr__(self) -> str:
        return (f"<BloggerGlobalSlot(id={self.id}, credential_id={self.google_credential_id}, "
                f"dow={self.day_of_week}, time={self.hour:02d}:{self.minute:02d})>")

    def __str__(self) -> str:
        day_names = ["월", "화", "수", "목", "금", "토", "일"]
        day_name = day_names[self.day_of_week] if 0 <= self.day_of_week <= 6 else str(self.day_of_week)
        return f"Slot #{self.id} ({day_name} {self.hour:02d}:{self.minute:02d})"

    @property
    def time_str(self) -> str:
        """시간 문자열 (HH:MM 형식)"""
        return f"{self.hour:02d}:{self.minute:02d}"

    @property
    def day_name_kr(self) -> str:
        """한글 요일명"""
        day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        return day_names[self.day_of_week] if 0 <= self.day_of_week <= 6 else "알 수 없음"

    @property
    def day_name_en(self) -> str:
        """영문 요일명"""
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return day_names[self.day_of_week] if 0 <= self.day_of_week <= 6 else "Unknown"

    @property
    def assignment_type(self) -> Optional[str]:
        """할당 타입 반환"""
        if self.blog_id:
            return "blog"
        elif self.module_id:
            return "module"
        elif self.flow_id:
            return "flow"
        return None

    @property
    def assignment_id(self) -> Optional[int]:
        """할당 대상 ID 반환"""
        if self.blog_id:
            return self.blog_id
        elif self.module_id:
            return self.module_id
        elif self.flow_id:
            return self.flow_id
        return None

    @property
    def is_weekend(self) -> bool:
        """주말 여부 확인"""
        return self.day_of_week in [5, 6]  # 토요일, 일요일

    @property
    def is_business_hour(self) -> bool:
        """업무 시간 여부 확인 (9-18시)"""
        return 9 <= self.hour <= 18

    def assign_to_blog(self, blog_id: int) -> None:
        """블로그에 할당"""
        self.clear_assignment()
        self.blog_id = blog_id

    def assign_to_module(self, module_id: int) -> None:
        """모듈에 할당 (새 시스템)"""
        self.clear_assignment()
        self.module_id = module_id

    def assign_to_flow(self, flow_id: int) -> None:
        """플로우에 할당 (새 시스템)"""
        self.clear_assignment()
        self.flow_id = flow_id

    # 레거시 메소드들 (호환성을 위해 유지, 새 시스템으로 리디렉션)
    def assign_to_group(self, group_id: int) -> None:
        """그룹에 할당 (레거시 - 플로우로 리디렉션)"""
        # 레거시 호환성: 그룹 ID를 플로우 ID로 처리
        self.assign_to_flow(group_id)

    def assign_to_profile(self, profile_id: int) -> None:
        """프로파일에 할당 (레거시 - 모듈로 리디렉션)"""
        # 레거시 호환성: 프로파일 ID를 모듈 ID로 처리
        self.assign_to_module(profile_id)

    def clear_assignment(self) -> None:
        """할당 해제"""
        self.blog_id = None
        self.module_id = None
        self.flow_id = None

    def is_same_time(self, day_of_week: int, hour: int, minute: int) -> bool:
        """동일한 시간 슬롯인지 확인"""
        return (
            self.day_of_week == day_of_week and
            self.hour == hour and
            self.minute == minute
        )

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "google_credential_id": self.google_credential_id,
            "day_of_week": self.day_of_week,
            "hour": self.hour,
            "minute": self.minute,
            "time_str": self.time_str,
            "day_name_kr": self.day_name_kr,
            "day_name_en": self.day_name_en,
            "assignment_type": self.assignment_type,
            "assignment_id": self.assignment_id,
            "blog_id": self.blog_id,
            "module_id": self.module_id,
            "flow_id": self.flow_id,
            # 레거시 필드는 제거됨
            # "group_id": self.group_id,  # 제거됨
            # "profile_id": self.profile_id,  # 제거됨
            "is_weekend": self.is_weekend,
            "is_business_hour": self.is_business_hour,
            "created_at": self.created_at
        }