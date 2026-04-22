"""
플로우 스케줄러 (action_type 기반)

Features:
- IntervalTrigger 기반 분 단위 스케줄링
- 오토런 등록 시 즉시 실행
- 일시정지/재개 시 남은 시간 보존
- schedule_matrix를 활성화 시간대로 해석
- action_type 기반 Job 등록/관리
- publish/republish는 GP 직접 실행 (모듈 불필요)
- collect/data/generate는 모듈 기반 실행
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
from ..models.blog import Blog, BlogPlatform
from ..models.flow_execution_state import FlowExecutionState
from ..models.autorun_log import AutorunLog
from ..models.user_settings import UserSettings
from ..services.system_settings_service import SystemSettingsService
from ..engine.flow_engine import FlowEngine
from ..core.database import db_manager


async def _use_celery(key: str, db: AsyncSession) -> bool:
    """시스템 설정에서 Celery 플래그 조회."""
    return await SystemSettingsService.get_bool(key, db, default=False)
from ..core.logger import get_logger
from ..services.generation.growth_profile_resolver import GrowthProfileResolver
from ..services.generation.flow_execution_context import StageParams
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
        # Job ID 포맷: flow_{flow_id}_{action_type}
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

        # AI API 키 rate_limited 자동 복구 스케줄러 등록
        self._register_rate_limit_recovery()

        self._initialized = True
        logger.info("[FLOW_SCHEDULER] Initialized with IntervalTrigger")

    def _register_rate_limit_recovery(self) -> None:
        """AI API 키 rate_limited 자동 복구 Job 등록 (15분 간격)"""
        job_id = "ai_key_rate_limit_recovery"

        # 기존 Job 제거
        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            _rate_limit_recovery_callback,
            trigger=IntervalTrigger(minutes=15),
            id=job_id,
            name="AI API 키 rate_limited 자동 복구",
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info("[FLOW_SCHEDULER] AI 키 rate_limit 자동 복구 Job 등록 (15분 간격)")

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

                # GP 설정 조회 (스케줄/간격의 기준)
                gp_settings = self._find_gp_settings(flow)
                blogs = [link.blog for link in flow.blog_links if link.blog]

                # GP 필수 액션 타입 정의
                # generate/prompt/publish/republish는 성장 단계별 전략이 필요하므로 GP 필수
                # collect/data는 단순 수집이므로 GP 없이도 등록 가능
                GP_REQUIRED_ACTIONS = {"generate", "prompt", "publish", "republish"}

                if not gp_settings:
                    logger.info(
                        f"[FLOW_SCHEDULER] GP 모듈 미설정 | FlowID={flow_id} | "
                        f"GP 불필요 액션만 등록 진행"
                    )

                # action_type 기반 등록
                registered_count = 0
                registered_actions = set()
                skipped_actions: list[str] = []

                for link in flow.module_links:
                    module = link.module
                    if not module or not module.module_type:
                        continue

                    module_type_code = module.module_type.code

                    # prompt, growth_profile 모듈은 개별 스케줄링 안 함
                    if module_type_code in ("prompt", "growth_profile"):
                        logger.info(
                            f"[FLOW_SCHEDULER] {module_type_code} 모듈 스킵 | "
                            f"FlowID={flow_id}"
                        )
                        continue

                    # publish, republish는 GP가 직접 처리하므로 여기서 스킵
                    if module_type_code in ("publish", "republish"):
                        continue

                    # GP 필수 액션인데 GP가 없으면 스킵
                    if module_type_code in GP_REQUIRED_ACTIONS and not gp_settings:
                        skipped_actions.append(module_type_code)
                        logger.warning(
                            f"[FLOW_SCHEDULER] GP 필수 액션 스킵 | FlowID={flow_id} | "
                            f"ActionType={module_type_code} | GP 모듈 없음"
                        )
                        continue

                    if module_type_code in registered_actions:
                        logger.info(
                            f"[FLOW_SCHEDULER] 중복 액션 스킵 | FlowID={flow_id} | "
                            f"ActionType={module_type_code}"
                        )
                        continue
                    registered_actions.add(module_type_code)

                    # 실행 상태 조회 또는 생성 (action_type 기반)
                    state = await self._get_or_create_execution_state(
                        db, flow.id, module_type_code
                    )

                    # 간격 계산: GP 있으면 GP 기반, 없으면 모듈 설정 또는 기본값
                    if gp_settings:
                        interval_minutes = self._get_gp_interval(
                            gp_settings, blogs, module_type_code
                        )
                    else:
                        module_settings = module.settings or {}
                        interval_minutes = module_settings.get(
                            "interval_minutes", 60
                        )
                        logger.info(
                            f"[FLOW_SCHEDULER] GP 없음, 폴백 간격 사용 | "
                            f"FlowID={flow_id} | ActionType={module_type_code} | "
                            f"Interval={interval_minutes}분"
                        )

                    # 즉시 실행 + 스케줄 등록
                    if immediate_execution:
                        await self._schedule_immediate_execution(
                            flow, action_type=module_type_code, state=state
                        )
                    else:
                        await self._schedule_next_execution(
                            db, flow, action_type=module_type_code, state=state,
                            interval_minutes=interval_minutes,
                            gp_settings=gp_settings
                        )

                    registered_count += 1
                    logger.info(
                        f"[FLOW_SCHEDULER] 액션 등록 | FlowID={flow_id} | "
                        f"ActionType={module_type_code}"
                    )

                # GP에서 publish/republish 활성화 확인 후 등록
                if gp_settings and gp_settings.get("stages"):
                    for gp_action in ("publish", "republish"):
                        if gp_action in registered_actions:
                            continue
                        # 아무 stage에서든 활성화되어 있는지 확인
                        any_enabled = False
                        for stage in gp_settings["stages"]:
                            action_cfg = stage.get(gp_action, {})
                            if action_cfg.get("enabled", False):
                                any_enabled = True
                                break

                        if any_enabled:
                            registered_actions.add(gp_action)
                            state = await self._get_or_create_execution_state(
                                db, flow.id, gp_action
                            )
                            interval_minutes = self._get_gp_interval(
                                gp_settings, blogs, gp_action
                            )

                            if immediate_execution:
                                await self._schedule_immediate_execution(
                                    flow, action_type=gp_action, state=state
                                )
                            else:
                                await self._schedule_next_execution(
                                    db, flow, action_type=gp_action, state=state,
                                    interval_minutes=interval_minutes,
                                    gp_settings=gp_settings
                                )

                            registered_count += 1
                            logger.info(
                                f"[FLOW_SCHEDULER] GP 액션 등록 | FlowID={flow_id} | "
                                f"ActionType={gp_action}"
                            )

                await db.commit()

                # 등록된 액션이 없는 경우 (모든 액션이 GP 필수인데 GP 없음)
                if registered_count == 0:
                    skip_msg = ", ".join(skipped_actions) if skipped_actions else "없음"
                    logger.warning(
                        f"[FLOW_SCHEDULER] 등록 가능한 액션 없음 | FlowID={flow_id} | "
                        f"GP 필수로 스킵된 액션={skip_msg}"
                    )
                    return {
                        "success": False,
                        "message": (
                            "등록 가능한 액션이 없습니다. "
                            f"GP 필수 액션({skip_msg})은 Growth Profile 모듈이 필요합니다"
                        ),
                        "flow_id": flow_id
                    }

                logger.info(
                    f"[FLOW_SCHEDULER] Flow registered | FlowID={flow_id} | "
                    f"Modules={registered_count} | Immediate={immediate_execution} | "
                    f"Skipped={skipped_actions}"
                )

                # 결과 메시지에 스킵 정보 포함
                message = f"플로우가 등록되었습니다 (모듈 {registered_count}개)"
                if skipped_actions:
                    message += f" (GP 없어 스킵: {', '.join(skipped_actions)})"

                return {
                    "success": True,
                    "message": message,
                    "flow_id": flow_id,
                    "module_count": registered_count,
                    "immediate_execution": immediate_execution,
                    "skipped_actions": skipped_actions
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
        """플로우 일시정지 - 남은 시간 보존 (FES 직접 조회)"""
        try:
            logger.info(f"[FLOW_SCHEDULER] Pausing flow | FlowID={flow_id}")

            async with db_manager.get_session() as db:
                # FES 레코드 직접 조회
                query = select(FlowExecutionState).where(
                    FlowExecutionState.flow_id == flow_id
                )
                result = await db.execute(query)
                states = list(result.scalars().all())

                paused_count = 0
                for state in states:
                    state.pause()
                    paused_count += 1

                # Job 제거
                await self.unregister_flow(flow_id)

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Flow paused | FlowID={flow_id} | "
                    f"PausedActions={paused_count}"
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
        """플로우 재개 - 남은 시간으로 스케줄 복원 (FES 직접 조회)"""
        try:
            logger.info(f"[FLOW_SCHEDULER] Resuming flow | FlowID={flow_id}")

            async with db_manager.get_session() as db:
                # 플로우 조회 (스케줄 등록에 필요)
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    return {
                        "success": False,
                        "message": f"플로우를 찾을 수 없습니다: {flow_id}"
                    }

                # 일시정지된 FES 레코드 직접 조회
                query = select(FlowExecutionState).where(
                    and_(
                        FlowExecutionState.flow_id == flow_id,
                        FlowExecutionState.is_paused == True
                    )
                )
                result = await db.execute(query)
                states = list(result.scalars().all())

                resumed_count = 0
                for state in states:
                    # 재개하고 다음 실행 시간 가져오기
                    next_execution = state.resume()

                    if next_execution:
                        # 남은 시간으로 스케줄 등록
                        await self._schedule_at_time(
                            flow, action_type=state.action_type, state=state,
                            run_time=next_execution
                        )
                    else:
                        # 남은 시간이 없으면 즉시 실행
                        await self._schedule_immediate_execution(
                            flow, action_type=state.action_type, state=state
                        )

                    resumed_count += 1

                await db.commit()

                logger.info(
                    f"[FLOW_SCHEDULER] Flow resumed | FlowID={flow_id} | "
                    f"ResumedActions={resumed_count}"
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
        """플로우 즉시 실행 (수동) - 모듈 방식"""
        started_at = datetime.now()

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

                # 모듈 찾기 (collect/data/generate/prompt만 모듈 필요)
                target_module = None
                if action_type in ("collect", "data", "generate", "prompt"):
                    for link in flow.module_links:
                        module = link.module
                        if module and module.module_type and module.module_type.code == action_type:
                            target_module = module
                            break
                    if not target_module:
                        return {
                            "success": False,
                            "message": f"액션 타입에 해당하는 모듈이 없습니다: {action_type}"
                        }

                # 로깅용 모듈 이름
                module_name = target_module.name if target_module else "GP"

                # 블로그 목록 가져오기
                blogs = [link.blog for link in flow.blog_links if link.blog]

                # GP 설정 조회
                gp_settings = self._find_gp_settings(flow)

                # action_type별 실행
                if action_type == "collect":
                    
                    if await _use_celery("use_celery_utility", db):
                        from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                        dispatcher = get_dispatcher()
                        task_id = dispatcher.dispatch_utility(
                            "tasks.collect_keywords",
                            kwargs={"module_id": target_module.id, "flow_id": flow.id},
                            priority=PRIORITY_NORMAL,
                        )
                        result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                    else:
                        result = await self._execute_collect_module(target_module, db, flow)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module_name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="collect"
                    )

                elif action_type == "publish":
                    result = await self._execute_publish_action(
                        flow, blogs, gp_settings, db
                    )

                elif action_type == "republish":
                    result = await self._execute_republish_action(
                        flow, blogs, gp_settings, db
                    )

                elif action_type == "data":
                    
                    if await _use_celery("use_celery_utility", db):
                        from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                        dispatcher = get_dispatcher()
                        task_id = dispatcher.dispatch_utility(
                            "tasks.transfer_titles",
                            kwargs={"module_id": target_module.id, "flow_id": flow.id},
                            priority=PRIORITY_NORMAL,
                        )
                        result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                    else:
                        result = await self._execute_data_module(target_module, db)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module_name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="data"
                    )

                elif action_type in ("generate", "prompt"):
                    result = await self._execute_generate_module(
                        flow, target_module, blogs, db,
                        gp_settings=gp_settings,
                    )
                else:
                    result = {"success": False, "message": f"지원하지 않는 액션 타입: {action_type}"}

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                result["duration_ms"] = duration_ms

                logger.info(
                    f"[FLOW_SCHEDULER] Manual execution completed | "
                    f"FlowID={flow_id} | Success={result.get('success', False)} | "
                    f"Duration={duration_ms}ms"
                )

                # 실행 상태 업데이트 (action_type 기반)
                state = await self._get_or_create_execution_state(
                    db, flow.id, action_type
                )
                state.record_execution(result.get("success", False))

                # GP 기반 다음 실행 시간 계산
                interval_minutes = self._get_gp_interval(
                    gp_settings, blogs, action_type
                ) if gp_settings else 60

                if gp_settings:
                    _jitter = gp_settings.get("jitter", {})
                    state.calculate_next_execution(
                        interval_minutes=interval_minutes,
                        schedule_matrix=gp_settings.get("schedule_matrix"),
                        jitter_enabled=_jitter.get("enabled", False),
                        jitter_min_percent=_jitter.get("min_percent", -15),
                        jitter_max_percent=_jitter.get("max_percent", 25),
                    )
                else:
                    state.calculate_next_execution(
                        interval_minutes=interval_minutes,
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
        action_type: str,
        blog_id: int = None,
    ) -> FlowExecutionState:
        """실행 상태 조회 또는 생성 (action_type 기반)"""
        query = select(FlowExecutionState).where(
            and_(
                FlowExecutionState.flow_id == flow_id,
                FlowExecutionState.action_type == action_type,
                FlowExecutionState.blog_id == blog_id,
            )
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if not state:
            state = FlowExecutionState(
                flow_id=flow_id,
                action_type=action_type,
                blog_id=blog_id,
            )
            db.add(state)
            await db.flush()

        return state

    async def _get_execution_state(
        self,
        db: AsyncSession,
        flow_id: int,
        action_type: str,
        blog_id: int = None,
    ) -> Optional[FlowExecutionState]:
        """실행 상태 조회 (action_type 기반)"""
        query = select(FlowExecutionState).where(
            and_(
                FlowExecutionState.flow_id == flow_id,
                FlowExecutionState.action_type == action_type,
                FlowExecutionState.blog_id == blog_id,
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _schedule_immediate_execution(
        self,
        flow: Flow,
        action_type: str,
        state: FlowExecutionState
    ) -> None:
        """즉시 실행 스케줄 등록 (action_type 기반)"""
        job_id = self._get_job_id(flow.id, action_type)

        # 즉시 실행 (3초 후) - timezone aware datetime 사용
        run_time = datetime.now(KST) + timedelta(seconds=3)

        self.scheduler.add_job(
            self._execute_module_callback,  # AsyncIOExecutor가 async 함수 직접 지원
            DateTrigger(run_date=run_time, timezone=KST),
            args=[flow.id, action_type],
            id=job_id,
            name=f"Immediate: Flow {flow.name} - Action {action_type}",
            replace_existing=True
        )

        logger.info(
            f"[FLOW_SCHEDULER] Scheduled immediate | FlowID={flow.id} | "
            f"ActionType={action_type} | RunTime={run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _schedule_next_execution(
        self,
        db: AsyncSession,
        flow: Flow,
        action_type: str,
        state: FlowExecutionState,
        interval_minutes: int,
        gp_settings: dict = None,
    ) -> None:
        """다음 실행 시간 계산 및 스케줄 등록 (GP 기반, action_type 사용)"""
        # GP 설정에서 schedule_matrix/jitter 사용 (GP 없으면 기본값)
        if gp_settings:
            schedule_matrix = gp_settings.get("schedule_matrix")
            jitter = gp_settings.get("jitter", {})
            jitter_enabled = jitter.get("enabled", False)
            jitter_min = jitter.get("min_percent", -15)
            jitter_max = jitter.get("max_percent", 25)
        else:
            schedule_matrix = None
            jitter_enabled = False
            jitter_min = -15
            jitter_max = 25

        next_execution = state.calculate_next_execution(
            interval_minutes=interval_minutes,
            schedule_matrix=schedule_matrix,
            jitter_enabled=jitter_enabled,
            jitter_min_percent=jitter_min,
            jitter_max_percent=jitter_max,
        )

        if next_execution:
            await self._schedule_at_time(flow, action_type=action_type, state=state, run_time=next_execution)

    async def _schedule_at_time(
        self,
        flow: Flow,
        action_type: str,
        state: FlowExecutionState,
        run_time: datetime
    ) -> None:
        """특정 시간에 실행 스케줄 등록 (action_type 기반)"""
        job_id = self._get_job_id(flow.id, action_type)

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
            args=[flow.id, action_type],
            id=job_id,
            name=f"Flow {flow.name} - Action {action_type}",
            replace_existing=True
        )

        logger.info(
            f"[FLOW_SCHEDULER] Scheduled | FlowID={flow.id} | "
            f"ActionType={action_type} | RunTime={run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _execute_module_callback(
        self,
        flow_id: int,
        action_type: str
    ) -> None:
        """
        모듈 실행 콜백 (action_type 기반)

        action_type에 따라 적절한 서비스를 호출하여 실행합니다.
        publish/republish는 모듈 없이 GP 직접 실행합니다.
        """
        started_at = datetime.now()

        try:
            logger.info(
                f"[FLOW_SCHEDULER] Executing | FlowID={flow_id} | ActionType={action_type}"
            )

            async with db_manager.get_session() as db:
                # 플로우 조회 (블로그 정보 포함)
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

                # 모듈이 필요한 액션 타입은 모듈 찾기
                module = None
                if action_type in ("collect", "data", "generate", "prompt"):
                    for link in flow.module_links:
                        if link.module and link.module.module_type:
                            if link.module.module_type.code == action_type:
                                module = link.module
                                break

                    if not module and action_type == "generate":
                        # generate는 prompt 모듈로 대체 가능
                        for link in flow.module_links:
                            if link.module and link.module.module_type:
                                if link.module.module_type.code == "prompt":
                                    module = link.module
                                    break

                    if not module:
                        logger.warning(
                            f"[FLOW_SCHEDULER] Module not found for action_type | "
                            f"FlowID={flow_id} | ActionType={action_type}"
                        )
                        return

                # 실행 상태 조회 (action_type 기반)
                state = await self._get_execution_state(db, flow_id, action_type)

                # 동시 실행 가드
                if state and not state.acquire_execution_lock():
                    logger.info(
                        f"[FLOW_SCHEDULER] 이전 실행 진행 중, 스킵 | "
                        f"FlowID={flow_id} | ActionType={action_type}"
                    )
                    await db.commit()
                    return
                # 잠금 상태를 즉시 DB에 반영
                await db.commit()

                # 블로그 목록 가져오기
                blogs = [link.blog for link in flow.blog_links if link.blog]

                # GP 설정 로드 (스케줄/간격의 기준)
                gp_settings = self._find_gp_settings(flow)

                # GP 활성 시간대 체크 (GP가 있는 경우에만)
                if gp_settings:
                    gp_schedule = gp_settings.get("schedule_matrix")
                    if state and not state.is_in_active_window(gp_schedule):
                        logger.info(
                            f"[FLOW_SCHEDULER] GP 비활성 시간대, 재스케줄 | "
                            f"FlowID={flow_id} | ActionType={action_type}"
                        )
                        interval_minutes = self._get_gp_interval(
                            gp_settings, blogs, action_type
                        )
                        await self._schedule_next_execution(
                            db, flow, action_type=action_type, state=state,
                            interval_minutes=interval_minutes,
                            gp_settings=gp_settings
                        )
                        await db.commit()
                        return

                # action_type별 실행
                if action_type == "collect":
                    
                    if await _use_celery("use_celery_utility", db):
                        from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                        dispatcher = get_dispatcher()
                        task_id = dispatcher.dispatch_utility(
                            "tasks.collect_keywords",
                            kwargs={"module_id": module.id, "flow_id": flow_id},
                            priority=PRIORITY_NORMAL,
                        )
                        result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                    else:
                        result = await self._execute_collect_module(module, db, flow)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module.name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="collect"
                    )

                    logger.info(
                        f"[FLOW_SCHEDULER] 수집 모듈 실행 완료 | FlowID={flow_id} | "
                        f"Success={result.get('success', False)} | Duration={duration_ms}ms"
                    )

                elif action_type == "publish":
                    result = await self._execute_publish_action(
                        flow, blogs, gp_settings, db
                    )

                elif action_type == "republish":
                    result = await self._execute_republish_action(
                        flow, blogs, gp_settings, db
                    )

                elif action_type == "data":
                    
                    if await _use_celery("use_celery_utility", db):
                        from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                        dispatcher = get_dispatcher()
                        task_id = dispatcher.dispatch_utility(
                            "tasks.transfer_titles",
                            kwargs={"module_id": module.id, "flow_id": flow_id},
                            priority=PRIORITY_NORMAL,
                        )
                        result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                    else:
                        result = await self._execute_data_module(module, db)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module.name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="data"
                    )

                    logger.info(
                        f"[FLOW_SCHEDULER] 데이터 모듈 실행 완료 | FlowID={flow_id} | "
                        f"Success={result.get('success', False)} | Duration={duration_ms}ms"
                    )
                elif action_type in ("generate", "prompt"):
                    result = await self._execute_generate_module(
                        flow, module, blogs, db,
                        gp_settings=gp_settings,
                    )
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module.name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="generate"
                    )

                    logger.info(
                        f"[FLOW_SCHEDULER] 생성 모듈 실행 완료 | FlowID={flow_id} | "
                        f"Success={result.get('success', False)} | Duration={duration_ms}ms"
                    )
                elif action_type == "growth_profile":
                    logger.info(
                        f"[FLOW_SCHEDULER] GP 모듈은 개별 실행 안 함 | "
                        f"FlowID={flow_id}"
                    )
                    result = {
                        "success": True,
                        "message": "GP 모듈은 컨텍스트 전용",
                        "skipped": True
                    }
                else:
                    result = {"success": False, "message": f"지원하지 않는 액션 타입: {action_type}"}
                    logger.warning(f"[FLOW_SCHEDULER] Unknown action type | {action_type}")

                # 실행 상태 업데이트
                if state:
                    state.record_execution(result.get("success", False))
                    state.release_execution_lock()

                # 다음 스케줄 등록 (성공/실패 무관)
                await self._reschedule_next(
                    db, flow, action_type, state, gp_settings, blogs
                )

                await db.commit()

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                logger.info(
                    f"[FLOW_SCHEDULER] Execution completed | FlowID={flow_id} | "
                    f"ActionType={action_type} | Success={result.get('success', False)} | "
                    f"Duration={duration_ms}ms"
                )

        except Exception as e:
            logger.error(
                f"[FLOW_SCHEDULER] Execution error | FlowID={flow_id} | "
                f"ActionType={action_type} | Error={e}"
            )
            # 잠금 해제 (별도 세션으로 안전하게 처리)
            try:
                await self._release_lock_safely(flow_id, action_type)
            except Exception as unlock_err:
                logger.error(
                    f"[FLOW_SCHEDULER] 잠금 해제 실패 | FlowID={flow_id} | "
                    f"ActionType={action_type} | Error={unlock_err}"
                )
            # 에러 시에도 다음 스케줄을 등록하여 오토런 영구 정지 방지
            await self._recover_schedule(flow_id, action_type)

    async def _reschedule_next(
        self,
        db: AsyncSession,
        flow: Flow,
        action_type: str,
        state: Optional[FlowExecutionState],
        gp_settings: Optional[dict],
        blogs: List[Blog],
        fallback_interval: int = 0,
    ) -> None:
        """다음 실행 스케줄 등록 (성공/실패 무관하게 항상 호출)

        기존 try 블록 내 스케줄 등록 로직(920~942행)을 추출한 메서드.
        fallback_interval이 지정되면 GP 간격 대신 해당 값(분)을 사용합니다.

        Args:
            db: DB 세션
            flow: 플로우 객체
            action_type: 액션 타입
            state: 실행 상태 (None이면 스케줄 등록 생략)
            gp_settings: GP 설정 dict
            blogs: 플로우에 연결된 블로그 목록
            fallback_interval: 폴백 간격(분). 0이면 GP 기반 계산 사용.
        """
        if not state:
            return

        # 간격 결정: 폴백 > GP > 모듈 settings > 기본값(60분)
        if fallback_interval > 0:
            interval_minutes = fallback_interval
        elif gp_settings:
            interval_minutes = self._get_gp_interval(
                gp_settings, blogs, action_type
            )
        else:
            # GP 없는 경우: 모듈 자체 settings에서 interval_minutes 조회
            interval_minutes = self._get_module_fallback_interval(
                flow, action_type
            )

        # GP jitter 설정 적용
        if gp_settings:
            _jitter = gp_settings.get("jitter", {})
            next_execution = state.calculate_next_execution(
                interval_minutes=interval_minutes,
                schedule_matrix=gp_settings.get("schedule_matrix"),
                jitter_enabled=_jitter.get("enabled", False),
                jitter_min_percent=_jitter.get("min_percent", -15),
                jitter_max_percent=_jitter.get("max_percent", 25),
            )
        else:
            next_execution = state.calculate_next_execution(
                interval_minutes=interval_minutes,
            )

        if next_execution:
            await self._schedule_at_time(
                flow, action_type=action_type, state=state,
                run_time=next_execution
            )

    async def _release_lock_safely(
        self,
        flow_id: int,
        action_type: str,
    ) -> None:
        """별도 세션으로 실행 잠금을 안전하게 해제합니다.

        예외 핸들러에서 기존 세션이 유효하지 않을 수 있으므로
        새 세션을 열어 잠금을 해제합니다.

        Args:
            flow_id: 플로우 ID
            action_type: 액션 타입
        """
        async with db_manager.get_session() as db:
            state = await self._get_execution_state(
                db, flow_id, action_type
            )
            if state and state.is_running:
                state.release_execution_lock()
                await db.commit()
                logger.info(
                    f"[FLOW_SCHEDULER] 잠금 안전 해제 완료 | "
                    f"FlowID={flow_id} | ActionType={action_type}"
                )

    async def _recover_schedule(
        self,
        flow_id: int,
        action_type: str,
    ) -> None:
        """에러 발생 시 복구 스케줄링

        실행 콜백에서 예외 발생 시 호출되어, 연속 실패를 기록하고
        다음 실행 스케줄을 등록합니다.
        연속 5회 이상 실패 시 해당 액션의 오토런을 일시정지합니다.

        Args:
            flow_id: 플로우 ID
            action_type: 액션 타입
        """
        max_consecutive_failures = 5
        fallback_interval_minutes = 15

        try:
            async with db_manager.get_session() as db:
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow:
                    logger.warning(
                        f"[FLOW_SCHEDULER] 복구 스케줄링 - 플로우 없음 | FlowID={flow_id}"
                    )
                    return

                state = await self._get_execution_state(db, flow_id, action_type)
                if not state:
                    logger.warning(
                        f"[FLOW_SCHEDULER] 복구 스케줄링 - 실행 상태 없음 | "
                        f"FlowID={flow_id} | ActionType={action_type}"
                    )
                    return

                # 잠금 해제 + 실패 기록
                state.release_execution_lock()
                state.record_execution(False)

                # 연속 실패 임계값 초과 시 일시정지
                if (state.consecutive_failures or 0) >= max_consecutive_failures:
                    state.is_paused = True
                    state.paused_at = datetime.now(KST)
                    logger.warning(
                        f"[FLOW_SCHEDULER] 연속 실패 {state.consecutive_failures}회 "
                        f"→ 오토런 일시정지 | FlowID={flow_id} | ActionType={action_type}"
                    )
                else:
                    # 폴백 간격으로 다음 실행 등록
                    gp_settings = self._find_gp_settings(flow)
                    blogs = [link.blog for link in flow.blog_links if link.blog]
                    await self._reschedule_next(
                        db, flow, action_type, state, gp_settings, blogs,
                        fallback_interval=fallback_interval_minutes,
                    )
                    logger.info(
                        f"[FLOW_SCHEDULER] 에러 복구 스케줄 등록 | FlowID={flow_id} | "
                        f"ActionType={action_type} | "
                        f"ConsecutiveFailures={state.consecutive_failures} | "
                        f"FallbackInterval={fallback_interval_minutes}분"
                    )

                await db.commit()

        except Exception as inner_e:
            logger.error(
                f"[FLOW_SCHEDULER] 복구 스케줄링 실패 | FlowID={flow_id} | "
                f"ActionType={action_type} | Error={inner_e}"
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

    def _get_job_id(self, flow_id: int, action_type: str) -> str:
        """Job ID 생성 (action_type 기반)"""
        return f"{self._job_prefix}{flow_id}_{action_type}"

    # ===========================================
    # GP(Growth Profile) 기반 스케줄 헬퍼
    # ===========================================

    def _get_module_fallback_interval(
        self,
        flow: Flow,
        action_type: str,
        default_minutes: int = 60
    ) -> int:
        """
        GP가 없을 때 모듈 자체 settings에서 폴백 간격(분) 조회

        모듈의 settings.interval_minutes 값을 우선 사용하고,
        없으면 default_minutes를 반환합니다.

        Args:
            flow: 모듈 링크가 로드된 플로우
            action_type: 액션 타입 코드
            default_minutes: 기본 간격(분)

        Returns:
            실행 간격(분)
        """
        for link in flow.module_links:
            module = link.module
            if not module or not module.module_type:
                continue
            if module.module_type.code == action_type:
                module_settings = module.settings or {}
                interval = module_settings.get("interval_minutes")
                if interval and isinstance(interval, (int, float)) and interval > 0:
                    logger.debug(
                        f"[FLOW_SCHEDULER] 모듈 폴백 간격 | "
                        f"ActionType={action_type} | Interval={int(interval)}분"
                    )
                    return int(interval)
                break
        logger.debug(
            f"[FLOW_SCHEDULER] 기본 폴백 간격 사용 | "
            f"ActionType={action_type} | Interval={default_minutes}분"
        )
        return default_minutes

    def _find_gp_settings(self, flow: Flow) -> Optional[dict]:
        """
        플로우에서 Growth Profile 모듈의 settings 추출

        Args:
            flow: 모듈 링크가 로드된 플로우

        Returns:
            GP settings dict (stages 포함) 또는 None
        """
        for link in flow.module_links:
            module = link.module
            if not module or not module.module_type:
                continue
            if module.module_type.code == "growth_profile":
                settings = module.settings or {}
                if settings.get("stages"):
                    return settings
        return None

    def _get_gp_interval(
        self,
        gp_settings: dict,
        blogs: list,
        module_type_code: str,
        default_minutes: int = 60
    ) -> int:
        """
        GP 설정에서 모듈 타입별 최소 실행 간격(분) 계산

        블로그별 포스트 수 → GP 스테이지 결정 → 해당 모듈의 computed_interval.
        여러 블로그가 있으면 가장 짧은 간격을 사용.

        Args:
            gp_settings: GP 모듈의 settings dict
            blogs: 플로우에 연결된 블로그 목록
            module_type_code: 모듈 타입 코드 (generate, republish 등)
            default_minutes: GP 설정이 없을 때 기본 간격

        Returns:
            실행 간격(분)
        """
        if not gp_settings:
            return default_minutes

        stages = gp_settings.get("stages", [])
        if not stages:
            return default_minutes

        schedule_matrix = gp_settings.get("schedule_matrix")
        active_hours = GrowthProfileResolver.count_active_hours(schedule_matrix)

        min_interval = None
        for blog in blogs:
            post_count = blog.total_post_count or 0
            stage_dict = GrowthProfileResolver.resolve_stage_for_blog(
                post_count, stages
            )
            if not stage_dict:
                continue

            stage_params = StageParams.from_stage_dict(stage_dict, active_hours)

            # module_type_code → 해당 모듈 파라미터
            module_params = None
            if module_type_code in ("generate", "prompt"):
                module_params = stage_params.generate
            elif module_type_code == "republish":
                module_params = stage_params.republish
            elif module_type_code == "publish":
                module_params = stage_params.publish

            if (
                module_params
                and module_params.enabled
                and module_params.computed_interval
            ):
                if min_interval is None or module_params.computed_interval < min_interval:
                    min_interval = module_params.computed_interval

        result = min_interval or default_minutes
        logger.debug(
            f"[FLOW_SCHEDULER] GP 간격 계산 | type={module_type_code} | "
            f"interval={result}분 | blogs={len(blogs)}"
        )
        return result

    # ===========================================
    # 모듈 방식 실행 메서드 (flows_execute.py와 동일)
    # ===========================================

    async def _execute_collect_module(
        self,
        module: Module,
        db: AsyncSession,
        flow: Flow
    ) -> Dict[str, Any]:
        """
        수집 모듈 실행 (flows_execute.py와 동일한 모듈 방식)

        KeywordCollectorService를 사용하여 키워드/제목 수집을 수행합니다.
        """
        from app.services.keyword_collector_service import KeywordCollectorService

        try:
            settings = module.settings or {}

            # 수집 유형 확인 (keyword, title, both)
            collect_type = settings.get("collect_type", "both")

            # 키워드 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
            keyword_sources = []
            if settings.get("source_google_trends", False):
                keyword_sources.append("google_trends")
            if settings.get("source_naver_datalab", False):
                keyword_sources.append("naver_datalab")
            if settings.get("source_naver_ads", False):
                keyword_sources.append("naver_ads")

            # 제목 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
            title_sources = []
            if settings.get("source_naver_news", False):
                title_sources.append("naver_news")
            if settings.get("source_google_news", False):
                title_sources.append("google_news")
            if settings.get("source_naver_webdoc", False):
                title_sources.append("naver_webdoc")

            # collect_type에 따라 소스 필터링
            sources = []
            if collect_type == "keyword":
                sources = keyword_sources
            elif collect_type == "title":
                sources = title_sources
            else:  # both
                sources = keyword_sources + title_sources

            if not sources:
                return {
                    "success": False,
                    "message": f"수집 소스가 설정되지 않았습니다 (타입: {collect_type})",
                    "collected_count": 0
                }

            logger.info(
                f"[FLOW_SCHEDULER] 수집 모듈={module.name} | 타입={collect_type} | 소스={sources}"
            )

            # 사용자 설정 조회
            query = select(UserSettings).where(UserSettings.user_id == flow.user_id)
            result = await db.execute(query)
            user_settings = result.scalar_one_or_none()

            if not user_settings:
                return {
                    "success": False,
                    "message": "사용자 설정을 찾을 수 없습니다",
                    "collected_count": 0
                }

            # KeywordCollectorService를 사용하여 자동 수집
            collector = KeywordCollectorService(db=db, settings=user_settings)

            # 수집 수량 제한 적용 (키워드/제목 분리)
            keyword_limit = settings.get("keyword_collect_limit", 100)
            keyword_limit = max(10, min(1000, keyword_limit))
            # title_limit: 0 또는 None이면 무제한
            title_limit_setting = settings.get("title_collect_limit", 0)
            title_limit = None if title_limit_setting == 0 else title_limit_setting

            # 연관검색 확장 옵션 (기본값 True)
            enable_related_search = settings.get("enable_related_search", True)

            # 수집 유형 옵션 (일반/대량) - 기본값 False (명시적으로 활성화해야 동작)
            enable_normal_collect = settings.get("enable_normal_collect", False)
            enable_bulk_collect = settings.get("enable_bulk_collect", False)
            bulk_collect_delay = settings.get("bulk_collect_delay", 0.5)
            bulk_urls_per_cycle = settings.get("bulk_urls_per_cycle", 3)

            logger.info(
                f"[FLOW_SCHEDULER] 옵션 | keyword_limit={keyword_limit}, "
                f"title_limit={'무제한' if not title_limit else title_limit}, "
                f"enable_related_search={enable_related_search}, "
                f"enable_normal_collect={enable_normal_collect}, enable_bulk_collect={enable_bulk_collect}"
            )

            # 선택된 소스에서만 수집 (수량 제한 분리 적용)
            collect_result = await collector.collect_all(
                sources=sources,
                keyword_limit=keyword_limit,
                title_limit=title_limit,
                enable_related_search=enable_related_search,
                enable_normal_collect=enable_normal_collect,
                enable_bulk_collect=enable_bulk_collect,
                bulk_collect_delay=bulk_collect_delay,
                bulk_urls_per_cycle=bulk_urls_per_cycle
            )

            if collect_result.get("success"):
                total_collected = collect_result.get("total_collected", 0)
                total_saved = collect_result.get("total_saved", 0)
                results_detail = collect_result.get("results", {})

                # 각 소스별 결과 메시지 생성
                source_messages = []
                for source, src_result in results_detail.items():
                    if src_result.get("success"):
                        source_messages.append(
                            f"{source}: {src_result.get('collected', 0)}개 수집, {src_result.get('saved', 0)}개 저장"
                        )
                    else:
                        source_messages.append(
                            f"{source}: 오류 - {src_result.get('error', '알 수 없음')}"
                        )

                # 키워드 추출 실행 (설정에서 enable_keyword_extraction이 활성화된 경우)
                extraction_result = None
                if settings.get("enable_keyword_extraction", False):
                    try:
                        from app.services.keyword_extractor_service import KeywordExtractorService

                        extraction_method = settings.get("keyword_extraction_method", "all")
                        extraction_title_limit = settings.get("keyword_extraction_title_limit", 100)
                        extraction_keyword_limit = settings.get("keyword_extraction_limit", 50)

                        logger.info(
                            f"[FLOW_SCHEDULER] 키워드 추출 시작 | method={extraction_method}, "
                            f"title_limit={extraction_title_limit}, keyword_limit={extraction_keyword_limit}"
                        )

                        extractor = KeywordExtractorService(db)
                        extraction_result = await extractor.extract_and_save_keywords(
                            title_limit=extraction_title_limit,
                            keyword_limit=extraction_keyword_limit,
                            method=extraction_method,
                            title_status="new"
                        )

                        if extraction_result.get("success"):
                            extracted_count = extraction_result.get("keywords_saved", 0)
                            source_messages.append(f"키워드 추출: {extracted_count}개 저장")
                            logger.info(f"[FLOW_SCHEDULER] 키워드 추출 완료 | 저장={extracted_count}개")
                        else:
                            logger.warning(f"[FLOW_SCHEDULER] 키워드 추출 실패: {extraction_result.get('error', '알 수 없음')}")

                    except Exception as extract_error:
                        logger.error(f"[FLOW_SCHEDULER] 키워드 추출 오류: {extract_error}")

                return {
                    "success": True,
                    "message": f"총 {total_collected}개 수집, {total_saved}개 저장 ({', '.join(source_messages)})",
                    "collected_count": total_collected,
                    "saved_count": total_saved,
                    "sources": sources,
                    "collect_type": collect_type,
                    "results": results_detail,
                    "extraction_result": extraction_result
                }
            else:
                return {
                    "success": False,
                    "message": collect_result.get("error", "수집 실패"),
                    "collected_count": 0,
                    "sources": sources,
                    "collect_type": collect_type
                }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] 수집 실패 | module={module.name} | error={e}")
            return {
                "success": False,
                "message": str(e),
                "collected_count": 0
            }

    async def _execute_generate_module(
        self,
        flow: Flow,
        generate_module: Module,
        blogs: List[Blog],
        db: AsyncSession,
        gp_settings: dict = None,
    ) -> Dict[str, Any]:
        """
        생성 모듈 실행 (GP 기반)

        동일 플로우의 prompt 모듈들을 찾아
        FlowGenerateExecutor로 블로그별 글 생성을 실행합니다.

        Args:
            flow: 플로우
            generate_module: generate 타입 모듈 (스케줄러 소유)
            blogs: 플로우에 연결된 블로그 목록
            db: DB 세션
            gp_settings: GP 설정 (stage_params 생성용)
        """
        from app.services.generation.flow_generate_executor import FlowGenerateExecutor

        try:
            if not blogs:
                return {
                    "success": False,
                    "message": "플로우에 연결된 블로그가 없습니다"
                }

            # 동일 플로우 내 prompt 모듈 찾기
            prompt_modules = []
            for link in flow.module_links:
                if not link.module or not link.module.module_type:
                    continue
                if link.module.module_type.code == "prompt":
                    prompt_modules.append(link.module)

            if not prompt_modules:
                return {
                    "success": False,
                    "message": "플로우에 prompt 모듈이 없습니다"
                }

            logger.info(
                f"[FLOW_SCHEDULER] 생성 모듈 실행 | "
                f"prompt 모듈 {len(prompt_modules)}개 × "
                f"블로그 {len(blogs)}개"
            )

            # GP 기반 블로그별 StageParams 매핑
            blog_stage_map: Dict[int, StageParams] = {}
            if gp_settings:
                stages = gp_settings.get("stages", [])
                schedule_matrix = gp_settings.get("schedule_matrix")
                active_hours = GrowthProfileResolver.count_active_hours(
                    schedule_matrix
                )
                for blog in blogs:
                    post_count = blog.total_post_count or 0
                    stage_dict = GrowthProfileResolver.resolve_stage_for_blog(
                        post_count, stages
                    )
                    if stage_dict:
                        blog_stage_map[blog.id] = StageParams.from_stage_dict(
                            stage_dict, active_hours
                        )

            gen_executor = FlowGenerateExecutor(db, flow.user_id)

            total_success = 0
            total_skipped = 0
            total_failed = 0

            for prompt_module in prompt_modules:
                for blog in blogs:
                    # GP 컨텍스트에서 블로그별 StageParams 조회
                    stage_params = blog_stage_map.get(blog.id)

                    # generate.enabled 체크
                    if stage_params and not stage_params.generate.enabled:
                        logger.info(
                            f"[FLOW_SCHEDULER] 생성 비활성 | blog={blog.name} | "
                            f"stage={stage_params.stage_name}"
                        )
                        total_skipped += 1
                        continue

                    try:
                        blog_start = datetime.now()
                        # Celery 기능 플래그 체크
                        
                        if await _use_celery("use_celery_generation", db):
                            from app.core.task_dispatcher import get_dispatcher, PRIORITY_NORMAL
                            dispatcher = get_dispatcher()
                            try:
                                task_id = dispatcher.dispatch_generation(
                                    blog_id=blog.id,
                                    module_id=prompt_module.id,
                                    title_id=0,
                                    priority=PRIORITY_NORMAL,
                                    flow_id=flow.id,
                                )
                                result = {"success": True, "message": f"Celery 큐 등록: {task_id}"}
                                logger.info(
                                    f"[FLOW_SCHEDULER] Celery 디스패치 성공 | blog={blog.name} | task_id={task_id}"
                                )
                            except Exception as e:
                                result = {"success": False, "message": f"Celery 디스패치 실패: {e}"}
                                logger.warning(
                                    f"[FLOW_SCHEDULER] Celery 디스패치 실패 | blog={blog.name} | {e}"
                                )
                        else:
                            result = await gen_executor.execute_for_blog(
                                prompt_module, blog,
                                stage_params=stage_params,
                            )
                        blog_duration = int(
                            (datetime.now() - blog_start).total_seconds() * 1000
                        )

                        if result.get("success"):
                            if result.get("skipped"):
                                total_skipped += 1
                            else:
                                total_success += 1
                        else:
                            total_failed += 1

                        # 블로그별 AutorunLog 저장
                        await self._save_autorun_log(
                            db=db,
                            user_id=flow.user_id,
                            flow_id=flow.id,
                            flow_name=flow.name,
                            module_name=prompt_module.name,
                            blog_name=blog.name,
                            result=result,
                            duration_ms=blog_duration,
                            action="generate"
                        )

                    except Exception as e:
                        total_failed += 1
                        logger.error(
                            f"[FLOW_SCHEDULER] 생성 오류 | "
                            f"prompt={prompt_module.name} | "
                            f"blog={blog.name} | error={e}"
                        )

            msg = (
                f"생성 {total_success} / 스킵 {total_skipped} / "
                f"실패 {total_failed}"
            )
            logger.info(f"[FLOW_SCHEDULER] 생성 모듈 결과 | {msg}")

            return {
                "success": total_failed == 0,
                "message": msg,
                "generated": total_success,
                "skipped": total_skipped,
                "failed": total_failed,
            }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] 생성 모듈 오류: {e}")
            return {
                "success": False,
                "message": str(e),
                "generated": 0
            }

    async def _execute_data_module(
        self,
        module: Module,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        데이터 모듈 실행 (제목 이동 등)

        모듈 settings에 저장된 옵션을 사용하여 TitleTransferService를 호출합니다.
        """
        from app.services.title_transfer_service import TitleTransferService

        try:
            settings = module.settings or {}

            # 설정 값 추출
            transfer_mode = settings.get("transfer_mode", "auto")

            # 실행 조건
            execution = settings.get("execution", {})
            max_titles = execution.get("max_titles_per_run", 100)
            min_titles = execution.get("min_titles_required", 1)

            # 그룹화 설정
            auto_group = settings.get("auto_group", True)
            threshold = settings.get("similarity_threshold", 75)

            # 필터 설정
            filter_opts = settings.get("filter", {})
            categories = filter_opts.get("categories", [])

            logger.info(
                f"[FLOW_SCHEDULER] 데이터 모듈 실행 | module={module.name} | "
                f"mode={transfer_mode} | max={max_titles} | min={min_titles} | "
                f"auto_group={auto_group} | threshold={threshold}"
            )

            # TitleTransferService 생성 (threshold는 0-100 범위)
            service = TitleTransferService(db=db, threshold=threshold)

            # 이동 가능한 제목 수 확인
            from sqlalchemy import func
            from app.models.title import TempTitle

            query = select(func.count(TempTitle.id)).where(
                TempTitle.status.in_(["new", "categorized"])
            )

            if transfer_mode == "auto":
                query = query.where(TempTitle.topic_id.isnot(None))

            if categories:
                query = query.where(TempTitle.topic_id.in_(categories))

            result = await db.execute(query)
            available_count = result.scalar() or 0

            logger.info(f"[FLOW_SCHEDULER] 이동 가능 제목 수: {available_count} | 최소 조건: {min_titles}")

            if available_count < min_titles:
                return {
                    "success": True,
                    "message": f"이동 가능한 제목({available_count}개)이 최소 조건({min_titles}개)보다 적어 스킵",
                    "moved": 0,
                    "grouped": 0,
                    "duplicates": 0,
                    "skipped_reason": "min_titles_not_met"
                }

            # 이동 대상 제목 ID 조회
            id_query = select(TempTitle.id).where(
                TempTitle.status.in_(["new", "categorized"])
            )

            if transfer_mode == "auto":
                id_query = id_query.where(TempTitle.topic_id.isnot(None))

            if categories:
                id_query = id_query.where(TempTitle.topic_id.in_(categories))

            id_query = id_query.limit(max_titles)

            id_result = await db.execute(id_query)
            temp_ids = [row[0] for row in id_result.all()]

            if not temp_ids:
                return {
                    "success": True,
                    "message": "이동할 제목이 없습니다",
                    "moved": 0,
                    "grouped": 0,
                    "duplicates": 0
                }

            logger.info(f"[FLOW_SCHEDULER] 이동 대상 제목 수: {len(temp_ids)}")

            # 제목 이동 실행
            transfer_result = await service.move_to_main(temp_ids, auto_group=auto_group)

            moved = transfer_result.get("moved", 0)
            grouped = transfer_result.get("grouped", 0)
            duplicates = transfer_result.get("duplicates", 0)
            errors = transfer_result.get("errors", [])

            logger.info(
                f"[FLOW_SCHEDULER] 제목 이동 완료 | moved={moved} | grouped={grouped} | "
                f"duplicates={duplicates} | errors={len(errors)}"
            )

            return {
                "success": True,
                "message": f"제목 이동 완료: {moved}개 이동, {grouped}개 그룹화, {duplicates}개 중복",
                "moved": moved,
                "grouped": grouped,
                "duplicates": duplicates,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] 데이터 모듈 실패 | module={module.name} | error={e}")
            import traceback
            logger.error(f"[FLOW_SCHEDULER] 스택 트레이스: {traceback.format_exc()}")
            return {
                "success": False,
                "message": str(e),
                "moved": 0,
                "grouped": 0,
                "duplicates": 0
            }

    async def _execute_publish_action(
        self,
        flow: Flow,
        blogs: List[Blog],
        gp_settings: Optional[dict],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        발행 액션 실행 (GP 기반, 모듈 없이 직접 실행)

        Args:
            flow: 플로우
            blogs: 연결된 블로그 목록
            gp_settings: GP 설정
            db: DB 세션

        Returns:
            실행 결과
        """
        if not blogs:
            return {"success": False, "message": "블로그가 연결되지 않았습니다"}

        from ..services.generation.warmup_manager import WarmupManager
        from ..services.generation.publisher import Publisher
        from ..services.generation.publisher_pipeline import PublisherPipeline
        from ..services.generation.flow_execution_context import FlowExecutionContext
        from ..services.generation.growth_profile_resolver import GrowthProfileResolver

        gp_context = None
        if gp_settings:
            gp_context = GrowthProfileResolver.build_execution_context(
                flow.id, gp_settings,
                {b.id: b.total_post_count or 0 for b in blogs}
            )

        warmup_mgr = WarmupManager(db)
        publisher = Publisher(db)
        pipeline = PublisherPipeline(db)

        # GP 모듈 이름 찾기
        gp_module_name = "GP 발행"
        for _link in flow.module_links:
            _m = _link.module
            if _m and _m.module_type and _m.module_type.code == "growth_profile":
                gp_module_name = _m.name
                break

        success_count = 0
        fail_count = 0
        for blog in blogs:
            blog_start = datetime.now()
            try:
                stage_params = gp_context.get_stage_for_blog(blog.id) if gp_context else None
                if not stage_params or not stage_params.publish.enabled:
                    continue

                # 워밍업 체크
                warmup_settings = gp_settings.get("warmup", {}) if gp_settings else {}
                active_hours = GrowthProfileResolver.count_active_hours(
                    gp_settings.get("schedule_matrix")) if gp_settings else 16
                warmup_status = await warmup_mgr.check_warmup(
                    blog.id, warmup_settings, active_hours)

                if warmup_status.is_active and not warmup_status.can_publish:
                    continue

                # 발행 (항상 1개)
                

                if await _use_celery("use_celery_publish", db):
                    # Celery 워커에 발행 위임
                    from app.core.task_dispatcher import (
                        get_dispatcher, PRIORITY_NORMAL,
                    )
                    dispatcher = get_dispatcher()
                    try:
                        task_id = dispatcher.dispatch_publish(
                            blog_id=blog.id,
                            post_id=0,
                            priority=PRIORITY_NORMAL,
                            flow_id=flow.id,
                        )
                        pub_result = {
                            "success": True,
                            "message": f"Celery 큐 등록: {task_id}",
                        }
                        logger.info(
                            f"[SCHED:PUBLISH] Celery 디스패치 | "
                            f"blog={blog.name} | task={task_id}"
                        )
                    except Exception as e:
                        pub_result = {
                            "success": False,
                            "message": f"Celery 디스패치 실패: {e}",
                        }
                        logger.error(
                            f"[SCHED:PUBLISH] Celery 디스패치 오류 | "
                            f"blog={blog.name} | {e}"
                        )
                else:
                    pub_result = await publisher.publish_for_blog(
                        blog, warmup_status,
                    )

                if pub_result.get("success") and pub_result.get("crawled_post"):
                    crawled_post = pub_result["crawled_post"]
                    pipeline_result = await pipeline.publish_post(crawled_post, blog)

                    if pipeline_result.get("success"):
                        await publisher.complete_publish(blog, crawled_post, stage_params)
                        success_count += 1
                    else:
                        fail_count += 1
                elif pub_result.get("skipped"):
                    pass  # 스킵
                else:
                    fail_count += 1

                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                await self._save_autorun_log(
                    db=db, user_id=flow.user_id, flow_id=flow.id,
                    flow_name=flow.name, module_name=gp_module_name,
                    blog_name=blog.name, result=pub_result,
                    duration_ms=blog_duration, action="publish")

            except Exception as e:
                fail_count += 1
                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                await self._save_autorun_log(
                    db=db, user_id=flow.user_id, flow_id=flow.id,
                    flow_name=flow.name, module_name=gp_module_name,
                    blog_name=blog.name,
                    result={"success": False, "message": str(e)},
                    duration_ms=blog_duration, action="publish")

        return {
            "success": fail_count == 0,
            "message": f"발행 성공 {success_count}/{len(blogs)}, 실패 {fail_count}/{len(blogs)}"
        }

    async def _execute_republish_action(
        self,
        flow: Flow,
        blogs: List[Blog],
        gp_settings: Optional[dict],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        재발행 액션 실행 (GP 기반, 모듈 없이 직접 실행)

        Args:
            flow: 플로우
            blogs: 연결된 블로그 목록
            gp_settings: GP 설정
            db: DB 세션

        Returns:
            실행 결과
        """
        if not blogs:
            return {"success": False, "message": "블로그가 연결되지 않았습니다"}

        gp_context = None
        if gp_settings:
            gp_context = GrowthProfileResolver.build_execution_context(
                flow.id, gp_settings,
                {b.id: b.total_post_count or 0 for b in blogs}
            )

        # GP 모듈 이름 찾기
        gp_module_name = "GP 재발행"
        for _link in flow.module_links:
            _m = _link.module
            if _m and _m.module_type and _m.module_type.code == "growth_profile":
                gp_module_name = _m.name
                break

        success_count = 0
        fail_count = 0
        for blog in blogs:
            blog_start = datetime.now()
            try:
                stage_params = gp_context.get_stage_for_blog(blog.id) if gp_context else None
                if not stage_params or not stage_params.republish.enabled:
                    continue

                

                if await _use_celery("use_celery_publish", db):
                    # Celery 워커에 재발행 위임
                    from app.core.task_dispatcher import (
                        get_dispatcher, PRIORITY_NORMAL,
                    )
                    dispatcher = get_dispatcher()
                    try:
                        task_id = dispatcher.dispatch_republish(
                            blog_id=blog.id,
                            priority=PRIORITY_NORMAL,
                            flow_id=flow.id,
                        )
                        blog_result = {
                            "success": True,
                            "message": f"Celery 큐 등록: {task_id}",
                        }
                        logger.info(
                            f"[SCHED:REPUBLISH] Celery 디스패치 | "
                            f"blog={blog.name} | task={task_id}"
                        )
                    except Exception as e:
                        blog_result = {
                            "success": False,
                            "message": f"Celery 디스패치 실패: {e}",
                        }
                        logger.error(
                            f"[SCHED:REPUBLISH] Celery 디스패치 오류 | "
                            f"blog={blog.name} | {e}"
                        )
                else:
                    blog_result = await self._execute_republish_for_blog(blog)

                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)

                await self._save_autorun_log(
                    db=db, user_id=flow.user_id, flow_id=flow.id,
                    flow_name=flow.name, module_name=gp_module_name,
                    blog_name=blog.name, result=blog_result,
                    duration_ms=blog_duration, action="republish")

                if blog_result.get("success"):
                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                await self._save_autorun_log(
                    db=db, user_id=flow.user_id, flow_id=flow.id,
                    flow_name=flow.name, module_name=gp_module_name,
                    blog_name=blog.name,
                    result={"success": False, "message": str(e)},
                    duration_ms=blog_duration, action="republish")

        return {
            "success": fail_count == 0,
            "message": f"재발행 성공 {success_count}/{len(blogs)}, 실패 {fail_count}/{len(blogs)}"
        }

    async def _execute_republish_for_blog(self, blog: Blog) -> Dict[str, Any]:
        """
        블로그에 재발행 수행 (flows_execute.py와 동일)
        """
        from app.services.wordpress_service import WordPressRepublishService
        from app.services.blogger_service import BloggerRepublishService

        if blog.platform == BlogPlatform.WORDPRESS:
            service = WordPressRepublishService()
            return await service.republish(blog)
        elif blog.platform == BlogPlatform.BLOGGER:
            if not blog.google_credential:
                return {
                    "success": False,
                    "message": "Google 인증 정보가 없습니다"
                }
            service = BloggerRepublishService()
            return await service.republish(blog, blog.google_credential)
        else:
            return {
                "success": False,
                "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
            }

    async def _save_autorun_log(
        self,
        db: AsyncSession,
        user_id: int,
        flow_id: int,
        flow_name: str,
        module_name: str,
        blog_name: str,
        result: Dict[str, Any],
        duration_ms: int,
        action: str = "republish"
    ) -> None:
        """AutorunLog DB 저장 (flows_execute.py와 동일)"""
        try:
            is_success = result.get("success", False)
            status = "success" if is_success else "failed"
            post_title = result.get("post_title", "")

            # action_time 포맷팅
            action_time = None
            new_date = result.get("new_date")
            if new_date:
                try:
                    if "T" in new_date:
                        parsed = datetime.fromisoformat(new_date.replace("Z", "+00:00"))
                        action_time = parsed.strftime("%Y/%m/%d/%H:%M:%S")
                    else:
                        action_time = new_date
                except Exception:
                    action_time = datetime.now().strftime("%Y/%m/%d/%H:%M:%S")
            else:
                action_time = datetime.now().strftime("%Y/%m/%d/%H:%M:%S")

            # 메시지: 성공/실패 모두 result["message"] 사용
            log_message = result.get("message", "")

            # AutorunLog 생성
            log = AutorunLog.create_execution_log(
                user_id=user_id,
                flow_id=flow_id,
                action=action,
                status=status,
                flow_name=flow_name,
                module_name=module_name,
                blog_name=blog_name,
                post_title=post_title,
                action_time=action_time,
                duration_ms=duration_ms,
                message=log_message
            )

            db.add(log)
            # commit은 호출자에서 처리
            logger.info(f"[FLOW_SCHEDULER] AutorunLog 저장 | blog={blog_name} | status={status}")

        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] AutorunLog 저장 실패 | blog={blog_name} | error={e}")

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
                            "action_type": state.action_type,
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


def _rate_limit_recovery_callback() -> None:
    """AI API 키 rate_limited 자동 복구 콜백 (동기 래퍼)"""
    import asyncio

    async def _do_recovery():
        from ..services.ai_key_manager import AIKeyManager
        async with db_manager.session() as db:
            key_manager = AIKeyManager(db, user_id=1)
            count = await key_manager.reset_rate_limited_keys()
            if count > 0:
                logger.info(
                    f"[RATE_LIMIT_RECOVERY] {count}개 키 자동 복구 완료"
                )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_recovery())
        else:
            loop.run_until_complete(_do_recovery())
    except Exception as e:
        logger.error(f"[RATE_LIMIT_RECOVERY] 복구 실패: {e}")
