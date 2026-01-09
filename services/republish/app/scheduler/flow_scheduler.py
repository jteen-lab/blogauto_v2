"""
플로우 스케줄러

Features:
- 매 시간 정각에 스케줄된 플로우 실행
- 오토런에 등록되고 활성화된 플로우 대상
- FlowEngine과 통합
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from apscheduler.triggers.cron import CronTrigger

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..models.module import Module
from ..engine.flow_engine import FlowEngine
from ..core.database import db_manager
from ..core.logger import get_logger
from .scheduler import scheduler_instance

logger = get_logger("flow_scheduler", "republish.log")

# 전역 플로우 스케줄러 인스턴스
_flow_scheduler: Optional["FlowScheduler"] = None


class FlowScheduler:
    """플로우 스케줄러 - FlowEngine 통합"""

    def __init__(self):
        self.scheduler = scheduler_instance
        self.flow_engine = FlowEngine()
        self._initialized = False

    async def initialize(self) -> None:
        """스케줄러 초기화 및 시작"""
        if self._initialized:
            logger.warning("[FLOW_SCHEDULER] Already initialized")
            return

        # 매 시간 정각 실행 작업 등록
        self.scheduler.add_job(
            self.check_and_execute_flows,
            CronTrigger(minute=0),  # 매시 0분에 실행
            id="hourly_flow_check",
            name="Hourly Flow Execution Check",
            replace_existing=True
        )

        self._initialized = True
        logger.info("[FLOW_SCHEDULER] Initialized - Hourly check enabled")

    async def shutdown(self) -> None:
        """스케줄러 종료"""
        if not self._initialized:
            return

        try:
            self.scheduler.remove_job("hourly_flow_check")
        except Exception:
            pass

        self._initialized = False
        logger.info("[FLOW_SCHEDULER] Shutdown complete")

    @property
    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._initialized

    async def check_and_execute_flows(self) -> None:
        """
        현재 시간에 스케줄된 플로우 확인 및 실행

        매 시간 0분에 호출됨
        """
        now = datetime.now()
        current_day = now.weekday()  # 0=월요일, 6=일요일
        current_hour = now.hour

        logger.info(
            f"[FLOW_SCHEDULER] Checking flows | Day={current_day} | Hour={current_hour:02d}:00"
        )

        try:
            async with db_manager.get_session() as db:
                # 오토런 등록되고 활성화된 플로우 조회
                flows = await self._get_active_flows(db)
                logger.info(f"[FLOW_SCHEDULER] Found {len(flows)} active flows")

                executed_count = 0
                for flow in flows:
                    # 현재 시간에 스케줄된 모듈 찾기
                    scheduled_modules = self._find_scheduled_modules(
                        flow, current_day, current_hour
                    )

                    for module in scheduled_modules:
                        await self._execute_flow(db, flow, module)
                        executed_count += 1

                logger.info(f"[FLOW_SCHEDULER] Completed | Executed={executed_count} modules")

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Error checking flows | Error={e}")

    async def _get_active_flows(self, db: AsyncSession) -> List[Flow]:
        """오토런 활성화된 플로우 조회"""
        query = (
            select(Flow)
            .options(
                selectinload(Flow.module_links).selectinload(FlowModule.module),
                selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
            )
            .where(
                Flow.is_in_autorun == True,
                Flow.status == "active"
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    def _find_scheduled_modules(
        self,
        flow: Flow,
        day_of_week: int,
        hour: int
    ) -> List[Module]:
        """현재 시간에 스케줄된 모듈 찾기"""
        scheduled = []

        for link in flow.module_links:
            module = link.module
            if not module or not module.schedule_matrix:
                continue

            # schedule_matrix: 7x24 배열 (요일 x 시간)
            matrix = module.schedule_matrix
            if isinstance(matrix, list) and len(matrix) == 7:
                day_schedule = matrix[day_of_week]
                if isinstance(day_schedule, list) and len(day_schedule) == 24:
                    if day_schedule[hour]:
                        scheduled.append(module)
                        logger.debug(
                            f"[FLOW_SCHEDULER] Scheduled | FlowID={flow.id} | "
                            f"ModuleID={module.id} | Day={day_of_week} | Hour={hour}"
                        )

        return scheduled

    async def _execute_flow(
        self,
        db: AsyncSession,
        flow: Flow,
        module: Module
    ) -> None:
        """플로우 실행"""
        try:
            # 모듈 타입에서 액션 타입 결정
            action_type = "republish"
            if module.module_type:
                action_type = module.module_type.code

            logger.info(
                f"[FLOW_SCHEDULER] Executing | FlowID={flow.id} | "
                f"FlowName={flow.name} | ModuleID={module.id} | ActionType={action_type}"
            )

            result = await self.flow_engine.execute(
                db=db,
                flow=flow,
                action_type=action_type
            )

            if result.get("success"):
                logger.info(
                    f"[FLOW_SCHEDULER] Success | FlowID={flow.id} | "
                    f"SuccessCount={result.get('success_count', 0)} | "
                    f"FailCount={result.get('fail_count', 0)}"
                )
            else:
                logger.warning(
                    f"[FLOW_SCHEDULER] Failed | FlowID={flow.id} | "
                    f"Message={result.get('message', 'Unknown')}"
                )

        except Exception as e:
            logger.error(
                f"[FLOW_SCHEDULER] Execution error | FlowID={flow.id} | "
                f"ModuleID={module.id} | Error={e}"
            )

    async def execute_flow_now(self, flow_id: int, action_type: str = "republish") -> Dict[str, Any]:
        """플로우 즉시 실행 (수동)"""
        try:
            async with db_manager.get_session() as db:
                # 플로우 조회
                query = (
                    select(Flow)
                    .options(
                        selectinload(Flow.module_links).selectinload(FlowModule.module),
                        selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
                    )
                    .where(Flow.id == flow_id)
                )
                result = await db.execute(query)
                flow = result.scalar_one_or_none()

                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 플로우 실행
                return await self.flow_engine.execute(
                    db=db,
                    flow=flow,
                    action_type=action_type
                )

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] Manual execution error | FlowID={flow_id} | Error={e}")
            return {
                "success": False,
                "message": f"실행 오류: {e}"
            }

    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태 조회"""
        jobs = self.scheduler.get_jobs()
        return {
            "is_initialized": self._initialized,
            "is_running": self.scheduler.scheduler.running if self.scheduler.scheduler else False,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in jobs
            ]
        }


async def setup_flow_scheduler() -> FlowScheduler:
    """플로우 스케줄러 초기화 및 시작"""
    global _flow_scheduler

    if _flow_scheduler is None:
        _flow_scheduler = FlowScheduler()

    # 기본 스케줄러 시작
    await scheduler_instance.start()

    # 플로우 스케줄러 초기화
    await _flow_scheduler.initialize()

    logger.info("[FLOW_SCHEDULER] Setup complete")
    return _flow_scheduler


async def shutdown_flow_scheduler() -> None:
    """플로우 스케줄러 종료"""
    global _flow_scheduler

    if _flow_scheduler:
        await _flow_scheduler.shutdown()

    # 기본 스케줄러 종료
    await scheduler_instance.shutdown()

    logger.info("[FLOW_SCHEDULER] Shutdown complete")


def get_flow_scheduler() -> Optional[FlowScheduler]:
    """플로우 스케줄러 인스턴스 반환"""
    return _flow_scheduler
