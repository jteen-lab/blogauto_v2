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
from ..models.autorun_log import AutorunLog
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

            # 오토런에 추가된 플로우만 조회
            query = (
                select(Flow)
                .options(
                    selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                    selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
                )
                .where(
                    and_(
                        Flow.user_id == user.id,
                        Flow.is_in_autorun == True
                    )
                )
            )

            if not include_inactive:
                query = query.where(Flow.status != FlowStatus.INACTIVE)

            query = query.order_by(Flow.updated_at.desc())
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
                # 첫 번째 활성 플로우 (최근 업데이트 순)
                next_flow = active_flow_objs[0]
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
        # 모듈 링크 정보 구성
        module_links = []
        if flow.module_links:
            for link in flow.module_links:
                module_data = None
                if link.module:
                    module_data = {
                        "id": link.module.id,
                        "name": link.module.name,
                        "description": link.module.description,
                        "module_type": {
                            "code": link.module.module_type.code if link.module.module_type else "republish",
                            "name": link.module.module_type.name if link.module.module_type else "재발행"
                        },
                        "settings": link.module.settings,
                        "created_at": link.module.created_at.isoformat() if link.module.created_at else None
                    }
                module_links.append({
                    "id": link.id,
                    "execution_order": link.execution_order,
                    "module": module_data
                })

        # 블로그 링크 정보 구성
        blog_links = []
        if flow.blog_links:
            for link in flow.blog_links:
                blog_links.append({
                    "id": link.id,
                    "blog": {
                        "id": link.blog.id,
                        "name": link.blog.name,
                        "platform": link.blog.platform,
                        "url": link.blog.url
                    } if link.blog else None
                })

        return {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description,
            "status": flow.status,
            "module_count": len(flow.module_links) if flow.module_links else 0,
            "blog_count": len(flow.blog_links) if flow.blog_links else 0,
            "module_links": module_links,
            "blog_links": blog_links,
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
                selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
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

        # 모든 실행 상태의 is_paused 초기화 (연속 실패로 paused된 상태 복구)
        from ..models.flow_execution_state import FlowExecutionState
        fes_query = select(FlowExecutionState).where(
            and_(
                FlowExecutionState.flow_id == flow.id,
                FlowExecutionState.is_paused == True
            )
        )
        fes_result = await self.db.execute(fes_query)
        paused_states = list(fes_result.scalars().all())
        for state in paused_states:
            state.is_paused = False
            state.paused_at = None
            state.consecutive_failures = 0
            logger.info(
                f"[FLOW_ACTION] 실행 상태 일시정지 해제 | "
                f"FlowID={flow.id} | ActionType={state.action_type}"
            )

        # 스케줄러에 재등록 (즉시 실행 옵션 반영)
        from ..scheduler.flow_scheduler import get_flow_scheduler
        scheduler = get_flow_scheduler()
        next_execution = None
        if scheduler and flow.is_in_autorun:
            await scheduler.register_flow(
                flow.id, immediate_execution=bool(request.immediate)
            )
            schedule_info = await scheduler.get_flow_schedule_info(flow.id)
            if schedule_info.get("modules"):
                for module_info in schedule_info["modules"]:
                    if module_info.get("next_execution_at"):
                        next_execution = datetime.fromisoformat(
                            module_info["next_execution_at"]
                        )
                        break

        if not next_execution:
            next_execution = datetime.now() + timedelta(minutes=5)

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

        # 스케줄러에서 일시정지 (남은 시간 보존)
        from ..scheduler.flow_scheduler import get_flow_scheduler
        scheduler = get_flow_scheduler()
        if scheduler:
            await scheduler.pause_flow(flow.id)

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

        # 스케줄러에서 재개 (남은 시간으로 복원)
        from ..scheduler.flow_scheduler import get_flow_scheduler
        scheduler = get_flow_scheduler()
        next_execution = None
        if scheduler:
            result = await scheduler.resume_flow(flow.id)
            # 스케줄러에서 다음 실행 시간 받아오기
            if result.get("success"):
                schedule_info = await scheduler.get_flow_schedule_info(flow.id)
                if schedule_info.get("modules"):
                    for module_info in schedule_info["modules"]:
                        if module_info.get("next_execution_at"):
                            next_execution = datetime.fromisoformat(module_info["next_execution_at"])
                            break

        return FlowActionResult(
            success=True,
            message="플로우가 재개되었습니다",
            current_status=flow.status,
            next_execution=next_execution
        )

    async def _stop_flow(self, flow: Flow, request: FlowActionRequest) -> FlowActionResult:
        """플로우 중지 - 스케줄 상태 초기화 포함

        중지 시 FlowExecutionState를 초기화하여
        재시작 시 새로운 스케줄로 시작하도록 합니다.
        """
        if flow.status == FlowStatus.INACTIVE:
            return FlowActionResult(
                success=False,
                message="이미 중지된 플로우입니다",
                current_status=flow.status,
                error_code="ALREADY_INACTIVE"
            )

        # 스케줄러에서 해제
        from ..scheduler.flow_scheduler import get_flow_scheduler
        scheduler = get_flow_scheduler()
        if scheduler:
            await scheduler.unregister_flow(flow.id)

        # FlowExecutionState 초기화 (재시작 시 새로운 스케줄로 시작)
        await self._reset_execution_states(flow.id)

        # 상태 변경
        flow.status = FlowStatus.INACTIVE

        logger.info(
            f"[FLOW_ACTION] 플로우 중지 및 스케줄 상태 초기화 | FlowID={flow.id}"
        )

        return FlowActionResult(
            success=True,
            message="플로우가 중지되었습니다",
            current_status=flow.status
        )

    async def _reset_execution_states(self, flow_id: int) -> int:
        """플로우의 모든 FlowExecutionState 초기화

        중지/오토런 제외 시 호출하여 재시작 시
        새로운 스케줄로 시작하도록 합니다.
        레코드는 삭제하지 않고 값만 초기화합니다.

        Args:
            flow_id: 플로우 ID

        Returns:
            초기화된 상태 레코드 수
        """
        from ..models.flow_execution_state import FlowExecutionState

        states_result = await self.db.execute(
            select(FlowExecutionState).where(
                FlowExecutionState.flow_id == flow_id
            )
        )
        reset_count = 0
        for state in states_result.scalars().all():
            state.last_executed_at = None
            state.last_success_at = None
            state.next_execution_at = None
            state.successful_executions = 0
            state.failed_executions = 0
            state.total_executions = 0
            state.consecutive_failures = 0
            state.is_paused = False
            state.paused_at = None
            state.remaining_seconds = None
            state.is_running = False
            reset_count += 1

        if reset_count > 0:
            logger.info(
                f"[FLOW_ACTION] FlowExecutionState 초기화 완료 | "
                f"FlowID={flow_id} | ResetCount={reset_count}"
            )

        return reset_count

    async def _validate_flow_for_execution(self, flow: Flow) -> Dict[str, Any]:
        """플로우 실행 가능성 검증"""
        errors = []
        warnings = []

        # 모듈 존재 확인
        if not flow.module_links or len(flow.module_links) == 0:
            errors.append("연결된 모듈이 없습니다")
            return {
                "is_valid": False,
                "errors": errors,
                "warnings": warnings
            }

        # 모듈 타입 분석
        module_types = set()
        has_blog_required_module = False  # republish 등 블로그 필수 모듈
        for flow_module in flow.module_links:
            if flow_module.module and flow_module.module.module_type:
                type_code = flow_module.module.module_type.code
                module_types.add(type_code)
                # republish, publish 등은 블로그 필수
                if type_code in ("republish", "publish"):
                    has_blog_required_module = True

        # 블로그 존재 확인 (블로그 필수 모듈이 있는 경우에만)
        has_blogs = flow.blog_links and len(flow.blog_links) > 0
        if has_blog_required_module and not has_blogs:
            errors.append("재발행/발행 모듈이 있지만 연결된 블로그가 없습니다")

        # 블로그 없이 수집 모듈만 있는 경우는 허용
        if not has_blogs and "collect" in module_types and not has_blog_required_module:
            # collect 모듈만 있는 경우 블로그 없이 실행 가능
            warnings.append("수집 모듈만 있어 블로그 없이 실행됩니다")

        # Note: 스케줄은 Growth Profile(GP)에서 관리됨
        # module.schedule_matrix 레거시 컬럼은 029 마이그레이션에서 제거됨

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "module_types": list(module_types)
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

                except HTTPException as he:
                    # HTTPException도 개별 실패로 처리 (전체 실패로 이어지지 않음)
                    logger.warning(f"[BULK_FLOW_ACTION] 플로우 {flow_id} 액션 실패 (HTTP): {he.detail}")
                    failed_result = FlowActionResult(
                        success=False,
                        message=f"액션 실행 실패: {he.detail}",
                        flow_id=flow_id,
                        current_status=FlowStatus.INACTIVE,
                        error_code="HTTP_ERROR"
                    )
                    results.append(failed_result)
                    failed_count += 1

                except Exception as e:
                    # 개별 실패는 전체 실패로 이어지지 않음
                    logger.warning(f"[BULK_FLOW_ACTION] 플로우 {flow_id} 액션 실패: {e}")
                    failed_result = FlowActionResult(
                        success=False,
                        message=f"액션 실행 실패: {str(e)}",
                        flow_id=flow_id,
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

    # ===========================================
    # 오토런 미추가 플로우 조회 및 추가
    # ===========================================

    async def get_available_flows(
        self,
        user: User,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """오토런에 추가되지 않은 플로우 목록 조회"""
        try:
            logger.info(f"[GET_AVAILABLE_FLOWS] 사용자 {user.id} 미추가 플로우 조회")

            # 오토런 미추가 플로우 조회 (is_in_autorun = False)
            query = (
                select(Flow)
                .options(
                    selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                    selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
                )
                .where(
                    and_(
                        Flow.user_id == user.id,
                        Flow.is_in_autorun == False
                    )
                )
            )

            # 검색어 필터링
            if search:
                search_pattern = f"%{search}%"
                query = query.where(
                    Flow.name.ilike(search_pattern)
                )

            query = query.order_by(Flow.updated_at.desc())
            result = await self.db.execute(query)
            flows = result.scalars().all()

            logger.info(f"[GET_AVAILABLE_FLOWS] {len(flows)}개 미추가 플로우 조회됨")

            return [self._flow_to_execution_info(f) for f in flows]

        except Exception as e:
            logger.error(f"[GET_AVAILABLE_FLOWS] 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="미추가 플로우 목록을 조회하는 중 오류가 발생했습니다"
            )

    async def add_flows_to_autorun(
        self,
        user: User,
        flow_ids: List[int]
    ) -> Dict[str, Any]:
        """여러 플로우를 오토런에 추가"""
        try:
            logger.info(f"[ADD_FLOWS_TO_AUTORUN] 사용자 {user.id} 플로우 {len(flow_ids)}개 추가 요청")

            success_count = 0
            failed_count = 0
            failed_ids = []
            added_flow_ids = []  # 스케줄러 등록용

            for flow_id in flow_ids:
                try:
                    # 플로우 조회
                    query = select(Flow).where(
                        and_(
                            Flow.id == flow_id,
                            Flow.user_id == user.id
                        )
                    )
                    result = await self.db.execute(query)
                    flow = result.scalar_one_or_none()

                    if not flow:
                        failed_count += 1
                        failed_ids.append(flow_id)
                        continue

                    # 이미 추가된 경우 스킵
                    if flow.is_in_autorun:
                        continue

                    # 오토런에 추가
                    flow.add_to_autorun()
                    added_flow_ids.append(flow_id)
                    success_count += 1

                except Exception as e:
                    logger.warning(f"[ADD_FLOWS_TO_AUTORUN] 플로우 {flow_id} 추가 실패: {e}")
                    failed_count += 1
                    failed_ids.append(flow_id)

            # 먼저 커밋하여 DB에 반영 (중요: 스케줄러보다 먼저!)
            await self.db.commit()

            # 커밋 후 스케줄러에 등록 (즉시 실행)
            from ..scheduler.flow_scheduler import get_flow_scheduler
            scheduler = get_flow_scheduler()
            if scheduler:
                for flow_id in added_flow_ids:
                    try:
                        await scheduler.register_flow(flow_id, immediate_execution=True)
                        logger.info(f"[ADD_FLOWS_TO_AUTORUN] 스케줄러 등록 완료: {flow_id}")
                    except Exception as e:
                        logger.warning(f"[ADD_FLOWS_TO_AUTORUN] 스케줄러 등록 실패: {flow_id} | {e}")

            logger.info(f"[ADD_FLOWS_TO_AUTORUN] 완료: {success_count}개 성공, {failed_count}개 실패")

            return {
                "success": True,
                "message": f"{success_count}개 플로우가 오토런에 추가되었습니다",
                "success_count": success_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids
            }

        except Exception as e:
            logger.error(f"[ADD_FLOWS_TO_AUTORUN] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우를 오토런에 추가하는 중 오류가 발생했습니다"
            )

    async def remove_flow_from_autorun(
        self,
        user: User,
        flow_id: int
    ) -> Dict[str, Any]:
        """플로우를 오토런에서 제외"""
        try:
            logger.info(f"[REMOVE_FLOW_FROM_AUTORUN] 사용자 {user.id} 플로우 {flow_id} 제외 요청")

            # 플로우 조회
            query = select(Flow).where(
                and_(
                    Flow.id == flow_id,
                    Flow.user_id == user.id
                )
            )
            result = await self.db.execute(query)
            flow = result.scalar_one_or_none()

            if not flow:
                raise HTTPException(
                    status_code=404,
                    detail="플로우를 찾을 수 없습니다"
                )

            if not flow.is_in_autorun:
                return {
                    "success": False,
                    "message": "이미 오토런에서 제외된 플로우입니다"
                }

            # 스케줄러에서 해제
            from ..scheduler.flow_scheduler import get_flow_scheduler
            scheduler = get_flow_scheduler()
            if scheduler:
                await scheduler.unregister_flow(flow_id)

            # FlowExecutionState 초기화 (재추가 시 새로운 스케줄로 시작)
            await self._reset_execution_states(flow_id)

            # 오토런에서 제외
            flow.remove_from_autorun()
            await self.db.commit()

            logger.info(f"[REMOVE_FLOW_FROM_AUTORUN] 플로우 {flow_id} 오토런에서 제외 및 스케줄 상태 초기화")

            return {
                "success": True,
                "message": "플로우가 오토런에서 제외되었습니다"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[REMOVE_FLOW_FROM_AUTORUN] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우를 오토런에서 제외하는 중 오류가 발생했습니다"
            )

    # ===========================================
    # 로그 조회
    # ===========================================

    async def get_autorun_logs(
        self,
        user: User,
        flow_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """오토런 로그 조회"""
        try:
            logger.info(f"[GET_AUTORUN_LOGS] 사용자 {user.id} 로그 조회")

            # 기본 쿼리
            query = (
                select(AutorunLog)
                .options(selectinload(AutorunLog.flow))
                .where(AutorunLog.user_id == user.id)
            )

            # 플로우 ID 필터
            if flow_id:
                query = query.where(AutorunLog.flow_id == flow_id)

            # 액션 타입 필터
            if action:
                query = query.where(AutorunLog.action == action)

            # 정렬 및 페이징
            query = query.order_by(desc(AutorunLog.created_at)).offset(offset).limit(limit)

            result = await self.db.execute(query)
            logs = result.scalars().all()

            # 전체 개수 조회
            count_query = select(func.count(AutorunLog.id)).where(AutorunLog.user_id == user.id)
            if flow_id:
                count_query = count_query.where(AutorunLog.flow_id == flow_id)
            if action:
                count_query = count_query.where(AutorunLog.action == action)
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            logger.info(f"[GET_AUTORUN_LOGS] {len(logs)}개 로그 조회됨 (전체: {total})")

            return {
                "logs": [self._log_to_dict(log) for log in logs],
                "total": total,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"[GET_AUTORUN_LOGS] 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="로그를 조회하는 중 오류가 발생했습니다"
            )

    def _log_to_dict(self, log: AutorunLog) -> Dict[str, Any]:
        """로그를 딕셔너리로 변환 (새 간결한 포맷)"""
        # 작업 시간 m/s 포맷
        duration_formatted = None
        if log.execution_duration_ms is not None:
            duration_sec = log.execution_duration_ms / 1000
            duration_formatted = f"{duration_sec:.1f}s"

        return {
            "id": log.id,
            "flow_id": log.flow_id,
            # 새 간결한 포맷 필드
            "flow_name": log.flow_name or (log.flow.name if log.flow else None),
            "module_name": log.module_name,
            "module_type_name": log.module_type_name,  # 모듈 타입명 추가
            "blog_name": log.blog_name,
            "post_title": log.post_title,
            "action_time": log.action_time,
            "compact_display": log.compact_display,
            # 기존 호환성 필드
            "action": log.action,
            "action_display": log.action_display,
            "status": log.status,
            "status_display": log.status_display,
            "message": log.message,
            "execution_duration_ms": log.execution_duration_ms,
            "formatted_duration": log.formatted_duration,
            "duration_formatted": duration_formatted,  # m/s 포맷 추가
            "posts_processed": log.posts_processed,
            "posts_success": log.posts_success,
            "posts_failed": log.posts_failed,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }

    async def create_log(
        self,
        user_id: int,
        flow_id: int,
        action: str,
        status: str = "success",
        message: str = None
    ) -> AutorunLog:
        """로그 생성"""
        try:
            log = AutorunLog.create_action_log(
                user_id=user_id,
                flow_id=flow_id,
                action=action,
                status=status,
                message=message
            )
            self.db.add(log)
            await self.db.commit()
            await self.db.refresh(log)
            return log
        except Exception as e:
            logger.error(f"[CREATE_LOG] 오류: {e}")
            await self.db.rollback()
            return None