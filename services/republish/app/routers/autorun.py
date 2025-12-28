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

router = APIRouter(prefix="/api/v1/autorun", tags=["autorun"])


@router.get(
    "",
    response_model=AutorunFlowListResponse,
    summary="오토런 플로우 목록",
    description="상태별로 분류된 플로우 목록과 실행 정보를 조회합니다."
)
async def get_autorun_flows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AutorunFlowListResponse:
    """오토런 플로우 목록 조회"""
    try:
        logger.info(f"[GET_AUTORUN] 사용자 {current_user.id} 오토런 목록 조회")

        # 플로우 목록 조회 (관계 포함)
        query = (
            select(Flow)
            .options(
                selectinload(Flow.module_links),
                selectinload(Flow.blog_links)
            )
            .where(Flow.user_id == current_user.id)
            .order_by(Flow.updated_at.desc())
        )
        result = await db.execute(query)
        flows = result.scalars().all()

        # 상태별 분류
        active_flows = []
        paused_flows = []
        inactive_flows = []

        total_flows = len(flows)
        active_count = 0
        paused_count = 0

        for flow in flows:
            execution_info = FlowExecutionInfo(
                id=flow.id,
                name=flow.name,
                status=FlowStatus(flow.status),
                module_count=len(flow.module_links) if flow.module_links else 0,
                blog_count=len(flow.blog_links) if flow.blog_links else 0,
                # TODO: 실제 실행 정보는 스케줄러에서 계산
                next_execution=None,
                last_execution=None,
                execution_count=0,
                success_rate=0.0
            )

            if flow.status == "active":
                active_flows.append(execution_info)
                active_count += 1
            elif flow.status == "paused":
                paused_flows.append(execution_info)
                paused_count += 1
            else:  # inactive
                inactive_flows.append(execution_info)

        # 요약 정보
        summary = AutorunStatusSummary(
            total_flows=total_flows,
            active_flows=active_count,
            paused_flows=paused_count,
            inactive_flows=total_flows - active_count - paused_count,
            # TODO: 실제 실행 통계는 실행 로그에서 계산
            total_executions_today=0,
            successful_executions_today=0,
            failed_executions_today=0,
            next_execution=None,
            next_execution_flow_name=None
        )

        logger.info(
            f"[GET_AUTORUN] 플로우 분류 완료: "
            f"활성={active_count}, 일시정지={paused_count}, "
            f"비활성={len(inactive_flows)}"
        )

        return AutorunFlowListResponse(
            active_flows=active_flows,
            paused_flows=paused_flows,
            inactive_flows=inactive_flows,
            summary=summary
        )

    except Exception as e:
        logger.error(f"[GET_AUTORUN] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="오토런 목록을 조회하는 중 오류가 발생했습니다"
        )


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
    return await _execute_flow_action(
        flow_id, "start", "active", request, current_user, db
    )


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
    return await _execute_flow_action(
        flow_id, "pause", "paused", request, current_user, db
    )


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
    return await _execute_flow_action(
        flow_id, "resume", "active", request, current_user, db
    )


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
    return await _execute_flow_action(
        flow_id, "stop", "inactive", request, current_user, db
    )


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
    try:
        logger.info(
            f"[BULK_ACTION] 사용자 {current_user.id} "
            f"{len(request.flow_ids)}개 플로우에 {request.action} 실행"
        )

        # 액션에 따른 목표 상태 결정
        action_to_status = {
            "start": "active",
            "resume": "active",
            "pause": "paused",
            "stop": "inactive"
        }

        target_status = action_to_status.get(request.action.value)
        if not target_status:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 액션: {request.action}"
            )

        results = []
        successful_count = 0
        failed_count = 0

        for flow_id in request.flow_ids:
            try:
                action_request = FlowActionRequest(
                    action=request.action,
                    reason=request.reason
                )

                result = await _execute_flow_action(
                    flow_id, request.action.value, target_status,
                    action_request, current_user, db
                )

                results.append(result)
                if result.success:
                    successful_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1
                results.append(FlowActionResult(
                    success=False,
                    message=f"플로우 {flow_id} 액션 실패: {str(e)}",
                    flow_id=flow_id,
                    previous_status=FlowStatus.INACTIVE,
                    current_status=FlowStatus.INACTIVE,
                    error_code="BULK_ACTION_ERROR"
                ))

        summary_message = (
            f"총 {len(request.flow_ids)}개 플로우 중 "
            f"{successful_count}개 성공, {failed_count}개 실패"
        )

        logger.info(f"[BULK_ACTION] 완료: {summary_message}")

        return BulkFlowActionResult(
            total_requested=len(request.flow_ids),
            successful_count=successful_count,
            failed_count=failed_count,
            results=results,
            summary_message=summary_message
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BULK_ACTION] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="다중 플로우 액션을 실행하는 중 오류가 발생했습니다"
        )


@router.get(
    "/status",
    response_model=AutorunStatusSummary,
    summary="전체 실행 상태 요약",
    description="오토런 시스템의 전체 실행 상태를 요약하여 조회합니다."
)
async def get_autorun_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AutorunStatusSummary:
    """전체 실행 상태 요약"""
    try:
        logger.info(f"[GET_STATUS] 사용자 {current_user.id} 오토런 상태 요약 조회")

        # 플로우 상태별 집계
        status_query = (
            select(
                Flow.status,
                func.count(Flow.id).label('count')
            )
            .where(Flow.user_id == current_user.id)
            .group_by(Flow.status)
        )
        status_result = await db.execute(status_query)
        status_counts = {row.status: row.count for row in status_result}

        total_flows = sum(status_counts.values())
        active_flows = status_counts.get('active', 0)
        paused_flows = status_counts.get('paused', 0)
        inactive_flows = status_counts.get('inactive', 0)

        # TODO: 실제 실행 통계는 실행 로그 테이블에서 조회
        # 현재는 더미 데이터
        today = datetime.now().date()

        logger.info(
            f"[GET_STATUS] 상태 요약: 총={total_flows}, "
            f"활성={active_flows}, 일시정지={paused_flows}, 비활성={inactive_flows}"
        )

        return AutorunStatusSummary(
            total_flows=total_flows,
            active_flows=active_flows,
            paused_flows=paused_flows,
            inactive_flows=inactive_flows,
            total_executions_today=0,
            successful_executions_today=0,
            failed_executions_today=0,
            next_execution=None,
            next_execution_flow_name=None
        )

    except Exception as e:
        logger.error(f"[GET_STATUS] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="오토런 상태를 조회하는 중 오류가 발생했습니다"
        )


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

        # TODO: 실제 시스템 리소스는 psutil 등으로 조회
        # 현재는 더미 데이터
        health = SystemHealthCheck(
            status="healthy",
            timestamp=datetime.now(),
            cpu_usage_percent=25.5,
            memory_usage_percent=45.2,
            disk_usage_percent=32.1,
            database_status="connected",
            redis_status="connected",
            active_flows_count=active_flows_count,
            last_execution=None,
            failed_executions_last_hour=0,
            warnings=[],
            errors=[]
        )

        # 경고 조건 체크
        if active_flows_count > 20:
            health.warnings.append(f"활성 플로우가 많습니다: {active_flows_count}개")

        if health.warnings:
            health.status = "warning"

        logger.info(f"[HEALTH_CHECK] 상태: {health.status}")

        return health

    except Exception as e:
        logger.error(f"[HEALTH_CHECK] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="시스템 건강 상태를 확인하는 중 오류가 발생했습니다"
        )


async def _execute_flow_action(
    flow_id: int,
    action: str,
    target_status: str,
    request: FlowActionRequest,
    current_user: User,
    db: AsyncSession
) -> FlowActionResult:
    """플로우 액션 실행 헬퍼"""
    try:
        logger.info(
            f"[FLOW_ACTION] 사용자 {current_user.id} 플로우 {flow_id} "
            f"액션: {action} → {target_status}"
        )

        # 플로우 조회 (소유권 확인)
        query = select(Flow).where(
            and_(Flow.id == flow_id, Flow.user_id == current_user.id)
        )
        result = await db.execute(query)
        flow = result.scalar_one_or_none()

        if not flow:
            raise HTTPException(
                status_code=404,
                detail="플로우를 찾을 수 없습니다"
            )

        previous_status = FlowStatus(flow.status)

        # 상태 변경 유효성 검사
        if not _is_valid_status_transition(flow.status, target_status):
            raise HTTPException(
                status_code=400,
                detail=f"'{flow.status}'에서 '{target_status}'로 변경할 수 없습니다"
            )

        # 모듈과 블로그가 있는지 확인 (start/resume 액션 시)
        if target_status == "active":
            if not flow.module_links:
                raise HTTPException(
                    status_code=400,
                    detail="실행할 모듈이 없습니다. 먼저 모듈을 추가해주세요."
                )
            if not flow.blog_links:
                raise HTTPException(
                    status_code=400,
                    detail="대상 블로그가 없습니다. 먼저 블로그를 추가해주세요."
                )

        # 상태 변경
        flow.status = target_status
        await db.commit()

        # TODO: 실제 스케줄러 연동
        # - 활성화 시: 스케줄 등록
        # - 비활성화 시: 스케줄 제거
        # - 일시정지 시: 스케줄 일시정지

        next_execution = None
        if target_status == "active":
            # TODO: 다음 실행 시간 계산
            next_execution = datetime.now() + timedelta(minutes=30)

        message = f"플로우가 {_get_status_message(target_status)}되었습니다"
        if request.reason:
            message += f" (사유: {request.reason})"

        logger.info(f"[FLOW_ACTION] 완료: {flow_id} {previous_status} → {target_status}")

        return FlowActionResult(
            success=True,
            message=message,
            flow_id=flow_id,
            previous_status=previous_status,
            current_status=FlowStatus(target_status),
            next_execution=next_execution
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW_ACTION] 오류: {e}")
        return FlowActionResult(
            success=False,
            message=f"액션 실행 중 오류가 발생했습니다: {str(e)}",
            flow_id=flow_id,
            previous_status=FlowStatus.INACTIVE,
            current_status=FlowStatus.INACTIVE,
            error_code="ACTION_EXECUTION_ERROR",
            error_details={"exception": str(e)}
        )


def _is_valid_status_transition(current: str, target: str) -> bool:
    """상태 전환 유효성 검사"""
    valid_transitions = {
        "inactive": ["active"],
        "active": ["paused", "inactive"],
        "paused": ["active", "inactive"]
    }
    return target in valid_transitions.get(current, [])


def _get_status_message(status: str) -> str:
    """상태별 메시지"""
    messages = {
        "active": "시작",
        "paused": "일시정지",
        "inactive": "중지"
    }
    return messages.get(status, status)