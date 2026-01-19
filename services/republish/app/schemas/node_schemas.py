"""
노드 간 데이터 전달을 위한 Pydantic 스키마

Features:
- 노드 입출력 타입 정의
- 데이터 검증 및 직렬화
- 공용/특화 노드 간 인터페이스 표준화
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ============================================
# 공통 Enum
# ============================================

class BlogPlatformType(str, Enum):
    """블로그 플랫폼 타입"""
    WORDPRESS = "wordpress"
    BLOGGER = "blogger"


class RepublishProfile(str, Enum):
    """재발행 프로파일 (누적 포스트 수 기반)"""
    SEEDLING = "seedling"      # 🌱 새싹: 1-100
    GROWTH = "growth"          # 🌿 성장: 101-200
    STABLE = "stable"          # 🌳 안정: 201-300
    MATURE = "mature"          # 🏛️ 성숙: 301-400
    UNLIMITED = "unlimited"    # ♾️ 무제한: 401+


class ExecutionStatus(str, Enum):
    """실행 상태"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


# ============================================
# 노드 1: 블로그 조회 (BlogFetcher)
# ============================================

class BlogFetcherInput(BaseModel):
    """노드 1 입력: 플로우 및 사용자 정보"""
    flow_id: int = Field(..., description="플로우 ID")
    user_id: int = Field(..., description="사용자 ID")
    module_id: Optional[int] = Field(None, description="모듈 ID (선택)")


class BlogInfo(BaseModel):
    """블로그 정보"""
    id: int = Field(..., description="블로그 ID")
    name: str = Field(..., description="블로그 이름")
    url: str = Field(..., description="블로그 URL")
    platform: BlogPlatformType = Field(..., description="플랫폼")
    post_count: int = Field(0, description="누적 포스트 수")
    last_publish_at: Optional[datetime] = Field(None, description="마지막 발행 시간")
    credential_id: Optional[int] = Field(None, description="인증 정보 ID (Blogger용)")


class BlogFetcherOutput(BaseModel):
    """노드 1 출력: 블로그 목록"""
    blogs: list[BlogInfo] = Field(default_factory=list, description="블로그 목록")
    total_count: int = Field(0, description="총 블로그 수")
    fetched_at: datetime = Field(default_factory=datetime.now, description="조회 시간")


# ============================================
# 노드 2: 상태 분류 (StatusClassifier)
# ============================================

class StatusClassifierInput(BaseModel):
    """노드 2 입력: 블로그 목록"""
    blogs: list[BlogInfo] = Field(..., description="블로그 목록")
    module_settings: Optional[dict[str, Any]] = Field(None, description="모듈 설정")


class ClassifiedBlog(BaseModel):
    """분류된 블로그 정보"""
    blog: BlogInfo = Field(..., description="블로그 정보")
    profile: RepublishProfile = Field(..., description="재발행 프로파일")
    interval_minutes: int = Field(..., description="권장 발행 간격 (분)")
    daily_target: int = Field(..., description="일일 목표 횟수")
    is_eligible: bool = Field(True, description="재발행 대상 여부")
    skip_reason: Optional[str] = Field(None, description="건너뛰기 사유")


class StatusClassifierOutput(BaseModel):
    """노드 2 출력: 분류된 블로그 목록"""
    classified_blogs: list[ClassifiedBlog] = Field(
        default_factory=list, description="분류된 블로그 목록"
    )
    profile_summary: dict[str, int] = Field(
        default_factory=dict, description="프로파일별 블로그 수"
    )


# ============================================
# 노드 3: 액션 스케줄러 (ActionScheduler)
# ============================================

class ActionSchedulerInput(BaseModel):
    """노드 3 입력: 분류된 블로그 목록"""
    classified_blogs: list[ClassifiedBlog] = Field(..., description="분류된 블로그 목록")
    schedule_matrix: Optional[list[list[bool]]] = Field(
        None, description="스케줄 매트릭스 (7일 x 24시간)"
    )
    current_time: datetime = Field(
        default_factory=datetime.now, description="현재 시간"
    )


class ExecutableBlog(BaseModel):
    """실행 대상 블로그"""
    blog: BlogInfo = Field(..., description="블로그 정보")
    profile: RepublishProfile = Field(..., description="재발행 프로파일")
    should_execute: bool = Field(..., description="실행 여부")
    skip_reason: Optional[str] = Field(None, description="건너뛰기 사유")
    next_execution_at: Optional[datetime] = Field(None, description="다음 실행 예정 시간")


class ActionSchedulerOutput(BaseModel):
    """노드 3 출력: 실행 대상 블로그 목록"""
    executable_blogs: list[ExecutableBlog] = Field(
        default_factory=list, description="실행 대상 블로그"
    )
    skipped_blogs: list[ExecutableBlog] = Field(
        default_factory=list, description="건너뛴 블로그"
    )
    is_active_time: bool = Field(..., description="현재 활성 시간대 여부")


# ============================================
# 노드 4: 발행 집행 (PublishExecutor)
# ============================================

class PublishExecutorInput(BaseModel):
    """노드 4 입력: 실행 대상 블로그"""
    blog: BlogInfo = Field(..., description="블로그 정보")
    profile: RepublishProfile = Field(..., description="재발행 프로파일")


class PublishResult(BaseModel):
    """발행 결과"""
    blog_id: int = Field(..., description="블로그 ID")
    blog_name: str = Field(..., description="블로그 이름")
    status: ExecutionStatus = Field(..., description="실행 상태")
    post_id: Optional[str] = Field(None, description="발행된 포스트 ID")
    post_title: Optional[str] = Field(None, description="발행된 포스트 제목")
    post_url: Optional[str] = Field(None, description="발행된 포스트 URL")
    old_date: Optional[str] = Field(None, description="이전 발행일")
    new_date: Optional[str] = Field(None, description="새 발행일")
    error_message: Optional[str] = Field(None, description="오류 메시지")
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (ms)")
    executed_at: datetime = Field(default_factory=datetime.now, description="실행 시간")


class PublishExecutorOutput(BaseModel):
    """노드 4 출력: 발행 결과"""
    result: PublishResult = Field(..., description="발행 결과")


# ============================================
# 노드 5: 상태 기록 (StatusLogger)
# ============================================

class StatusLoggerInput(BaseModel):
    """노드 5 입력: 발행 결과"""
    result: PublishResult = Field(..., description="발행 결과")
    flow_id: int = Field(..., description="플로우 ID")
    user_id: int = Field(..., description="사용자 ID")
    module_id: Optional[int] = Field(None, description="모듈 ID")


class LogEntry(BaseModel):
    """로그 엔트리"""
    id: Optional[int] = Field(None, description="로그 ID")
    flow_id: int = Field(..., description="플로우 ID")
    blog_id: int = Field(..., description="블로그 ID")
    action: str = Field(..., description="액션 타입")
    status: ExecutionStatus = Field(..., description="실행 상태")
    message: Optional[str] = Field(None, description="메시지")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")


class StatusLoggerOutput(BaseModel):
    """노드 5 출력: 실행 요약"""
    log_entry: LogEntry = Field(..., description="생성된 로그")
    blog_updated: bool = Field(..., description="블로그 상태 업데이트 여부")
    url_saved: bool = Field(..., description="URL 저장 여부")


# ============================================
# 오케스트레이터용 전체 실행 결과
# ============================================

class RepublishExecutionSummary(BaseModel):
    """재발행 전체 실행 요약"""
    flow_id: int = Field(..., description="플로우 ID")
    executed_at: datetime = Field(default_factory=datetime.now, description="실행 시간")
    total_blogs: int = Field(0, description="총 블로그 수")
    executed_count: int = Field(0, description="실행된 블로그 수")
    success_count: int = Field(0, description="성공 수")
    failed_count: int = Field(0, description="실패 수")
    skipped_count: int = Field(0, description="건너뛴 수")
    results: list[PublishResult] = Field(default_factory=list, description="개별 결과")
    execution_time_ms: int = Field(0, description="총 실행 시간 (ms)")
