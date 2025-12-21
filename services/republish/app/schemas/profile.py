"""
프로파일 관련 스키마

Features:
- 프로파일 생성/수정/응답 스키마
- 블로그 연동 요청/응답 스키마
- 프로파일 통계 스키마
- 유효성 검증 및 타입 힌트
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ProfileStatus(str, Enum):
    """프로파일 상태"""
    ACTIVE = "active"
    PAUSED = "paused"
    INACTIVE = "inactive"


class TimeConditionType(str, Enum):
    """시간 조건 타입"""
    SPECIFIC_HOURS = "specific_hours"
    INTERVAL_HOURS = "interval_hours"
    WEEKDAYS_ONLY = "weekdays_only"


# ===========================================
# 프로파일 기본 스키마
# ===========================================

class ProfileBaseSchema(BaseModel):
    """프로파일 기본 스키마"""
    name: str = Field(..., description="프로파일 이름", max_length=100)
    description: Optional[str] = Field(None, description="프로파일 설명", max_length=500)
    status: ProfileStatus = Field(ProfileStatus.ACTIVE, description="프로파일 상태")

    # 포스트 범위 설정
    start_post_id: int = Field(..., description="시작 포스트 ID", ge=1)
    end_post_id: int = Field(..., description="종료 포스트 ID", ge=1)

    # 발행 조건
    hours_between_posts: int = Field(24, description="포스트간 간격(시간)", ge=1, le=168)
    time_condition_type: TimeConditionType = Field(
        TimeConditionType.INTERVAL_HOURS,
        description="시간 조건 타입"
    )
    specific_hours: Optional[List[int]] = Field(
        None,
        description="특정 시간대 (0-23)"
    )

    # 기타 설정
    max_posts_per_day: int = Field(5, description="일일 최대 포스트 수", ge=1, le=10)
    is_sequential: bool = Field(True, description="순차 발행 여부")

    @validator('end_post_id')
    def validate_post_range(cls, v, values):
        """포스트 범위 검증"""
        if 'start_post_id' in values and v <= values['start_post_id']:
            raise ValueError('종료 포스트 ID는 시작 포스트 ID보다 커야 합니다')
        return v

    @validator('specific_hours')
    def validate_specific_hours(cls, v, values):
        """특정 시간대 검증"""
        if v is not None:
            if not all(0 <= hour <= 23 for hour in v):
                raise ValueError('시간은 0-23 사이여야 합니다')
            if len(v) == 0:
                raise ValueError('특정 시간대는 최소 1개 이상이어야 합니다')
        return v


class ProfileCreateRequest(ProfileBaseSchema):
    """프로파일 생성 요청"""
    pass


class ProfileUpdateRequest(BaseModel):
    """프로파일 수정 요청"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[ProfileStatus] = None
    hours_between_posts: Optional[int] = Field(None, ge=1, le=168)
    time_condition_type: Optional[TimeConditionType] = None
    specific_hours: Optional[List[int]] = None
    max_posts_per_day: Optional[int] = Field(None, ge=1, le=10)
    is_sequential: Optional[bool] = None

    @validator('specific_hours')
    def validate_specific_hours(cls, v):
        """특정 시간대 검증"""
        if v is not None:
            if not all(0 <= hour <= 23 for hour in v):
                raise ValueError('시간은 0-23 사이여야 합니다')
        return v


class ProfileResponse(ProfileBaseSchema):
    """프로파일 응답"""
    id: int = Field(..., description="프로파일 ID")
    user_id: int = Field(..., description="사용자 ID")
    created_at: datetime = Field(..., description="생성일시")
    updated_at: datetime = Field(..., description="수정일시")

    # 연동 정보
    linked_blogs_count: int = Field(0, description="연동된 블로그 수")
    total_published: int = Field(0, description="총 발행 횟수")

    class Config:
        from_attributes = True


class ProfileListResponse(BaseModel):
    """프로파일 목록 응답"""
    id: int
    name: str
    description: Optional[str]
    status: ProfileStatus
    start_post_id: int
    end_post_id: int
    linked_blogs_count: int
    total_published: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# 블로그 연동 스키마
# ===========================================

class BlogLinkRequest(BaseModel):
    """블로그 연동 요청"""
    blog_id: int = Field(..., description="블로그 ID", ge=1)


class BlogUnlinkRequest(BaseModel):
    """블로그 연동 해제 요청"""
    blog_id: int = Field(..., description="블로그 ID", ge=1)


class LinkedBlogResponse(BaseModel):
    """연동된 블로그 응답"""
    blog_id: int
    blog_name: str
    blog_url: str
    blog_platform: str
    linked_at: datetime
    last_published_at: Optional[datetime]
    total_published: int

    class Config:
        from_attributes = True


class BlogLinkResponse(BaseModel):
    """블로그 연동 응답"""
    profile_id: int
    blog_id: int
    message: str
    success: bool


# ===========================================
# 프로파일 통계 스키마
# ===========================================

class ProfileStatsResponse(BaseModel):
    """프로파일 통계 응답"""
    total_profiles: int = Field(0, description="총 프로파일 수")
    active_profiles: int = Field(0, description="활성 프로파일 수")
    paused_profiles: int = Field(0, description="일시정지 프로파일 수")
    total_linked_blogs: int = Field(0, description="총 연동된 블로그 수")
    total_published_posts: int = Field(0, description="총 발행된 포스트 수")

    # 상태별 분포
    by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="상태별 프로파일 수"
    )

    # 최근 활동
    recent_activity: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="최근 활동 내역"
    )


class ProfileDetailStatsResponse(BaseModel):
    """프로파일 상세 통계 응답"""
    profile_id: int
    profile_name: str

    # 발행 통계
    total_published: int = Field(0, description="총 발행 횟수")
    successful_publishes: int = Field(0, description="성공한 발행")
    failed_publishes: int = Field(0, description="실패한 발행")
    success_rate: float = Field(0.0, description="성공률")

    # 연동 블로그 통계
    linked_blogs: List[LinkedBlogResponse] = Field(
        default_factory=list,
        description="연동된 블로그 목록"
    )

    # 시간대별 통계 (24시간)
    hourly_stats: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="시간대별 발행 통계"
    )

    # 일별 통계 (최근 30일)
    daily_stats: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="일별 발행 통계"
    )


# ===========================================
# 에러 응답
# ===========================================

class ErrorResponse(BaseModel):
    """에러 응답"""
    message: str = Field(..., description="에러 메시지")
    detail: Optional[str] = Field(None, description="상세 에러 내용")
    error_code: Optional[str] = Field(None, description="에러 코드")