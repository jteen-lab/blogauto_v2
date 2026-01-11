"""
플로우 스케줄러 (재설계)

Features:
- IntervalTrigger 기반 분 단위 스케줄링
- 오토런 등록 시 즉시 실행
- 일시정지/재개 시 남은 시간 보존
- schedule_matrix를 활성화 시간대로 해석
- 개별 Job 등록/관리
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..models.module import Module
from ..models.flow_execution_state import FlowExecutionState
from ..engine.flow_engine import FlowEngine
from ..core.database import db_manager
from ..core.logger import get_logger
from .scheduler import scheduler_instance

logger = get_logger("flow_scheduler", "republish.log")

# Timezone 설정
KST = pytz.timezone('Asia/Seoul')

# 전역 플로우 스케줄러 인스턴스
_flow_scheduler: Optional["FlowScheduler"] = None


class FlowScheduler:
    """플로우 스케줄러 - IntervalTrigger 기반 분 단위 스케줄링"""

    def __init__(self):
        self.scheduler = scheduler_instance
        self.flow_engine = FlowEngine()
        self._initialized = False
        # Job ID 포맷: flow_{flow_id}_module_{module_id}
        self._job_prefix = "flow_"

    async def initialize(self) -> None:
        """스케줄러 초기화 및 시작"""
        if self._initialized:
            logger.warning("[FLOW_SCHEDULER] Already initialized")
            return

        # 기존 모든 플로우 Job 제거 후 재등록
        await self._cleanup_all_jobs()

        # 오토런 활성화된 플로우들의 스케줄 등록
        await self._register_active_flows()

        self._initialized = True
        logger.info("[FLOW_SCHEDULER] Initialized with IntervalTrigger")

    async def shutdown(self) -> None:
        """스케줄러 종료"""
        if not self._initialized:
            return

        await self._cleanup_all_jobs()
        self._initialized = False
        logger.info("[FLOW_SCHEDULER] Shutdown complete")

    @property
    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._initialized

    # ===========================================
    # 플로우 등록/해제
    # ===========================================

    async def register_flow(
        self,
        flow_id: int,
        immediate_execution: bool = True
    ) -> Dict[str, Any]:
        """
        플로우를 스케줄러에 등록

        Args:
            flow_id: 플로우 ID
            immediate_execution: 즉시 실행 여부 (기본: True)

        Returns:
            등록 결과
        """
        try:
            logger.info(f"[FLOW_SCHEDULER] Registering flow | FlowID={flow_id}")

            async with db_manager.get_session() as db:
                # 플로우 조회
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 오토런 상태 확인
                if not flow.is_in_autorun:
                    return {
                        "success": False,
                        "message": "오토런에 등록되지 않은 플로우입니다"
                    }

                # 기존 Job 제거
                await self.unregister_flow(flow_id)

                # 모듈별 실행 상태 초기화 또는 조회
                registered_count = 0
                for link in flow.module_links:
                    module = link.module
                    if not module:
                        continue

                    # 실행 상태 조회 또는 생성
                    state = await self._get_or_create_execution_state(
                        db, flow.id, module.id
                    )

                    # 간격 계산
                    interval_minutes = module.calculated_interval_minutes

                    # 즉시 실행 + 스케줄 등록
                    if immediate_execution:
                        # 즉시 실행 Job 등록
                        await self._schedule_immediate_execution(
                            flow, module, state
                        )
                    else:
                        # 다음 실행 시간 계산 및 스케줄 등록
                        await self._schedule_next_execution(
                            db, flow, module, state, interval_minutes
                        )

                    registered_count += 1

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Flow registered | FlowID={flow_id} | "
                    f"Modules={registered_count} | Immediate={immediate_execution}"
                )

                return {
                    "success": True,
                    "message": f"플로우가 등록되었습니다 (모듈 {registered_count}개)",
                    "flow_id": flow_id,
                    "module_count": registered_count,
                    "immediate_execution": immediate_execution
                }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Register error | FlowID={flow_id} | Error={e}")
            return {
                "success": False,
                "message": f"플로우 등록 오류: {e}"
            }

    async def unregister_flow(self, flow_id: int) -> Dict[str, Any]:
        """플로우 스케줄 해제"""
        try:
            logger.info(f"[FLOW_SCHEDULER] Unregistering flow | FlowID={flow_id}")

            # 해당 플로우의 모든 Job 제거
            jobs = self.scheduler.get_jobs()
            removed_count = 0

            for job in jobs:
                if job.id.startswith(f"{self._job_prefix}{flow_id}_"):
                    try:
                        self.scheduler.remove_job(job.id)
                        removed_count += 1
                    except Exception:
                        pass

            logger.info(
                f"[FLOW_SCHEDULER] Flow unregistered | FlowID={flow_id} | "
                f"RemovedJobs={removed_count}"
            )

            return {
                "success": True,
                "message": f"{removed_count}개 스케줄이 해제되었습니다",
                "removed_count": removed_count
            }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Unregister error | FlowID={flow_id} | Error={e}")
            return {
                "success": False,
                "message": f"스케줄 해제 오류: {e}"
            }

    # ===========================================
    # 일시정지/재개
    # ===========================================

    async def pause_flow(self, flow_id: int) -> Dict[str, Any]:
        """플로우 일시정지 - 남은 시간 보존"""
        try:
            logger.info(f"[FLOW_SCHEDULER] Pausing flow | FlowID={flow_id}")

            async with db_manager.get_session() as db:
                # 플로우 조회
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 각 모듈의 실행 상태에 남은 시간 저장
                paused_count = 0
                for link in flow.module_links:
                    module = link.module
                    if not module:
                        continue

                    # 실행 상태 조회
                    state = await self._get_execution_state(
                        db, flow.id, module.id
                    )
                    if state:
                        state.pause()
                        paused_count += 1

                # Job 제거
                await self.unregister_flow(flow_id)

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Flow paused | FlowID={flow_id} | "
                    f"PausedModules={paused_count}"
                )

                return {
                    "success": True,
                    "message": "플로우가 일시정지되었습니다",
                    "paused_count": paused_count
                }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Pause error | FlowID={flow_id} | Error={e}")
            return {
                "success": False,
                "message": f"일시정지 오류: {e}"
            }

    async def resume_flow(self, flow_id: int) -> Dict[str, Any]:
        """플로우 재개 - 남은 시간으로 스케줄 복원"""
        try:
            logger.info(f"[FLOW_SCHEDULER] Resuming flow | FlowID={flow_id}")

            async with db_manager.get_session() as db:
                # 플로우 조회
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 각 모듈의 실행 상태에서 남은 시간으로 스케줄 복원
                resumed_count = 0
                for link in flow.module_links:
                    module = link.module
                    if not module:
                        continue

                    # 실행 상태 조회
                    state = await self._get_execution_state(
                        db, flow.id, module.id
                    )
                    if state and state.is_paused:
                        # 재개하고 다음 실행 시간 가져오기
                        next_execution = state.resume()

                        if next_execution:
                            # 남은 시간으로 스케줄 등록
                            await self._schedule_at_time(
                                flow, module, state, next_execution
                            )
                        else:
                            # 남은 시간이 없으면 즉시 실행
                            await self._schedule_immediate_execution(
                                flow, module, state
                            )

                        resumed_count += 1

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Flow resumed | FlowID={flow_id} | "
                    f"ResumedModules={resumed_count}"
                )

                return {
                    "success": True,
                    "message": "플로우가 재개되었습니다",
                    "resumed_count": resumed_count
                }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Resume error | FlowID={flow_id} | Error={e}")
            return {
                "success": False,
                "message": f"재개 오류: {e}"
            }

    # ===========================================
    # 수동 실행
    # ===========================================

    async def execute_flow_now(
        self,
        flow_id: int,
        action_type: str = "republish"
    ) -> Dict[str, Any]:
        """플로우 즉시 실행 (수동)"""
        try:
            logger.info(
                f"[FLOW_SCHEDULER] Manual execution | FlowID={flow_id} | "
                f"ActionType={action_type}"
            )

            async with db_manager.get_session() as db:
                # 플로우 조회
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 플로우 실행
                result = await self.flow_engine.execute(
                    db=db,
                    flow=flow,
                    action_type=action_type
                )

                # 실행 상태 업데이트
                for link in flow.module_links:
                    module = link.module
                    if module and module.module_type and module.module_type.code == action_type:
                        state = await self._get_or_create_execution_state(
                            db, flow.id, module.id
                        )
                        state.record_execution(result.get("success", False))

                        # 다음 실행 시간 계산
                        interval_minutes = module.calculated_interval_minutes
                        state.calculate_next_execution(
                            interval_minutes=interval_minutes,
                            schedule_matrix=module.schedule_matrix,
                            jitter_enabled=module.jitter_enabled,
                            jitter_min_percent=module.jitter_min_percent,
                            jitter_max_percent=module.jitter_max_percent
                        )

                await db.commit()

                return result

        except Exception as e:
            logger.error(
                f"[FLOW_SCHEDULER] Manual execution error | FlowID={flow_id} | "
                f"Error={e}"
            )
            return {
                "success": False,
                "message": f"실행 오류: {e}"
            }

    # ===========================================
    # 내부 헬퍼 메서드
    # ===========================================

    async def _get_flow_with_modules(
        self,
        db: AsyncSession,
        flow_id: int
    ) -> Optional[Flow]:
        """플로우 및 모듈 정보 조회"""
        query = (
            select(Flow)
            .options(
                selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
            )
            .where(Flow.id == flow_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _get_or_create_execution_state(
        self,
        db: AsyncSession,
        flow_id: int,
        module_id: int
    ) -> FlowExecutionState:
        """실행 상태 조회 또는 생성"""
        query = select(FlowExecutionState).where(
            and_(
                FlowExecutionState.flow_id == flow_id,
                FlowExecutionState.module_id == module_id
            )
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if not state:
            state = FlowExecutionState(
                flow_id=flow_id,
                module_id=module_id
            )
            db.add(state)
            await db.flush()

        return state

    async def _get_execution_state(
        self,
        db: AsyncSession,
        flow_id: int,
        module_id: int
    ) -> Optional[FlowExecutionState]:
        """실행 상태 조회"""
        query = select(FlowExecutionState).where(
            and_(
                FlowExecutionState.flow_id == flow_id,
                FlowExecutionState.module_id == module_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _schedule_immediate_execution(
        self,
        flow: Flow,
        module: Module,
        state: FlowExecutionState
    ) -> None:
        """즉시 실행 스케줄 등록"""
        job_id = self._get_job_id(flow.id, module.id)

        # 즉시 실행 (3초 후) - timezone aware datetime 사용
        run_time = datetime.now(KST) + timedelta(seconds=3)

        self.scheduler.add_job(
            self._execute_module_callback,  # AsyncIOExecutor가 async 함수 직접 지원
            DateTrigger(run_date=run_time, timezone=KST),
            args=[flow.id, module.id],
            id=job_id,
            name=f"Immediate: Flow {flow.name} - Module {module.name}",
            replace_existing=True
        )

        logger.info(
            f"[FLOW_SCHEDULER] Scheduled immediate | FlowID={flow.id} | "
            f"ModuleID={module.id} | RunTime={run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _schedule_next_execution(
        self,
        db: AsyncSession,
        flow: Flow,
        module: Module,
        state: FlowExecutionState,
        interval_minutes: int
    ) -> None:
        """다음 실행 시간 계산 및 스케줄 등록"""
        # 다음 실행 시간 계산
        next_execution = state.calculate_next_execution(
            interval_minutes=interval_minutes,
            schedule_matrix=module.schedule_matrix,
            jitter_enabled=module.jitter_enabled,
            jitter_min_percent=module.jitter_min_percent,
            jitter_max_percent=module.jitter_max_percent
        )

        if next_execution:
            await self._schedule_at_time(flow, module, state, next_execution)

    async def _schedule_at_time(
        self,
        flow: Flow,
        module: Module,
        state: FlowExecutionState,
        run_time: datetime
    ) -> None:
        """특정 시간에 실행 스케줄 등록"""
        job_id = self._get_job_id(flow.id, module.id)

        # timezone aware로 변환
        now = datetime.now(KST)
        if run_time.tzinfo is None:
            run_time = KST.localize(run_time)

        # 이미 지난 시간이면 즉시 실행
        if run_time <= now:
            run_time = now + timedelta(seconds=3)

        self.scheduler.add_job(
            self._execute_module_callback,  # AsyncIOExecutor가 async 함수 직접 지원
            DateTrigger(run_date=run_time, timezone=KST),
            args=[flow.id, module.id],
            id=job_id,
            name=f"Flow {flow.name} - Module {module.name}",
            replace_existing=True
        )

        logger.info(
            f"[FLOW_SCHEDULER] Scheduled | FlowID={flow.id} | "
            f"ModuleID={module.id} | RunTime={run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _execute_module_callback(
        self,
        flow_id: int,
        module_id: int
    ) -> None:
        """모듈 실행 콜백 (비동기 실제 로직)"""
        try:
            logger.info(
                f"[FLOW_SCHEDULER] Executing | FlowID={flow_id} | ModuleID={module_id}"
            )

            async with db_manager.get_session() as db:
                # 플로우 조회
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    logger.warning(f"[FLOW_SCHEDULER] Flow not found | FlowID={flow_id}")
                    return

                # 오토런 상태 확인
                if not flow.is_in_autorun:
                    logger.warning(
                        f"[FLOW_SCHEDULER] Flow not in autorun | FlowID={flow_id}"
                    )
                    return

                # 플로우 상태 확인 (paused면 실행하지 않음)
                if flow.status == "paused":
                    logger.info(
                        f"[FLOW_SCHEDULER] Flow is paused, skipping | FlowID={flow_id}"
                    )
                    return

                # 해당 모듈 찾기
                module = None
                for link in flow.module_links:
                    if link.module and link.module.id == module_id:
                        module = link.module
                        break

                if not module:
                    logger.warning(
                        f"[FLOW_SCHEDULER] Module not found | FlowID={flow_id} | "
                        f"ModuleID={module_id}"
                    )
                    return

                # 실행 상태 조회
                state = await self._get_execution_state(db, flow_id, module_id)

                # 활성화 시간대 체크
                if state and not state.is_in_active_window(module.schedule_matrix):
                    logger.info(
                        f"[FLOW_SCHEDULER] Not in active window, rescheduling | "
                        f"FlowID={flow_id} | ModuleID={module_id}"
                    )
                    # 다음 활성 시간대로 재스케줄
                    interval_minutes = module.calculated_interval_minutes
                    await self._schedule_next_execution(
                        db, flow, module, state, interval_minutes
                    )
                    await db.commit()
                    return

                # 모듈 타입에서 액션 타입 결정
                action_type = "republish"
                if module.module_type:
                    action_type = module.module_type.code

                # 플로우 실행 (module_id 전달하여 정확한 모듈로 실행)
                result = await self.flow_engine.execute(
                    db=db,
                    flow=flow,
                    action_type=action_type,
                    module_id=module_id
                )

                # 실행 상태 업데이트
                if state:
                    state.record_execution(result.get("success", False))

                    # 다음 실행 시간 계산 및 스케줄 등록
                    interval_minutes = module.calculated_interval_minutes
                    next_execution = state.calculate_next_execution(
                        interval_minutes=interval_minutes,
                        schedule_matrix=module.schedule_matrix,
                        jitter_enabled=module.jitter_enabled,
                        jitter_min_percent=module.jitter_min_percent,
                        jitter_max_percent=module.jitter_max_percent
                    )

                    if next_execution:
                        await self._schedule_at_time(flow, module, state, next_execution)

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Execution completed | FlowID={flow_id} | "
                    f"ModuleID={module_id} | Success={result.get('success', False)}"
                )

        except Exception as e:
            logger.error(
                f"[FLOW_SCHEDULER] Execution error | FlowID={flow_id} | "
                f"ModuleID={module_id} | Error={e}"
            )

    async def _register_active_flows(self) -> None:
        """모든 활성 오토런 플로우 등록"""
        try:
            async with db_manager.get_session() as db:
                # 오토런 활성화된 플로우 조회
                query = (
                    select(Flow)
                    .options(
                        selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
                        selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
                    )
                    .where(
                        and_(
                            Flow.is_in_autorun == True,
                            Flow.status == "active"
                        )
                    )
                )
                result = await db.execute(query)
                flows = list(result.scalars().all())

                logger.info(
                    f"[FLOW_SCHEDULER] Registering active flows | Count={len(flows)}"
                )

                for flow in flows:
                    # 즉시 실행 없이 스케줄만 등록
                    await self.register_flow(flow.id, immediate_execution=False)

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Register active flows error | Error={e}")

    async def _cleanup_all_jobs(self) -> None:
        """모든 플로우 Job 제거"""
        try:
            jobs = self.scheduler.get_jobs()
            removed_count = 0

            for job in jobs:
                if job.id.startswith(self._job_prefix):
                    try:
                        self.scheduler.remove_job(job.id)
                        removed_count += 1
                    except Exception:
                        pass

            logger.info(f"[FLOW_SCHEDULER] Cleaned up {removed_count} jobs")

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Cleanup error | Error={e}")

    def _get_job_id(self, flow_id: int, module_id: int) -> str:
        """Job ID 생성"""
        return f"{self._job_prefix}{flow_id}_module_{module_id}"

    # ===========================================
    # 상태 조회
    # ===========================================

    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태 조회"""
        jobs = self.scheduler.get_jobs()
        flow_jobs = [j for j in jobs if j.id.startswith(self._job_prefix)]

        return {
            "is_initialized": self._initialized,
            "is_running": self.scheduler.scheduler.running if self.scheduler.scheduler else False,
            "total_jobs": len(flow_jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in flow_jobs[:20]  # 최대 20개만
            ]
        }

    async def get_flow_schedule_info(self, flow_id: int) -> Dict[str, Any]:
        """플로우의 스케줄 정보 조회"""
        try:
            async with db_manager.get_session() as db:
                # 실행 상태 조회
                query = select(FlowExecutionState).where(
                    FlowExecutionState.flow_id == flow_id
                )
                result = await db.execute(query)
                states = list(result.scalars().all())

                # Job 정보 조회
                jobs = self.scheduler.get_jobs()
                flow_jobs = [
                    j for j in jobs
                    if j.id.startswith(f"{self._job_prefix}{flow_id}_")
                ]

                return {
                    "flow_id": flow_id,
                    "scheduled_jobs": len(flow_jobs),
                    "modules": [
                        {
                            "module_id": state.module_id,
                            "last_executed_at": state.last_executed_at.isoformat() if state.last_executed_at else None,
                            "next_execution_at": state.next_execution_at.isoformat() if state.next_execution_at else None,
                            "is_paused": state.is_paused,
                            "remaining_seconds": state.remaining_seconds,
                            "total_executions": state.total_executions,
                            "success_rate": state.success_rate
                        }
                        for state in states
                    ],
                    "jobs": [
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                        }
                        for job in flow_jobs
                    ]
                }

        except Exception as e:
            logger.error(
                f"[FLOW_SCHEDULER] Get schedule info error | FlowID={flow_id} | "
                f"Error={e}"
            )
            return {
                "flow_id": flow_id,
                "error": str(e)
            }


async def setup_flow_scheduler() -> FlowScheduler:
    """플로우 스케줄러 초기화 및 시작"""
    global _flow_scheduler

    if _flow_scheduler is None:
        _flow_scheduler = FlowScheduler()

    # 참고: 기본 스케줄러는 main.py에서 이미 시작됨
    # scheduler_instance.start()를 여기서 호출하지 않음

    # 플로우 스케줄러 초기화
    await _flow_scheduler.initialize()

    logger.info("[FLOW_SCHEDULER] Setup complete")
    return _flow_scheduler


async def shutdown_flow_scheduler() -> None:
    """플로우 스케줄러 종료"""
    global _flow_scheduler

    if _flow_scheduler:
        await _flow_scheduler.shutdown()

    # 참고: 기본 스케줄러 종료는 main.py에서 처리
    # scheduler_instance.shutdown()을 여기서 호출하지 않음

    logger.info("[FLOW_SCHEDULER] Shutdown complete")


def get_flow_scheduler() -> Optional[FlowScheduler]:
    """플로우 스케줄러 인스턴스 반환"""
    return _flow_scheduler
