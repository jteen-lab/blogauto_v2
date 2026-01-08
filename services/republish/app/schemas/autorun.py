"""
오토런 관련 스키마

Features:
- 플로우 실행 상태 관리
- 전체 오토런 상태 요약
- 실행 제어 요청/응답
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

from .flow import FlowStatus, FlowExecutionInfo


class AutorunAction(str, Enum):
    """오토런 액션"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


class AutorunStatusSummary(BaseModel):
    """오토런 상태 요약"""
    total_flows: int
    active_flows: int
    paused_flows: int
    inactive_flows: int

    # 실행 통계
    total_executions_today: int = 0
    successful_executions_today: int = 0
    failed_executions_today: int = 0

    # 다음 실행 예정
    next_execution: Optional[datetime] = None
    next_execution_flow_name: Optional[str] = None


class AutorunFlowListResponse(BaseModel):
    """오토런 플로우 목록 응답"""
    active_flows: List[FlowExecutionInfo] = Field(default_factory=list)
    paused_flows: List[FlowExecutionInfo] = Field(default_factory=list)
    inactive_flows: List[FlowExecutionInfo] = Field(default_factory=list)

    summary: AutorunStatusSummary


class FlowActionRequest(BaseModel):
    """플로우 액션 요청"""
    action: AutorunAction = Field(..., description="실행할 액션")
    reason: Optional[str] = Field(None, max_length=200, description="액션 이유")

    # 스케줄 관련 (start 액션 시)
    immediate: bool = Field(False, description="즉시 실행 여부")

    # 일시정지 관련 (pause 액션 시)
    pause_duration_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="일시정지 시간(분)"
    )


class FlowActionResult(BaseModel):
    """플로우 액션 결과"""
    success: bool
    message: str
    flow_id: Optional[int] = None
    previous_status: Optional[FlowStatus] = None
    current_status: FlowStatus

    # 액션별 추가 정보
    next_execution: Optional[datetime] = None
    paused_until: Optional[datetime] = None

    # 오류 정보
    error_code: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


class ExecutionHistoryItem(BaseModel):
    """실행 이력 항목"""
    id: int
    flow_id: int
    flow_name: str
    module_id: int
    module_name: str
    blog_id: int
    blog_name: str

    # 실행 정보
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str  # 'running', 'success', 'failed', 'skipped'

    # 결과 정보
    posts_processed: int = 0
    posts_published: int = 0
    error_message: Optional[str] = None

    # 실행 시간
    duration_seconds: Optional[float] = None


class ExecutionHistoryResponse(BaseModel):
    """실행 이력 응답"""
    executions: List[ExecutionHistoryItem]
    total: int
    page: int
    size: int
    has_next: bool

    # 통계
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_duration_seconds: Optional[float] = None


class SystemHealthCheck(BaseModel):
    """시스템 건강 상태 체크"""
    status: str  # 'healthy', 'warning', 'error'
    timestamp: datetime

    # 시스템 리소스
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float

    # 서비스 상태
    database_status: str
    redis_status: Optional[str] = None

    # 오토런 상태
    active_flows_count: int
    last_execution: Optional[datetime] = None
    failed_executions_last_hour: int = 0

    # 경고/오류
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class FlowScheduleInfo(BaseModel):
    """플로우 스케줄 정보"""
    flow_id: int
    flow_name: str
    status: FlowStatus

    # 다음 실행 시간들
    next_executions: List[datetime] = Field(default_factory=list)

    # 모듈별 스케줄
    module_schedules: List[Dict[str, Any]] = Field(default_factory=list)

    # 블로그별 슬롯 정보
    blog_slots: List[Dict[str, Any]] = Field(default_factory=list)


class AutorunScheduleResponse(BaseModel):
    """오토런 스케줄 전체 응답"""
    schedules: List[FlowScheduleInfo] = Field(default_factory=list)

    # 오늘 예정된 총 실행 수
    today_scheduled_count: int = 0

    # 다음 24시간 예정
    next_24h_count: int = 0

    # 시간대별 실행 분포
    hourly_distribution: Dict[str, int] = Field(default_factory=dict)


class BulkFlowActionRequest(BaseModel):
    """다중 플로우 액션 요청"""
    flow_ids: List[int] = Field(..., min_items=1, max_items=50)
    action: AutorunAction = Field(..., description="실행할 액션")
    reason: Optional[str] = Field(None, max_length=200)


class BulkFlowActionResult(BaseModel):
    """다중 플로우 액션 결과"""
    total_requested: int
    successful_count: int
    failed_count: int

    # 개별 결과
    results: List[FlowActionResult] = Field(default_factory=list)

    # 요약 메시지
    summary_message: str