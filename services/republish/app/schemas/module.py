"""
모듈 관련 스키마

Features:
- 모듈 생성/수정/조회 요청/응답 스키마
- 모듈 타입별 설정 지원
- 기존 ProfileCreateRequest 호환성
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class IntervalMode(str, Enum):
    """간격 모드"""
    MANUAL = "manual"
    AUTO = "auto"


class ModuleTypeResponse(BaseModel):
    """모듈 타입 응답"""
    id: int
    code: str
    name: str
    icon: Optional[str] = None
    display_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class ModuleCreateRequest(BaseModel):
    """모듈 생성 요청"""
    module_type_code: str = Field(..., description="모듈 타입 코드")
    name: str = Field(..., min_length=1, max_length=255, description="모듈 이름")
    description: Optional[str] = Field(None, max_length=500, description="모듈 설명")

    # 스케줄 설정 (republish 타입 등)
    schedule_matrix: Optional[Union[List[List[bool]], str]] = Field(
        None, description="7x24 스케줄 매트릭스"
    )
    manual_interval_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="수동 간격(분)"
    )

    # 재발행 설정 (republish 타입)
    min_post_count: int = Field(10, ge=1, description="활성화 최소 포스트 수")
    post_range_start: int = Field(1, ge=1, description="포스트 범위 시작")
    post_range_end: Optional[int] = Field(None, ge=1, description="포스트 범위 끝")
    interval_mode: IntervalMode = Field(IntervalMode.MANUAL, description="간격 모드")
    auto_daily_count: Optional[int] = Field(None, ge=1, le=100, description="자동 모드 일일 목표")

    # 불규칙 간격 설정
    jitter_enabled: bool = Field(True, description="불규칙 간격 활성화")
    jitter_min_percent: int = Field(-20, ge=-50, le=0, description="최소 변동률(%)")
    jitter_max_percent: int = Field(30, ge=0, le=100, description="최대 변동률(%)")

    # 활성 시간대 설정
    active_hours_start: str = Field("09:00", pattern=r"^[0-2][0-9]:[0-5][0-9]$")
    active_hours_end: str = Field("22:00", pattern=r"^[0-2][0-9]:[0-5][0-9]$")
    blackout_days: List[int] = Field(default_factory=list, description="제외 요일")

    # 기타 설정
    cooldown_days: int = Field(7, ge=1, le=365, description="재발행 금지 일수")
    priority: int = Field(1, ge=1, le=10, description="우선순위")
    is_active: bool = True  # 기본값 (플로우 레벨에서 실제 관리)
    type_code: Optional[str] = None  # module_type.code 복사본
    platform_overrides: Dict[str, Any] = Field(default_factory=dict)

    # 타입별 추가 설정
    settings: Dict[str, Any] = Field(default_factory=dict, description="타입별 설정")

    @field_validator("post_range_end")
    @classmethod
    def validate_post_range(cls, v, info):
        """포스트 범위 유효성 검사"""
        if v is not None and "post_range_start" in info.data:
            if v <= info.data["post_range_start"]:
                raise ValueError("post_range_end must be greater than post_range_start")
        return v

    @field_validator("auto_daily_count")
    @classmethod
    def validate_auto_daily_count(cls, v, info):
        """자동 모드 설정 검사"""
        if "interval_mode" in info.data and info.data["interval_mode"] == "auto":
            if v is None:
                raise ValueError("auto_daily_count is required when interval_mode is auto")
        return v


class ModuleUpdateRequest(BaseModel):
    """모듈 수정 요청

    Note:
        description 필드는 빈 문자열("")로 설정하면 설명을 삭제합니다.
        None은 필드를 업데이트하지 않음을 의미합니다.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)  # ""는 삭제, None은 미변경

    # 스케줄 설정
    schedule_matrix: Optional[Union[List[List[bool]], str]] = None
    manual_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)

    # 재발행 설정
    min_post_count: Optional[int] = Field(None, ge=1)
    post_range_start: Optional[int] = Field(None, ge=1)
    post_range_end: Optional[int] = Field(None, ge=1)
    interval_mode: Optional[IntervalMode] = None
    auto_daily_count: Optional[int] = Field(None, ge=1, le=100)

    # 불규칙 간격 설정
    jitter_enabled: Optional[bool] = None
    jitter_min_percent: Optional[int] = Field(None, ge=-50, le=0)
    jitter_max_percent: Optional[int] = Field(None, ge=0, le=100)

    # 활성 시간대 설정
    active_hours_start: Optional[str] = Field(None, pattern=r"^[0-2][0-9]:[0-5][0-9]$")
    active_hours_end: Optional[str] = Field(None, pattern=r"^[0-2][0-9]:[0-5][0-9]$")
    blackout_days: Optional[List[int]] = None

    # 기타 설정
    cooldown_days: Optional[int] = Field(None, ge=1, le=365)
    priority: Optional[int] = Field(None, ge=1, le=10)
    platform_overrides: Optional[Dict[str, Any]] = None

    # 타입별 추가 설정
    settings: Optional[Dict[str, Any]] = None


class ModuleResponse(BaseModel):
    """모듈 응답"""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    module_type: ModuleTypeResponse

    # 주요 설정 (UI 표시용)
    manual_interval_minutes: Optional[int]
    interval_mode: str
    priority: int
    is_active: bool = True  # 기본값 (플로우 레벨에서 실제 관리)
    type_code: Optional[str] = None  # module_type.code 복사본

    # 편집을 위한 상세 필드들 (Optional)
    schedule_matrix: Optional[Union[List[List[bool]], Dict[str, Any]]] = None
    min_post_count: Optional[int] = None
    post_range_start: Optional[int] = None
    post_range_end: Optional[int] = None
    auto_daily_count: Optional[int] = None

    # 타입별 설정 (collect 등)
    settings: Dict[str, Any] = Field(default_factory=dict, description="타입별 설정")

    # 메타 정보
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModuleDetailResponse(ModuleResponse):
    """모듈 상세 응답"""
    # 상속받지 않는 추가 상세 필드들

    # 불규칙 간격 설정
    jitter_enabled: bool
    jitter_min_percent: int
    jitter_max_percent: int

    # 활성 시간대 설정
    active_hours_start: str
    active_hours_end: str
    blackout_days: List[int]

    # 기타 설정 (collect 등 일부 타입은 cooldown_days가 없음)
    cooldown_days: Optional[int] = None
    platform_overrides: Dict[str, Any]
    settings: Dict[str, Any]

    # 계산된 값
    calculated_interval_minutes: Optional[int] = None


class ModuleListResponse(BaseModel):
    """모듈 목록 응답"""
    modules: List[ModuleResponse]
    total: int
    page: int
    size: int
    has_next: bool