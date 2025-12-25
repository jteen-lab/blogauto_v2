"""
Blogger 슬롯 관리 스키마

Features:
- 시간 슬롯 생성/조회/할당
- 슬롯 충돌 검사
- 가용성 분석
"""
from pydantic import BaseModel, validator
from datetime import datetime, time
from typing import Optional, List, Dict, Any
from enum import Enum


class SlotAssignmentType(str, Enum):
    """슬롯 할당 타입"""
    BLOG = "blog"
    GROUP = "group"
    PROFILE = "profile"


class BloggerSlotBase(BaseModel):
    """Blogger 슬롯 기본 스키마"""
    day_of_week: int
    hour: int
    minute: int

    @validator('day_of_week')
    def validate_day_of_week(cls, v):
        if not 0 <= v <= 6:
            raise ValueError('요일은 0(월)~6(일) 범위여야 합니다')
        return v

    @validator('hour')
    def validate_hour(cls, v):
        if not 0 <= v <= 23:
            raise ValueError('시간은 0~23 범위여야 합니다')
        return v

    @validator('minute')
    def validate_minute(cls, v):
        if v not in [0, 15, 30, 45]:
            raise ValueError('분은 0, 15, 30, 45 중 하나여야 합니다')
        return v


class BloggerSlotCreate(BloggerSlotBase):
    """Blogger 슬롯 생성 스키마"""
    google_credential_id: int
    assignment_type: Optional[SlotAssignmentType] = None
    assignment_id: Optional[int] = None

    @validator('google_credential_id')
    def validate_credential_id(cls, v):
        if v <= 0:
            raise ValueError('유효한 Google 계정 ID가 필요합니다')
        return v

    @validator('assignment_id')
    def validate_assignment_id(cls, v, values):
        assignment_type = values.get('assignment_type')
        if assignment_type and not v:
            raise ValueError('할당 타입이 지정된 경우 할당 ID가 필요합니다')
        if not assignment_type and v:
            raise ValueError('할당 ID가 지정된 경우 할당 타입이 필요합니다')
        if v is not None and v <= 0:
            raise ValueError('할당 ID는 양수여야 합니다')
        return v


class BloggerSlotUpdate(BaseModel):
    """Blogger 슬롯 업데이트 스키마"""
    assignment_type: Optional[SlotAssignmentType] = None
    assignment_id: Optional[int] = None

    @validator('assignment_id')
    def validate_assignment_id(cls, v, values):
        assignment_type = values.get('assignment_type')
        if assignment_type and not v:
            raise ValueError('할당 타입이 지정된 경우 할당 ID가 필요합니다')
        if v is not None and v <= 0:
            raise ValueError('할당 ID는 양수여야 합니다')
        return v


class BloggerSlotResponse(BloggerSlotBase):
    """Blogger 슬롯 응답 스키마"""
    id: int
    google_credential_id: int
    time_str: str
    day_name_kr: str
    day_name_en: str
    assignment_type: Optional[str]
    assignment_id: Optional[int]
    blog_id: Optional[int]
    group_id: Optional[int]
    profile_id: Optional[int]
    is_weekend: bool
    is_business_hour: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BloggerSlotConflict(BaseModel):
    """슬롯 충돌 정보 스키마"""
    time_slot: str  # "월 09:30"
    day_of_week: int
    hour: int
    minute: int
    conflicting_slot: Optional[BloggerSlotResponse] = None
    is_conflicted: bool

    class Config:
        from_attributes = True


class BloggerSlotAvailability(BaseModel):
    """슬롯 가용성 정보 스키마"""
    google_credential_id: int
    total_possible_slots: int
    used_slots: int
    available_slots: int
    utilization_rate: float
    peak_hours: List[int]
    recommended_times: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class WeeklySlotGrid(BaseModel):
    """주간 슬롯 그리드 스키마"""
    google_credential_id: int
    grid: Dict[str, Dict[str, Optional[BloggerSlotResponse]]]  # {"0": {"09:00": slot_info}}
    summary: Dict[str, Any]

    class Config:
        from_attributes = True


class SlotRecommendation(BaseModel):
    """슬롯 추천 스키마"""
    day_of_week: int
    hour: int
    minute: int
    score: float
    reasons: List[str]
    conflicts: List[str]

    class Config:
        from_attributes = True


# 추가 스키마들

class SlotInfo(BaseModel):
    """슬롯 정보"""
    day_of_week: int
    hour: int
    minute: int
    blog_id: Optional[int] = None
    blog_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None

    class Config:
        from_attributes = True


class SlotConflict(BaseModel):
    """슬롯 충돌 정보"""
    day_of_week: int
    hour: int
    minute: int
    profile_name: str
    conflicting_blog_name: str
    conflicting_group_name: str
    alternatives: List[int]  # 가용한 분(minute) 목록

    class Config:
        from_attributes = True


class SlotSuggestion(BaseModel):
    """슬롯 제안"""
    hour: int
    available_minutes: List[int]
    recommendation: str

    class Config:
        from_attributes = True


class ValidationResult(BaseModel):
    """슬롯 검증 결과"""
    valid: bool
    conflicts: List[SlotConflict]
    reservable: List[SlotInfo]
    suggestions: List[SlotSuggestion]

    class Config:
        from_attributes = True


class AddBlogResult(BaseModel):
    """블로그 추가 결과"""
    success: bool
    message: str
    conflicts: Optional[List[SlotConflict]] = None
    reserved_slots: Optional[List[SlotInfo]] = None
    suggestions: Optional[List[SlotSuggestion]] = None

    class Config:
        from_attributes = True


class ScheduleInfo(BaseModel):
    """스케줄 정보"""
    profile_id: int
    profile_name: str
    day_of_week: int
    hour: int
    minute: int

    class Config:
        from_attributes = True


class SlotReservation(BaseModel):
    """슬롯 예약 요청"""
    profile_id: int
    day_of_week: int
    hour: int
    minute: int

    class Config:
        from_attributes = True