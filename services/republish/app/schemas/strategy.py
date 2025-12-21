"""
발행 비중 전략 관련 스키마

Features:
- 블로그별 발행 비중 전략 스키마
- 비중 조절 요청/응답 스키마
- 전략 통계 스키마
- 자동/수동 비중 조절 설정
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class WeightAdjustmentType(str, Enum):
    """비중 조절 타입"""
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class StrategyStatus(str, Enum):
    """전략 상태"""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


# ===========================================
# 전략 기본 스키마
# ===========================================

class StrategyBaseSchema(BaseModel):
    """전략 기본 스키마"""
    weight_percentage: float = Field(
        50.0,
        description="발행 비중 (%)",
        ge=0.0,
        le=100.0
    )
    adjustment_type: WeightAdjustmentType = Field(
        WeightAdjustmentType.AUTOMATIC,
        description="비중 조절 타입"
    )
    status: StrategyStatus = Field(
        StrategyStatus.ACTIVE,
        description="전략 상태"
    )

    # 자동 조절 설정
    enable_new_blog_priority: bool = Field(
        True,
        description="신규 블로그 우선 정책 활성화"
    )
    min_posts_for_adjustment: int = Field(
        10,
        description="비중 조절을 위한 최소 포스트 수",
        ge=1,
        le=100
    )
    weight_adjustment_threshold: int = Field(
        5,
        description="비중 조절 임계값 (포스트 수)",
        ge=1,
        le=20
    )

    # 제한 설정
    max_posts_per_day: int = Field(
        3,
        description="일일 최대 발행 포스트 수",
        ge=1,
        le=10
    )
    cooldown_hours: int = Field(
        4,
        description="발행 후 대기 시간 (시간)",
        ge=1,
        le=48
    )


class StrategyUpdateRequest(BaseModel):
    """전략 수정 요청"""
    weight_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    adjustment_type: Optional[WeightAdjustmentType] = None
    status: Optional[StrategyStatus] = None
    enable_new_blog_priority: Optional[bool] = None
    min_posts_for_adjustment: Optional[int] = Field(None, ge=1, le=100)
    weight_adjustment_threshold: Optional[int] = Field(None, ge=1, le=20)
    max_posts_per_day: Optional[int] = Field(None, ge=1, le=10)
    cooldown_hours: Optional[int] = Field(None, ge=1, le=48)


class StrategyResponse(StrategyBaseSchema):
    """전략 응답"""
    id: int = Field(..., description="전략 ID")
    blog_id: int = Field(..., description="블로그 ID")
    user_id: int = Field(..., description="사용자 ID")
    created_at: datetime = Field(..., description="생성일시")
    updated_at: datetime = Field(..., description="수정일시")

    # 블로그 정보
    blog_name: str = Field("", description="블로그 이름")
    blog_platform: str = Field("", description="블로그 플랫폼")

    # 통계 정보
    total_posts_published: int = Field(0, description="총 발행된 포스트 수")
    posts_published_today: int = Field(0, description="오늘 발행된 포스트 수")
    last_published_at: Optional[datetime] = Field(None, description="마지막 발행일시")
    next_publish_available_at: Optional[datetime] = Field(
        None,
        description="다음 발행 가능 시간"
    )

    class Config:
        from_attributes = True


# ===========================================
# 전략 통계 스키마
# ===========================================

class BlogStrategyStats(BaseModel):
    """블로그별 전략 통계"""
    blog_id: int
    blog_name: str
    blog_platform: str
    weight_percentage: float
    adjustment_type: WeightAdjustmentType
    status: StrategyStatus

    # 발행 통계
    total_posts_published: int = Field(0, description="총 발행 포스트 수")
    posts_published_today: int = Field(0, description="오늘 발행 포스트 수")
    posts_published_this_week: int = Field(0, description="이번 주 발행 포스트 수")
    posts_published_this_month: int = Field(0, description="이번 달 발행 포스트 수")

    # 성과 지표
    success_rate: float = Field(0.0, description="발행 성공률")
    average_interval_hours: float = Field(0.0, description="평균 발행 간격 (시간)")

    # 다음 예정
    next_publish_available_at: Optional[datetime] = None
    can_publish_now: bool = Field(False, description="현재 발행 가능 여부")


class StrategyStatsResponse(BaseModel):
    """전략 통계 응답"""
    user_id: int
    total_blogs: int = Field(0, description="총 블로그 수")
    active_strategies: int = Field(0, description="활성 전략 수")
    paused_strategies: int = Field(0, description="일시정지 전략 수")

    # 전체 통계
    total_weight_percentage: float = Field(0.0, description="총 비중 (검증용)")
    total_posts_published_today: int = Field(0, description="오늘 총 발행 포스트")
    total_posts_published_this_week: int = Field(0, description="이번 주 총 발행 포스트")

    # 블로그별 상세
    blog_strategies: List[BlogStrategyStats] = Field(
        default_factory=list,
        description="블로그별 전략 통계"
    )

    # 비중 분포
    weight_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="블로그별 비중 분포"
    )

    # 추천 사항
    recommendations: List[str] = Field(
        default_factory=list,
        description="비중 조절 추천사항"
    )


# ===========================================
# 비중 조절 스키마
# ===========================================

class WeightAdjustmentRequest(BaseModel):
    """비중 조절 요청"""
    blog_adjustments: List[Dict[str, Any]] = Field(
        ...,
        description="블로그별 비중 조절 설정",
        example=[
            {"blog_id": 1, "weight_percentage": 30.0},
            {"blog_id": 2, "weight_percentage": 70.0}
        ]
    )
    normalize: bool = Field(
        True,
        description="비중 정규화 여부 (총합 100%로 맞춤)"
    )

    @validator('blog_adjustments')
    def validate_adjustments(cls, v):
        """비중 조절 검증"""
        if not v:
            raise ValueError('최소 1개 이상의 블로그 비중을 설정해야 합니다')

        blog_ids = set()
        total_weight = 0.0

        for adjustment in v:
            if 'blog_id' not in adjustment or 'weight_percentage' not in adjustment:
                raise ValueError('blog_id와 weight_percentage는 필수입니다')

            blog_id = adjustment['blog_id']
            weight = adjustment['weight_percentage']

            if blog_id in blog_ids:
                raise ValueError(f'중복된 블로그 ID: {blog_id}')

            if not isinstance(weight, (int, float)) or weight < 0 or weight > 100:
                raise ValueError(f'비중은 0-100 사이여야 합니다: {weight}')

            blog_ids.add(blog_id)
            total_weight += weight

        # 정규화하지 않는 경우 총합 검증
        if not cls.__dict__.get('normalize', True) and abs(total_weight - 100.0) > 0.1:
            raise ValueError(f'총 비중은 100%여야 합니다: {total_weight}%')

        return v


class WeightAdjustmentResponse(BaseModel):
    """비중 조절 응답"""
    success: bool
    message: str
    adjusted_blogs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="조절된 블로그 목록"
    )
    total_weight_before: float = Field(0.0, description="조절 전 총 비중")
    total_weight_after: float = Field(0.0, description="조절 후 총 비중")
    warnings: List[str] = Field(
        default_factory=list,
        description="경고 메시지"
    )


# ===========================================
# 자동 조절 스키마
# ===========================================

class AutoAdjustmentResult(BaseModel):
    """자동 조절 결과"""
    performed: bool = Field(False, description="조절 수행 여부")
    reason: str = Field("", description="조절 이유")
    adjustments_made: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="수행된 조절 내역"
    )
    next_check_at: Optional[datetime] = Field(
        None,
        description="다음 확인 예정 시간"
    )


# ===========================================
# 에러 응답
# ===========================================

class ErrorResponse(BaseModel):
    """에러 응답"""
    message: str = Field(..., description="에러 메시지")
    detail: Optional[str] = Field(None, description="상세 에러 내용")
    error_code: Optional[str] = Field(None, description="에러 코드")