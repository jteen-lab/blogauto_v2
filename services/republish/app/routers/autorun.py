"""
오토런 라우터

Features:
- 플로우 실행 상태 제어
- 전체 오토런 모니터링
- 실행 이력 조회
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..models import User
from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..services.autorun_service import AutorunService
from ..services.scheduler_manager import scheduler_manager
from ..schemas.autorun import (
    AutorunFlowListResponse,
    AutorunStatusSummary,
    FlowActionRequest,
    FlowActionResult,
    BulkFlowActionRequest,
    BulkFlowActionResult,
    ExecutionHistoryResponse,
    SystemHealthCheck,
    AutorunScheduleResponse
)
from ..schemas.flow import FlowStatus, FlowExecutionInfo
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("autorun_router", "app.log")

router = APIRouter(prefix="/autorun", tags=["autorun"])


@router.get(
    "",
    response_model=AutorunFlowListResponse,
    summary="오토런 플로우 목록",
    description="상태별로 분류된 플로우 목록과 실행 정보를 조회합니다."
)
async def get_autorun_flows(
    include_inactive: bool = Query(True, description="비활성 플로우 포함 여부"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AutorunFlowListResponse:
    """오토런 플로우 목록 조회"""
    service = AutorunService(db)
    return await service.get_autorun_status(current_user, include_inactive)


@router.get(
    "/available",
    summary="오토런 미추가 플로우 목록",
    description="오토런에 추가되지 않은 플로우 목록을 조회합니다."
)
async def get_available_flows(
    search: Optional[str] = Query(None, description="검색어 (플로우명, 모듈명, 블로그명)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """오토런 미추가 플로우 목록 조회"""
    service = AutorunService(db)
    return await service.get_available_flows(current_user, search)


@router.post(
    "/flows",
    summary="플로우 다중 추가",
    description="여러 플로우를 오토런에 추가합니다."
)
async def add_flows_to_autorun(
    flow_ids: List[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우 다중 추가"""
    service = AutorunService(db)
    result = await service.add_flows_to_autorun(current_user, flow_ids)

    # 성공한 플로우들을 스케줄러에 등록
    if result.get("success"):
        added_ids = result.get("added_flow_ids", [])
        for flow_id in added_ids:
            try:
                await scheduler_manager.register_flow_schedule(flow_id)
            except Exception as e:
                # 스케줄러 등록 실패해도 오토런 추가는 유지
                pass

    return result


@router.delete(
    "/flows/{flow_id}",
    summary="플로우 제외",
    description="플로우를 오토런에서 제외합니다."
)
async def remove_flow_from_autorun(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우 제외"""
    service = AutorunService(db)
    result = await service.remove_flow_from_autorun(current_user, flow_id)

    # 성공 시 스케줄러에서 제거
    if result.get("success"):
        await scheduler_manager.unregister_flow_schedule(flow_id)

    return result


@router.post(
    "/flows/{flow_id}/start",
    response_model=FlowActionResult,
    summary="플로우 시작",
    description="플로우를 활성 상태로 변경하여 실행을 시작합니다."
)
async def start_flow(
    flow_id: int,
    request: FlowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowActionResult:
    """플로우 시작"""
    service = AutorunService(db)
    result = await service.execute_flow_action(current_user, flow_id, request)

    # 성공 시 스케줄러에 등록
    if result.success and result.current_status == FlowStatus.ACTIVE:
        await scheduler_manager.register_flow_schedule(flow_id)

    return result


@router.post(
    "/flows/{flow_id}/pause",
    response_model=FlowActionResult,
    summary="플로우 일시정지",
    description="활성 플로우를 일시정지 상태로 변경합니다."
)
async def pause_flow(
    flow_id: int,
    request: FlowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowActionResult:
    """플로우 일시정지"""
    service = AutorunService(db)
    result = await service.execute_flow_action(current_user, flow_id, request)

    # 성공 시 스케줄러에서 제거
    if result.success and result.current_status == FlowStatus.PAUSED:
        await scheduler_manager.unregister_flow_schedule(flow_id)

    return result


@router.post(
    "/flows/{flow_id}/resume",
    response_model=FlowActionResult,
    summary="플로우 재개",
    description="일시정지된 플로우를 다시 활성화합니다."
)
async def resume_flow(
    flow_id: int,
    request: FlowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowActionResult:
    """플로우 재개"""
    service = AutorunService(db)
    result = await service.execute_flow_action(current_user, flow_id, request)

    # 성공 시 스케줄러에 등록
    if result.success and result.current_status == FlowStatus.ACTIVE:
        await scheduler_manager.register_flow_schedule(flow_id)

    return result


@router.post(
    "/flows/{flow_id}/stop",
    response_model=FlowActionResult,
    summary="플로우 중지",
    description="플로우를 비활성 상태로 변경하여 실행을 중지합니다."
)
async def stop_flow(
    flow_id: int,
    request: FlowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowActionResult:
    """플로우 중지"""
    service = AutorunService(db)
    result = await service.execute_flow_action(current_user, flow_id, request)

    # 성공 시 스케줄러에서 제거
    if result.success and result.current_status == FlowStatus.INACTIVE:
        await scheduler_manager.unregister_flow_schedule(flow_id)

    return result


@router.post(
    "/bulk-action",
    response_model=BulkFlowActionResult,
    summary="다중 플로우 액션",
    description="여러 플로우에 대해 동일한 액션을 일괄 실행합니다."
)
async def bulk_flow_action(
    request: BulkFlowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> BulkFlowActionResult:
    """다중 플로우 액션"""
    service = AutorunService(db)
    result = await service.execute_bulk_flow_action(current_user, request)

    # 스케줄러 연동 처리
    for flow_result in result.results:
        if flow_result.success:
            if flow_result.current_status == FlowStatus.ACTIVE:
                await scheduler_manager.register_flow_schedule(flow_result.flow_id)
            else:
                await scheduler_manager.unregister_flow_schedule(flow_result.flow_id)

    return result


@router.get(
    "/status",
    response_model=AutorunStatusSummary,
    summary="전체 실행 상태 요약",
    description="오토런 시스템의 전체 실행 상태를 요약하여 조회합니다."
)
async def get_autorun_status_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AutorunStatusSummary:
    """전체 실행 상태 요약"""
    service = AutorunService(db)
    response = await service.get_autorun_status(current_user, include_inactive=True)
    return response.summary


@router.get(
    "/health",
    response_model=SystemHealthCheck,
    summary="시스템 건강 상태",
    description="오토런 시스템의 건강 상태를 체크합니다."
)
async def get_system_health(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> SystemHealthCheck:
    """시스템 건강 상태 체크"""
    try:
        logger.info(f"[HEALTH_CHECK] 시스템 건강 상태 체크")

        # 활성 플로우 수 조회
        active_count_query = select(func.count(Flow.id)).where(
            and_(Flow.user_id == current_user.id, Flow.status == 'active')
        )
        active_count_result = await db.execute(active_count_query)
        active_flows_count = active_count_result.scalar()

        # 스케줄러 상태 조회
        scheduler_status = scheduler_manager.get_scheduler_status()

        health = SystemHealthCheck(
            status="healthy",
            timestamp=datetime.now(),
            cpu_usage_percent=25.5,  # TODO: psutil로 실제 조회
            memory_usage_percent=45.2,  # TODO: psutil로 실제 조회
            disk_usage_percent=32.1,  # TODO: psutil로 실제 조회
            database_status="connected",
            redis_status="connected",
            active_flows_count=active_flows_count,
            last_execution=None,
            failed_executions_last_hour=0,
            warnings=[],
            errors=[]
        )

        # 스케줄러 상태 체크
        if not scheduler_status["is_running"]:
            health.errors.append("스케줄러가 실행 중이지 않습니다")
            health.status = "error"

        # 경고 조건 체크
        if active_flows_count > 20:
            health.warnings.append(f"활성 플로우가 많습니다: {active_flows_count}개")

        if health.warnings and health.status == "healthy":
            health.status = "warning"

        logger.info(f"[HEALTH_CHECK] 상태: {health.status}")
        return health

    except Exception as e:
        logger.error(f"[HEALTH_CHECK] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="시스템 건강 상태를 확인하는 중 오류가 발생했습니다"
        )


@router.get(
    "/scheduler/status",
    summary="스케줄러 상태 조회",
    description="APScheduler 스케줄러의 상태와 작업 목록을 조회합니다."
)
async def get_scheduler_status():
    """스케줄러 상태 조회"""
    return scheduler_manager.get_scheduler_status()


@router.post(
    "/scheduler/start",
    summary="스케줄러 시작",
    description="APScheduler 스케줄러를 시작합니다."
)
async def start_scheduler():
    """스케줄러 시작"""
    success = await scheduler_manager.start()
    if success:
        return {"success": True, "message": "스케줄러가 시작되었습니다"}
    else:
        raise HTTPException(
            status_code=500,
            detail="스케줄러 시작에 실패했습니다"
        )


@router.post(
    "/scheduler/stop",
    summary="스케줄러 중지",
    description="APScheduler 스케줄러를 중지합니다."
)
async def stop_scheduler():
    """스케줄러 중지"""
    success = await scheduler_manager.stop()
    if success:
        return {"success": True, "message": "스케줄러가 중지되었습니다"}
    else:
        raise HTTPException(
            status_code=500,
            detail="스케줄러 중지에 실패했습니다"
        )


# ===========================================
# 로그 관련 엔드포인트
# ===========================================

@router.get(
    "/logs",
    summary="오토런 로그 조회",
    description="오토런 실행 로그를 조회합니다."
)
async def get_autorun_logs(
    flow_id: Optional[int] = Query(None, description="특정 플로우 ID로 필터링"),
    action: Optional[str] = Query(None, description="액션 타입 필터 (started/completed/failed/paused/resumed)"),
    limit: int = Query(50, ge=1, le=200, description="조회 개수"),
    offset: int = Query(0, ge=0, description="시작 위치"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """오토런 로그 조회"""
    service = AutorunService(db)
    return await service.get_autorun_logs(
        user=current_user,
        flow_id=flow_id,
        action=action,
        limit=limit,
        offset=offset
    )


