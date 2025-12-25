"""
Google 계정 정책 스키마

Features:
- 계정별 발행 정책 설정
- 시간대 및 제한 설정 검증
- 안전 모드 적용
"""
from pydantic import BaseModel, validator
from datetime import datetime
from typing import Optional


class GoogleAccountPolicyBase(BaseModel):
    """Google 계정 정책 기본 스키마"""
    min_interval_minutes: Optional[int] = 30
    max_daily_per_blog: Optional[int] = 5
    max_daily_total: Optional[int] = 50
    allowed_hours_start: Optional[int] = 9
    allowed_hours_end: Optional[int] = 22
    safety_mode: Optional[bool] = True

    @validator('min_interval_minutes')
    def validate_min_interval(cls, v):
        if v is not None and (v < 10 or v > 1440):  # 10분~24시간
            raise ValueError('최소 간격은 10분~1440분 범위여야 합니다')
        return v

    @validator('max_daily_per_blog')
    def validate_max_daily_per_blog(cls, v):
        if v is not None and (v < 1 or v > 100):
            raise ValueError('블로그당 일일 최대 발행 수는 1~100 범위여야 합니다')
        return v

    @validator('max_daily_total')
    def validate_max_daily_total(cls, v):
        if v is not None and (v < 1 or v > 1000):
            raise ValueError('일일 총 최대 발행 수는 1~1000 범위여야 합니다')
        return v

    @validator('allowed_hours_start')
    def validate_hours_start(cls, v):
        if v is not None and (v < 0 or v > 23):
            raise ValueError('시작 시간은 0~23 범위여야 합니다')
        return v

    @validator('allowed_hours_end')
    def validate_hours_end(cls, v):
        if v is not None and (v < 0 or v > 23):
            raise ValueError('종료 시간은 0~23 범위여야 합니다')
        return v


class GoogleAccountPolicyCreate(GoogleAccountPolicyBase):
    """Google 계정 정책 생성 스키마"""
    google_credential_id: int

    @validator('google_credential_id')
    def validate_credential_id(cls, v):
        if v <= 0:
            raise ValueError('유효한 Google 계정 ID가 필요합니다')
        return v


class GoogleAccountPolicyUpdate(GoogleAccountPolicyBase):
    """Google 계정 정책 업데이트 스키마"""
    pass


class GoogleAccountPolicyResponse(GoogleAccountPolicyBase):
    """Google 계정 정책 응답 스키마"""
    id: int
    google_credential_id: int
    slots_per_hour: int
    working_hours_count: int
    is_conservative_policy: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicyEffectiveness(BaseModel):
    """정책 효과성 분석 스키마"""
    credential_id: int
    policy: GoogleAccountPolicyResponse
    daily_slots_available: int
    total_weekly_slots: int
    average_slots_per_day: float
    bottleneck_analysis: dict

    class Config:
        from_attributes = True