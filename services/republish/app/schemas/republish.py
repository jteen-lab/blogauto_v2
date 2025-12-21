"""
재발행 관련 스키마

Features:
- 재발행 실행 요청/응답 스키마
- 스케줄러 상태 모니터링 스키마
- 연결 테스트 스키마
- 발행 이력 스키마
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum


class PublishResult(str, Enum):
    """발행 결과"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


class SchedulerStatus(str, Enum):
    """스케줄러 상태"""
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"


class ConnectionTestResult(str, Enum):
    """연결 테스트 결과"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"


# ===========================================
# 연결 테스트 스키마
# ===========================================

class ConnectionTestRequest(BaseModel):
    """연결 테스트 요청"""
    blog_id: int = Field(..., description="블로그 ID", ge=1)


class ConnectionTestResponse(BaseModel):
    """연결 테스트 응답"""
    blog_id: int = Field(..., description="블로그 ID")
    blog_name: str = Field("", description="블로그 이름")
    result: ConnectionTestResult = Field(..., description="테스트 결과")
    success: bool = Field(..., description="성공 여부")
    message: str = Field("", description="결과 메시지")

    # 상세 정보
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (ms)")
    api_version: Optional[str] = Field(None, description="API 버전")
    platform_info: Optional[Dict[str, Any]] = Field(
        None,
        description="플랫폼 상세 정보"
    )
    error_details: Optional[str] = Field(None, description="에러 상세 내용")

    # 권한 확인 결과
    can_read_posts: bool = Field(False, description="포스트 읽기 권한")
    can_write_posts: bool = Field(False, description="포스트 쓰기 권한")
    can_upload_media: bool = Field(False, description="미디어 업로드 권한")

    tested_at: datetime = Field(default_factory=datetime.now, description="테스트 시간")


# ===========================================
# 수동 재발행 실행 스키마
# ===========================================

class ManualRepublishRequest(BaseModel):
    """수동 재발행 실행 요청"""
    profile_id: int = Field(..., description="프로파일 ID", ge=1)
    force_execute: bool = Field(
        False,
        description="강제 실행 여부 (대기시간 무시)"
    )
    specific_post_id: Optional[int] = Field(
        None,
        description="특정 포스트 ID (지정시 해당 포스트만 발행)"
    )
    dry_run: bool = Field(
        False,
        description="테스트 실행 여부 (실제 발행하지 않음)"
    )


class ManualRepublishResponse(BaseModel):
    """수동 재발행 실행 응답"""
    profile_id: int = Field(..., description="프로파일 ID")
    profile_name: str = Field("", description="프로파일 이름")

    # 실행 결과
    executed: bool = Field(..., description="실행 여부")
    result: PublishResult = Field(..., description="발행 결과")
    message: str = Field("", description="결과 메시지")

    # 발행 정보
    post_id: Optional[int] = Field(None, description="발행된 포스트 ID")
    post_title: Optional[str] = Field(None, description="발행된 포스트 제목")
    published_to_blogs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="발행된 블로그 목록"
    )

    # 대기 정보
    can_publish_immediately: bool = Field(True, description="즉시 발행 가능 여부")
    next_publish_available_at: Optional[datetime] = Field(
        None,
        description="다음 발행 가능 시간"
    )

    # 실행 메타 정보
    execution_time_ms: int = Field(0, description="실행 시간 (ms)")
    dry_run: bool = Field(False, description="테스트 실행 여부")
    executed_at: datetime = Field(default_factory=datetime.now, description="실행 시간")


# ===========================================
# 스케줄러 상태 스키마
# ===========================================

class SchedulerStatusResponse(BaseModel):
    """스케줄러 상태 응답"""
    status: SchedulerStatus = Field(..., description="스케줄러 상태")
    running: bool = Field(..., description="실행 중 여부")
    started_at: Optional[datetime] = Field(None, description="시작 시간")
    last_execution_at: Optional[datetime] = Field(None, description="마지막 실행 시간")
    next_execution_at: Optional[datetime] = Field(None, description="다음 실행 예정 시간")

    # 실행 통계
    total_executions: int = Field(0, description="총 실행 횟수")
    successful_executions: int = Field(0, description="성공한 실행 횟수")
    failed_executions: int = Field(0, description="실패한 실행 횟수")
    success_rate: float = Field(0.0, description="성공률 (%)")

    # 현재 작업 정보
    current_jobs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="현재 실행 중인 작업"
    )
    pending_jobs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="대기 중인 작업"
    )

    # 최근 활동
    recent_activities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="최근 활동 내역 (최대 10개)"
    )

    # 시스템 정보
    version: str = Field("1.0.0", description="스케줄러 버전")
    uptime_seconds: int = Field(0, description="가동 시간 (초)")
    memory_usage_mb: Optional[float] = Field(None, description="메모리 사용량 (MB)")


# ===========================================
# 발행 이력 스키마
# ===========================================

class PublishLogEntry(BaseModel):
    """발행 이력 엔트리"""
    id: int = Field(..., description="로그 ID")
    profile_id: Optional[int] = Field(None, description="프로파일 ID")
    profile_name: Optional[str] = Field(None, description="프로파일 이름")
    blog_id: int = Field(..., description="블로그 ID")
    blog_name: str = Field("", description="블로그 이름")
    post_id: int = Field(..., description="포스트 ID")
    post_title: str = Field("", description="포스트 제목")

    # 발행 정보
    result: PublishResult = Field(..., description="발행 결과")
    platform_post_id: Optional[str] = Field(None, description="플랫폼별 포스트 ID")
    published_url: Optional[str] = Field(None, description="발행된 포스트 URL")

    # 메타 정보
    execution_time_ms: int = Field(0, description="실행 시간 (ms)")
    error_message: Optional[str] = Field(None, description="에러 메시지")
    api_response: Optional[Dict[str, Any]] = Field(None, description="API 응답")

    # 시간 정보
    published_at: datetime = Field(..., description="발행 시간")

    class Config:
        from_attributes = True


class PublishHistoryRequest(BaseModel):
    """발행 이력 조회 요청"""
    profile_id: Optional[int] = Field(None, description="프로파일 ID 필터")
    blog_id: Optional[int] = Field(None, description="블로그 ID 필터")
    result: Optional[PublishResult] = Field(None, description="결과 필터")
    start_date: Optional[datetime] = Field(None, description="시작 날짜")
    end_date: Optional[datetime] = Field(None, description="종료 날짜")
    limit: int = Field(50, description="조회 개수", ge=1, le=200)
    offset: int = Field(0, description="오프셋", ge=0)


class PublishHistoryResponse(BaseModel):
    """발행 이력 조회 응답"""
    entries: List[PublishLogEntry] = Field(
        default_factory=list,
        description="발행 이력 목록"
    )
    total_count: int = Field(0, description="전체 개수")
    current_page: int = Field(1, description="현재 페이지")
    page_size: int = Field(50, description="페이지 크기")
    total_pages: int = Field(0, description="전체 페이지 수")

    # 통계 정보
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="요약 통계"
    )


# ===========================================
# 대시보드 스키마
# ===========================================

class RepublishDashboardResponse(BaseModel):
    """재발행 대시보드 응답"""
    # 스케줄러 상태
    scheduler_status: SchedulerStatusResponse

    # 오늘 통계
    today_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="오늘 발행 통계"
    )

    # 주간 통계
    weekly_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="주간 발행 통계"
    )

    # 활성 프로파일 현황
    active_profiles: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="활성 프로파일 현황"
    )

    # 최근 활동
    recent_publishes: List[PublishLogEntry] = Field(
        default_factory=list,
        description="최근 발행 이력 (최대 10개)"
    )

    # 알림 및 경고
    alerts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="시스템 알림 및 경고"
    )

    # 성과 지표
    performance_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="성과 지표"
    )


# ===========================================
# 에러 응답
# ===========================================

class ErrorResponse(BaseModel):
    """에러 응답"""
    message: str = Field(..., description="에러 메시지")
    detail: Optional[str] = Field(None, description="상세 에러 내용")
    error_code: Optional[str] = Field(None, description="에러 코드")
    timestamp: datetime = Field(default_factory=datetime.now, description="에러 발생 시간")