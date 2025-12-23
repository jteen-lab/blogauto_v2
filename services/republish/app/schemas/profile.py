"""
프로파일 관련 스키마
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class IntervalMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


class ProfileCreateRequest(BaseModel):
    """프로파일 생성 요청"""
    name: str = Field(..., max_length=100)
    is_active: bool = Field(True)
    min_post_count: int = Field(10, ge=1)
    post_range_start: int = Field(1, ge=1)
    post_range_end: Optional[int] = None
    interval_mode: IntervalMode = Field(IntervalMode.MANUAL)
    manual_interval_minutes: Optional[int] = Field(60, ge=1, le=1440)
    auto_daily_count: Optional[int] = Field(None, ge=1, le=100)
    jitter_enabled: bool = Field(False)
    jitter_min_percent: int = Field(0, ge=-50, le=0)
    jitter_max_percent: int = Field(0, ge=0, le=100)
    active_hours_start: str = Field("00:00")
    active_hours_end: str = Field("23:59")
    cooldown_days: int = Field(7, ge=1, le=365)
    priority: int = Field(1, ge=1, le=10)
    schedule_matrix: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    """프로파일 수정 요청"""
    name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    min_post_count: Optional[int] = Field(None, ge=1)
    post_range_start: Optional[int] = Field(None, ge=1)
    post_range_end: Optional[int] = None
    interval_mode: Optional[IntervalMode] = None
    manual_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    auto_daily_count: Optional[int] = Field(None, ge=1, le=100)
    jitter_enabled: Optional[bool] = None
    jitter_min_percent: Optional[int] = Field(None, ge=-50, le=0)
    jitter_max_percent: Optional[int] = Field(None, ge=0, le=100)
    active_hours_start: Optional[str] = None
    active_hours_end: Optional[str] = None
    cooldown_days: Optional[int] = Field(None, ge=1, le=365)
    priority: Optional[int] = Field(None, ge=1, le=10)
    schedule_matrix: Optional[str] = None


class ProfileResponse(BaseModel):
    """프로파일 응답"""
    id: int
    user_id: int
    name: str
    is_active: bool
    min_post_count: int
    post_range_start: int
    post_range_end: Optional[int]
    interval_mode: str
    manual_interval_minutes: Optional[int]
    auto_daily_count: Optional[int]
    jitter_enabled: bool
    jitter_min_percent: int
    jitter_max_percent: int
    active_hours_start: str
    active_hours_end: str
    cooldown_days: int
    priority: int
    schedule_matrix: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    linked_blogs_count: int = 0
    total_published: int = 0

    class Config:
        from_attributes = True


class ProfileListResponse(BaseModel):
    """프로파일 목록 응답"""
    id: int
    name: str
    is_active: bool
    min_post_count: int
    post_range_start: int
    post_range_end: Optional[int]
    interval_mode: str
    priority: int
    created_at: datetime

    class Config:
        from_attributes = True


class BlogLinkRequest(BaseModel):
    blog_id: int = Field(..., ge=1)


class BlogUnlinkRequest(BaseModel):
    blog_id: int = Field(..., ge=1)


class BlogLinkResponse(BaseModel):
    profile_id: int
    blog_id: int
    message: str
    success: bool


class LinkedBlogResponse(BaseModel):
    blog_id: int
    blog_name: str
    blog_url: str
    linked_at: datetime

    class Config:
        from_attributes = True


class ProfileStatsResponse(BaseModel):
    total_profiles: int = 0
    active_profiles: int = 0
    inactive_profiles: int = 0


class ProfileDetailStatsResponse(BaseModel):
    profile_id: int
    profile_name: str
    total_published: int = 0
    successful_publishes: int = 0
    failed_publishes: int = 0
    success_rate: float = 0.0
    linked_blogs: List[LinkedBlogResponse] = []
    hourly_stats: List[Dict[str, Any]] = []
    daily_stats: List[Dict[str, Any]] = []


class ErrorResponse(BaseModel):
    message: str
    detail: Optional[str] = None
