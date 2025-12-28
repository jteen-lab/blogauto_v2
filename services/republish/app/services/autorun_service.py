"""
오토런 서비스

Features:
- 플로우 상태 관리 (start/pause/resume/stop)
- 실행 이력 관리
- 시스템 상태 모니터링
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update, desc, text
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..models.module import Module
from ..models.blog import Blog
from ..models.user import User
from ..schemas.flow import FlowStatus
from ..schemas.autorun import (
    AutorunFlowListResponse,
    AutorunStatusSummary,
    FlowActionRequest,
    FlowActionResult,
    AutorunAction,
    ExecutionHistoryResponse,
    FlowScheduleInfo,
    AutorunScheduleResponse,
    BulkFlowActionRequest,
    BulkFlowActionResult,
    SystemHealthCheck
)
from ..core.logger import get_logger

logger = get_logger("autorun_service", "app.log")


class AutorunService:
    """오토런 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===========================================
    # 오토런 상태 조회
    # ===========================================

    async def get_autorun_status(
        self,
        user: User,
        include_inactive: bool = True
    ) -> AutorunFlowListResponse:
        """전체 오토런 상태 조회"""
        try:
            logger.info(f"[GET_AUTORUN_STATUS] 사용자 {user.id} 오토런 상태 조회")

            # 플로우 목록 조회
            query = (
                select(Flow)
                .options(
                    selectinload(Flow.flow_modules).selectinload(FlowModule.module),
                    selectinload(Flow.flow_blogs).selectinload(FlowBlog.blog)
                )
                .where(Flow.user_id == user.id)
            )

            if not include_inactive:
                query = query.where(Flow.status != FlowStatus.INACTIVE)

            query = query.order_by(Flow.priority.desc(), Flow.updated_at.desc())
            result = await self.db.execute(query)
            flows = result.scalars().all()

            # 상태별 분류
            active_flows = [f for f in flows if f.status == FlowStatus.ACTIVE]
            paused_flows = [f for f in flows if f.status == FlowStatus.PAUSED]
            inactive_flows = [f for f in flows if f.status == FlowStatus.INACTIVE]

            # 요약 정보 생성
            summary = await self._build_status_summary(user.id, flows)

            logger.info(f"[GET_AUTORUN_STATUS] 총 {len(flows)}개 플로우 (활성: {len(active_flows)}, 일시정지: {len(paused_flows)}, 비활성: {len(inactive_flows)})")

            return AutorunFlowListResponse(
                active_flows=[self._flow_to_execution_info(f) for f in active_flows],
                paused_flows=[self._flow_to_execution_info(f) for f in paused_flows],
                inactive_flows=[self._flow_to_execution_info(f) for f in inactive_flows],
                summary=summary
            )

        except Exception as e:
            logger.error(f"[GET_AUTORUN_STATUS] 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="오토런 상태를 조회하는 중 오류가 발생했습니다"
            )

    async def _build_status_summary(self, user_id: int, flows: List[Flow]) -> AutorunStatusSummary:
        """상태 요약 생성"""
        # 기본 통계
        total_flows = len(flows)
        active_flows = len([f for f in flows if f.status == FlowStatus.ACTIVE])
        paused_flows = len([f for f in flows if f.status == FlowStatus.PAUSED])
        inactive_flows = len([f for f in flows if f.status == FlowStatus.INACTIVE])

        # 오늘의 실행 통계 (임시로 0으로 설정, 실제로는 execution_log 테이블에서 조회)
        today = datetime.now().date()
        total_executions_today = 0
        successful_executions_today = 0
        failed_executions_today = 0

        # 다음 실행 예정 (활성 플로우 중 첫 번째)
        next_execution = None
        next_execution_flow_name = None

        if active_flows > 0:
            active_flow_objs = [f for f in flows if f.status == FlowStatus.ACTIVE]
            if active_flow_objs:
                # 가장 높은 우선순위의 활성 플로우
                next_flow = max(active_flow_objs, key=lambda x: x.priority)
                next_execution_flow_name = next_flow.name
                # 임시로 현재 시간 + 1시간 설정 (실제로는 스케줄러에서 계산)
                next_execution = datetime.now() + timedelta(hours=1)

        return AutorunStatusSummary(
            total_flows=total_flows,
            active_flows=active_flows,
            paused_flows=paused_flows,
            inactive_flows=inactive_flows,
            total_executions_today=total_executions_today,
            successful_executions_today=successful_executions_today,
            failed_executions_today=failed_executions_today,
            next_execution=next_execution,
            next_execution_flow_name=next_execution_flow_name
        )

    def _flow_to_execution_info(self, flow: Flow) -> Dict[str, Any]:
        """Flow를 FlowExecutionInfo 형태로 변환"""
        return {
            "id": flow.id,
            "name": flow.name,
            "status": flow.status,
            "module_count": len(flow.flow_modules) if flow.flow_modules else 0,
            "blog_count": len(flow.flow_blogs) if flow.flow_blogs else 0,
            "next_execution": None,  # 스케줄러에서 계산
            "last_execution": None,  # execution_log에서 조회
            "paused_at": None,  # 일시정지 시간
            "execution_count": 0,  # execution_log에서 계산
            "success_rate": 0.0  # execution_log에서 계산
        }

    # ===========================================
    # 플로우 상태 제어
    # ===========================================

    async def execute_flow_action(
        self,
        user: User,
        flow_id: int,
        request: FlowActionRequest
    ) -> FlowActionResult:
        """플로우 액션 실행 (start/pause/resume/stop)"""
        try:
            logger.info(f"[FLOW_ACTION] 사용자 {user.id} 플로우 {flow_id} 액션: {request.action}")

            # 플로우 조회
            flow = await self._get_flow_with_validation(user, flow_id)
            if not flow:
                raise HTTPException(
                    status_code=404,
                    detail="플로우를 찾을 수 없습니다"
                )

            previous_status = flow.status

            # 액션별 처리
            if request.action == AutorunAction.START:
                result = await self._start_flow(flow, request)
            elif request.action == AutorunAction.PAUSE:
                result = await self._pause_flow(flow, request)
            elif request.action == AutorunAction.RESUME:
                result = await self._resume_flow(flow, request)
            elif request.action == AutorunAction.STOP:
                result = await self._stop_flow(flow, request)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"지원하지 않는 액션입니다: {request.action}"
                )

            # 결과에 기본 정보 추가
            result.flow_id = flow.id
            result.previous_status = previous_status

            await self.db.commit()

            logger.info(f"[FLOW_ACTION] 플로우 {flow_id} 상태 변경 완료: {previous_status} → {result.current_status}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[FLOW_ACTION] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우 액션을 실행하는 중 오류가 발생했습니다"
            )

    async def _get_flow_with_validation(self, user: User, flow_id: int) -> Optional[Flow]:
        """플로우 조회 및 소유권 검증"""
        query = (
            select(Flow)
            .options(
                selectinload(Flow.flow_modules).selectinload(FlowModule.module),
                selectinload(Flow.flow_blogs).selectinload(FlowBlog.blog)
            )
            .where(
                and_(
                    Flow.id == flow_id,
                    Flow.user_id == user.id
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _start_flow(self, flow: Flow, request: FlowActionRequest) -> FlowActionResult:
        """플로우 시작"""
        # 상태 검증
        if flow.status == FlowStatus.ACTIVE:
            return FlowActionResult(
                success=False,
                message="이미 실행 중인 플로우입니다",
                current_status=flow.status,
                error_code="ALREADY_ACTIVE"
            )

        # 플로우 구성 검증
        validation_result = await self._validate_flow_for_execution(flow)
        if not validation_result["is_valid"]:
            return FlowActionResult(
                success=False,
                message=f"플로우를 시작할 수 없습니다: {', '.join(validation_result['errors'])}",
                current_status=flow.status,
                error_code="VALIDATION_FAILED",
                error_details=validation_result
            )

        # 상태 변경
        flow.status = FlowStatus.ACTIVE

        # 즉시 실행 처리 (옵션)
        next_execution = None
        if request.immediate:
            # 즉시 실행 로직 (스케줄러에서 처리)
            next_execution = datetime.now()
        else:
            # 다음 스케줄 시간 계산 (스케줄러에서 처리)
            next_execution = datetime.now() + timedelta(minutes=5)  # 임시

        return FlowActionResult(
            success=True,
            message="플로우가 시작되었습니다",
            current_status=flow.status,
            next_execution=next_execution
        )

    async def _pause_flow(self, flow: Flow, request: FlowActionRequest) -> FlowActionResult:
        """플로우 일시정지"""
        if flow.status != FlowStatus.ACTIVE:
            return FlowActionResult(
                success=False,
                message="실행 중이지 않은 플로우는 일시정지할 수 없습니다",
                current_status=flow.status,
                error_code="NOT_ACTIVE"
            )

        # 상태 변경
        flow.status = FlowStatus.PAUSED

        # 일시정지 시간 계산
        paused_until = None
        if request.pause_duration_minutes:
            paused_until = datetime.now() + timedelta(minutes=request.pause_duration_minutes)

        return FlowActionResult(
            success=True,
            message="플로우가 일시정지되었습니다",
            current_status=flow.status,
            paused_until=paused_until
        )

    async def _resume_flow(self, flow: Flow, request: FlowActionRequest) -> FlowActionResult:
        """플로우 재개"""
        if flow.status != FlowStatus.PAUSED:
            return FlowActionResult(
                success=False,
                message="일시정지 상태가 아닌 플로우는 재개할 수 없습니다",
                current_status=flow.status,
                error_code="NOT_PAUSED"
            )

        # 상태 변경
        flow.status = FlowStatus.ACTIVE

        # 다음 실행 시간 계산
        next_execution = datetime.now() + timedelta(minutes=1)  # 임시

        return FlowActionResult(
            success=True,
            message="플로우가 재개되었습니다",
            current_status=flow.status,
            next_execution=next_execution
        )

    async def _stop_flow(self, flow: Flow, request: FlowActionRequest) -> FlowActionResult:
        """플로우 중지"""
        if flow.status == FlowStatus.INACTIVE:
            return FlowActionResult(
                success=False,
                message="이미 중지된 플로우입니다",
                current_status=flow.status,
                error_code="ALREADY_INACTIVE"
            )

        # 상태 변경
        flow.status = FlowStatus.INACTIVE

        return FlowActionResult(
            success=True,
            message="플로우가 중지되었습니다",
            current_status=flow.status
        )

    async def _validate_flow_for_execution(self, flow: Flow) -> Dict[str, Any]:
        """플로우 실행 가능성 검증"""
        errors = []
        warnings = []

        # 모듈 존재 확인
        if not flow.flow_modules or len(flow.flow_modules) == 0:
            errors.append("연결된 모듈이 없습니다")

        # 블로그 존재 확인
        if not flow.flow_blogs or len(flow.flow_blogs) == 0:
            errors.append("연결된 블로그가 없습니다")

        # 모듈 스케줄 확인
        has_schedules = False
        if flow.flow_modules:
            for flow_module in flow.flow_modules:
                if flow_module.module and flow_module.module.schedule_matrix:
                    has_schedules = True
                    break

        if not has_schedules:
            warnings.append("스케줄이 설정된 모듈이 없습니다")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    # ===========================================
    # 일괄 액션 처리
    # ===========================================

    async def execute_bulk_flow_action(
        self,
        user: User,
        request: BulkFlowActionRequest
    ) -> BulkFlowActionResult:
        """다중 플로우 일괄 액션"""
        try:
            logger.info(f"[BULK_FLOW_ACTION] 사용자 {user.id} 일괄 액션: {request.action} ({len(request.flow_ids)}개)")

            results = []
            successful_count = 0
            failed_count = 0

            for flow_id in request.flow_ids:
                try:
                    # 개별 액션 실행
                    action_request = FlowActionRequest(
                        action=request.action,
                        reason=request.reason
                    )
                    result = await self.execute_flow_action(user, flow_id, action_request)

                    results.append(result)
                    if result.success:
                        successful_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    # 개별 실패는 전체 실패로 이어지지 않음
                    logger.warning(f"[BULK_FLOW_ACTION] 플로우 {flow_id} 액션 실패: {e}")
                    failed_result = FlowActionResult(
                        success=False,
                        message=f"액션 실행 실패: {str(e)}",
                        flow_id=flow_id,
                        previous_status=FlowStatus.INACTIVE,  # 기본값
                        current_status=FlowStatus.INACTIVE,
                        error_code="EXECUTION_ERROR"
                    )
                    results.append(failed_result)
                    failed_count += 1

            # 요약 메시지 생성
            summary_message = f"{len(request.flow_ids)}개 플로우 중 {successful_count}개 성공, {failed_count}개 실패"

            logger.info(f"[BULK_FLOW_ACTION] 일괄 액션 완료: {summary_message}")

            return BulkFlowActionResult(
                total_requested=len(request.flow_ids),
                successful_count=successful_count,
                failed_count=failed_count,
                results=results,
                summary_message=summary_message
            )

        except Exception as e:
            logger.error(f"[BULK_FLOW_ACTION] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="일괄 액션을 실행하는 중 오류가 발생했습니다"
            )