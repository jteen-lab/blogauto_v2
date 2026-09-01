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
from ..models.flow_execution_state import FlowExecutionState, MIN_EXECUTION_GAP
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
from ..services.generation.post_count_helper import build_effective_post_counts
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

        # 애드센스 사이트 상태 정기 동기화 등록
        self._register_adsense_sync()
        self._register_model_catalog_sync()

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

    def _register_adsense_sync(self) -> None:
        """애드센스 사이트 상태 동기화 Job 등록 (12시간 간격).

        승인 여부는 자주 바뀌지 않으므로 하루 두 번이면 충분하다. 즉시 확인이
        필요하면 설정 화면의 '지금 상태 확인' 버튼을 쓴다.
        """
        job_id = "adsense_site_sync"

        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            _adsense_sync_callback,
            trigger=IntervalTrigger(hours=_adsense_sync_hours()),
            id=job_id,
            name="애드센스 사이트 상태 동기화",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "[FLOW_SCHEDULER] 애드센스 상태 동기화 Job 등록 (%d시간 간격)",
            _adsense_sync_hours(),
        )

    def _register_model_catalog_sync(self) -> None:
        """AI 모델 목록 동기화 Job 등록.

        주기는 사용자가 설정 화면에서 바꾼다(기본 24시간). 0 을 저장하면
        등록하지 않고 '지금 갱신' 버튼으로만 돌린다.
        """
        job_id = "ai_model_catalog_sync"

        existing = self.scheduler.get_job(job_id)
        if existing:
            self.scheduler.remove_job(job_id)

        hours = _model_sync_hours()
        if hours <= 0:
            logger.info("[FLOW_SCHEDULER] AI 모델 목록 자동 동기화 사용 안 함")
            return

        self.scheduler.add_job(
            _model_catalog_sync_callback,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            name="AI 모델 목록 동기화",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "[FLOW_SCHEDULER] AI 모델 목록 동기화 Job 등록 (%d시간 간격)", hours,
        )

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

                    # 등록 시 일시정지 상태 초기화 (연속 실패로 paused된 상태 복구)
                    if state.is_paused:
                        state.is_paused = False
                        state.paused_at = None
                        state.consecutive_failures = 0
                        logger.info(
                            f"[FLOW_SCHEDULER] 실행 상태 일시정지 해제 | "
                            f"FlowID={flow_id} | ActionType={module_type_code}"
                        )

                    # 간격 계산: GP 있으면 GP 기반, 없으면 모듈 설정 또는 기본값
                    #
                    # keyword 는 예외다. 성장 프로파일은 '얼마나 자주
                    # 발행할까' 를 정하는데, 키워드 생산은 '재고가 부족한가'
                    # 로 돌아야 한다. 축이 다르므로 GP 가 있어도 모듈 설정을
                    # 쓴다(실제 실행 시점에 재고를 다시 본다).
                    if gp_settings and module_type_code != "keyword":
                        interval_minutes = self._get_gp_interval(
                            gp_settings, blogs, module_type_code
                        )
                    else:
                        module_settings = module.settings or {}
                        # bulk_collect 는 nested 경로(settings.schedule.interval_minutes)
                        # 에 저장한다(UI: _bulk_collect_form.html). 4-3 핫픽스로
                        # 모듈 타입별 폴백 경로 분기.
                        if module_type_code in ("bulk_collect", "keyword"):
                            # 둘 다 settings.schedule.interval_minutes 를 쓴다
                            schedule_cfg = (
                                module_settings.get("schedule") or {}
                            )
                            interval_minutes = schedule_cfg.get(
                                "interval_minutes",
                                360 if module_type_code == "keyword" else 60,
                            )
                        else:
                            interval_minutes = module_settings.get(
                                "interval_minutes", 60
                            )
                        logger.info(
                            f"[FLOW_SCHEDULER] GP 없음, 폴백 간격 사용 | "
                            f"FlowID={flow_id} | ActionType={module_type_code} | "
                            f"Interval={interval_minutes}분"
                        )

                    # fixed_time 모드의 collect/data/bulk_collect 모듈은 즉시 실행 금지
                    # (정해진 시각에만 실행되어야 하므로 등록 직후 트리거 안 함)
                    skip_immediate = False
                    if (
                        immediate_execution
                        and module_type_code in (
                            "collect", "data", "bulk_collect",
                        )
                        and not gp_settings
                    ):
                        module_settings = module.settings or {}
                        # bulk_collect 는 settings.schedule.* 중첩 경로 사용
                        if module_type_code == "bulk_collect":
                            _sched = module_settings.get("schedule") or {}
                            _mode = _sched.get("schedule_mode")
                        else:
                            _mode = module_settings.get("schedule_mode")
                        if _mode == "fixed_time":
                            skip_immediate = True
                            logger.info(
                                f"[FLOW_SCHEDULER] fixed_time 모드 즉시 실행 스킵 | "
                                f"FlowID={flow_id} | ActionType={module_type_code}"
                            )

                    if immediate_execution and not skip_immediate:
                        await self._schedule_immediate_execution(
                            flow, action_type=module_type_code, state=state
                        )
                    else:
                        # bulk_collect 등 GP 없이 자체 스케줄을 가지는 모듈은
                        # module_settings 를 넘겨 모듈 단위 지터를 적용한다.
                        mod_settings_for_jitter = None
                        if not gp_settings and module_type_code == "bulk_collect":
                            mod_settings_for_jitter = module.settings or {}
                        await self._schedule_next_execution(
                            db, flow, action_type=module_type_code, state=state,
                            interval_minutes=interval_minutes,
                            gp_settings=gp_settings,
                            module_settings=mod_settings_for_jitter,
                        )

                    registered_count += 1
                    logger.info(
                        f"[FLOW_SCHEDULER] 액션 등록 | FlowID={flow_id} | "
                        f"ActionType={module_type_code}"
                    )

                # GP에서 publish/republish 활성화 확인 후 등록
                if gp_settings and gp_settings.get("stages"):
                    for gp_action in ("generate", "publish", "republish"):
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

                            # 등록 시 일시정지 상태 초기화
                            if state.is_paused:
                                state.is_paused = False
                                state.paused_at = None
                                state.consecutive_failures = 0
                                logger.info(
                                    f"[FLOW_SCHEDULER] GP 실행 상태 일시정지 해제 | "
                                    f"FlowID={flow_id} | ActionType={gp_action}"
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

                # 모듈 찾기 (collect/bulk_collect/data/generate/prompt/contact_form만 모듈 필요)
                target_module = None
                if action_type in (
                    "collect", "bulk_collect", "data", "generate", "prompt",
                    "contact_form",
                ):
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

                elif action_type == "bulk_collect":
                    from app.routers.flows_execute import (
                        _execute_bulk_collect_module,
                    )
                    result = await _execute_bulk_collect_module(
                        target_module, db, flow_id=flow.id,
                    )
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
                        action="bulk_collect"
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
                elif action_type == "keyword":
                    result = await self._execute_keyword_module(
                        target_module, db, blogs
                    )

                elif action_type == "contact_form":
                    result = await self._execute_contact_form_module(
                        target_module, blogs, db,
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

    # 즉시 실행 시 액션마다 시작 시각을 벌린다.
    #
    # 오토런에 처음 등록하면 generate 와 publish 가 모두 '3초 뒤' 로 잡혀
    # 사실상 동시에 돈다. 그러면 발행이 아직 만들어지지도 않은 글을 찾다가
    # "발행 가능 글 없음" 으로 건너뛴다 — 최초 등록에서 거의 항상 그랬다.
    #
    # 생성이 먼저 자리를 잡도록 순서를 준다. 생성은 즉시, 발행·재발행은
    # 뒤로 물린다.
    # 생성이 끝나 재고에 반영되기까지 두는 여유(초).
    PUBLISH_AFTER_GENERATE_SEC = 120

    IMMEDIATE_DELAYS = {
        "generate": 3,
        "prompt": 3,
        "collect": 5,
        "bulk_collect": 5,
        "keyword": 5,
        "data": 5,
        "contact_form": 5,
        "publish": 180,      # 생성이 한 편 끝나기까지 통상 20~40초
        "republish": 240,
    }

    async def _next_publish_attempt(
        self,
        flow: Flow,
        action_type: str,
        gp_settings: Optional[dict],
        blogs: List[Blog],
        db: AsyncSession = None,
    ):
        """발행할 글이 없을 때 다음 시도 시각.

        **다음 생성 직후**가 기본이다. 생성 전에는 되물어도 결과가 같다.
        다만 발행 주기보다 오래 기다리지는 않는다 — 수동 생성 등 다른
        경로로 글이 생길 수 있고, 그때까지 손 놓고 있으면 안 된다.

        생성 액션이 등록돼 있지 않으면(생성 모듈 없음) 발행 주기를 쓴다.
        """
        now = datetime.now(KST)

        # 발행 주기 상한
        pub_interval = self._get_gp_interval(gp_settings, blogs, action_type) \
            if gp_settings else 60
        ceiling = now + timedelta(minutes=max(10, int(pub_interval or 60)))

        gen_state = await self._get_execution_state(db, flow.id, "generate") \
            if db is not None else None
        gen_next = getattr(gen_state, "next_execution_at", None)
        if not gen_next:
            return ceiling

        if gen_next.tzinfo is None:
            gen_next = KST.localize(gen_next)

        # 생성이 끝나고 저장될 시간을 조금 준다.
        candidate = gen_next + timedelta(seconds=self.PUBLISH_AFTER_GENERATE_SEC)
        if candidate <= now:
            # 생성 예정이 이미 지났다(밀렸다). 짧게 다시 본다.
            candidate = now + timedelta(minutes=5)
        return min(candidate, ceiling)

    async def _schedule_immediate_execution(
        self,
        flow: Flow,
        action_type: str,
        state: FlowExecutionState
    ) -> None:
        """즉시 실행 스케줄 등록 (action_type 기반).

        액션마다 지연을 달리해 **생성이 발행보다 먼저** 돌게 한다.
        """
        job_id = self._get_job_id(flow.id, action_type)

        delay = self.IMMEDIATE_DELAYS.get(action_type, 3)
        run_time = datetime.now(KST) + timedelta(seconds=delay)

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
        module_settings: dict = None,
    ) -> None:
        """다음 실행 시간 계산 및 스케줄 등록 (GP 기반, action_type 사용).

        지터 우선순위:
            1. GP 가 있으면 GP 의 ``jitter`` 객체 사용.
            2. ``module_settings`` 가 제공되면 (예: bulk_collect 등 GP 없는
               자체 스케줄 모듈) ``settings.schedule.jitter`` 를 사용.
               레거시 평탄 키 ``jitter_enabled/jitter_min_percent/...`` 도
               자동 폴백.
            3. 모두 없으면 지터 비활성.
        """
        from app.scheduler.jitter import resolve_module_jitter

        # fixed_time 모드 우선 처리 (GP 없는 collect/data/bulk_collect)
        if not gp_settings and action_type in (
            "collect", "data", "bulk_collect",
        ):
            fixed_next = self._get_module_next_fixed_time(flow, action_type)
            if fixed_next:
                await self._schedule_at_time(
                    flow, action_type=action_type, state=state,
                    run_time=fixed_next,
                )
                logger.info(
                    f"[FLOW_SCHEDULER] fixed_time 스케줄 등록 | "
                    f"FlowID={flow.id} | ActionType={action_type} | "
                    f"RunTime={fixed_next.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
                return

        # GP 설정에서 schedule_matrix/jitter 사용 (GP 없으면 모듈 설정 또는 기본값)
        if gp_settings:
            schedule_matrix = gp_settings.get("schedule_matrix")
            jitter = gp_settings.get("jitter", {})
            jitter_enabled = jitter.get("enabled", False)
            jitter_min = jitter.get("min_percent", -15)
            jitter_max = jitter.get("max_percent", 25)
        elif module_settings:
            # bulk_collect 등 모듈 자체 지터 (GP 와 동일 함수 재사용)
            schedule_matrix = None
            mod_jitter = resolve_module_jitter(module_settings)
            jitter_enabled = mod_jitter["enabled"]
            jitter_min = mod_jitter["min_percent"]
            jitter_max = mod_jitter["max_percent"]
            if jitter_enabled:
                logger.info(
                    f"[FLOW_SCHEDULER] 모듈 지터 적용 | FlowID={flow.id} | "
                    f"ActionType={action_type} | "
                    f"jitter=±{jitter_min}~{jitter_max}%"
                )
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

        # 이미 지난 시간이면 최소 간격 후 실행 (무한 루프 방지)
        if run_time <= now:
            run_time = now + timedelta(seconds=MIN_EXECUTION_GAP)

        self.scheduler.add_job(
            self._execute_module_callback,  # AsyncIOExecutor가 async 함수 직접 지원
            DateTrigger(run_date=run_time, timezone=KST),
            args=[flow.id, action_type],
            id=job_id,
            name=f"Flow {flow.name} - Action {action_type}",
            replace_existing=True
        )

        # FES.next_execution_at 도 동기화하여 UI 가시성 보장.
        # APScheduler memory store 가 1차 source 이고 이 컬럼은 거울이지만,
        # 사용자가 "다음 실행 언제?" 를 DB 조회 한 줄로 확인할 수 있어야 한다.
        if state is not None:
            try:
                state.next_execution_at = run_time
            except Exception as e:
                logger.warning(
                    f"[FLOW_SCHEDULER] next_execution_at 동기화 실패 | "
                    f"FlowID={flow.id} | Error={e}"
                )

        logger.info(
            f"[FLOW_SCHEDULER] Scheduled | FlowID={flow.id} | "
            f"ActionType={action_type} | RunTime={run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _check_daily_limit(
        self,
        db: AsyncSession,
        blog_id: int,
        action_type: str,
        daily_count: int,
    ) -> tuple:
        """일일 실행 한도 체크 (블로그별 카운트).

        AutorunLog에는 blog_id 컬럼이 없으므로 blog_name으로 매칭한다.
        blog_id가 0/None이면 블로그 무관 액션(collect/data 등)이므로
        blog_name == "-"인 로그만 카운트한다.

        Args:
            db: DB 세션
            blog_id: 블로그 ID (0이면 블로그 무관 액션)
            action_type: 액션 타입 (generate/publish/republish)
            daily_count: 일일 최대 횟수

        Returns:
            (exceeded: bool, today_count: int)
        """
        if not daily_count or daily_count <= 0:
            return False, 0

        from sqlalchemy import func as sa_func

        today_start = datetime.now(KST).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        count_query = select(sa_func.count(AutorunLog.id)).where(
            and_(
                AutorunLog.action == action_type,
                AutorunLog.status == "success",
                AutorunLog.created_at >= today_start,
            )
        )

        # 블로그별로 카운트: blog_id로 Blog.name을 조회하여 blog_name 매칭
        if blog_id:
            blog_obj = await db.get(Blog, blog_id)
            if blog_obj and blog_obj.name:
                count_query = count_query.where(
                    AutorunLog.blog_name == blog_obj.name
                )
            else:
                # 블로그를 찾을 수 없으면 안전하게 한도 초과로 처리
                logger.warning(
                    f"[DAILY_LIMIT] blog_id={blog_id} 블로그 조회 실패 - "
                    f"한도 체크 보수적 처리"
                )
                return True, 0
        else:
            # 블로그 무관 액션 (collect/data)
            count_query = count_query.where(AutorunLog.blog_name == "-")

        result = await db.execute(count_query)
        today_count = result.scalar() or 0

        return today_count >= daily_count, today_count

    def _get_next_day_active_start(
        self, gp_settings: dict
    ) -> Optional[datetime]:
        """다음 날 첫 활성 시간 반환.

        Args:
            gp_settings: GP 설정 dict

        Returns:
            다음 날 첫 활성 시간 (datetime) 또는 None
        """
        if not gp_settings:
            return None
        matrix = gp_settings.get("schedule_matrix")
        if not matrix:
            return None

        tomorrow = datetime.now(KST) + timedelta(days=1)
        tomorrow_start = tomorrow.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        dow = tomorrow_start.weekday()
        if dow < len(matrix):
            day_schedule = matrix[dow]
            for hour in range(24):
                if hour < len(day_schedule) and day_schedule[hour]:
                    return tomorrow_start.replace(hour=hour)

        # 폴백: 다음 날 08:00
        return tomorrow_start.replace(hour=8)

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
                if action_type in (
                    "collect", "bulk_collect", "data", "generate", "prompt",
                    "contact_form",
                ):
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

                # 일시정지된 실행 상태 체크 (연속 실패 등으로 paused)
                if state and state.is_paused:
                    # 플로우 자체가 active인데 state만 paused면 불일치 → 자동 해제
                    if flow.status == "active" and flow.is_in_autorun:
                        state.is_paused = False
                        state.paused_at = None
                        state.consecutive_failures = 0
                        await db.commit()
                        logger.info(
                            f"[FLOW_SCHEDULER] 불일치 해소: state paused → active | "
                            f"FlowID={flow_id} | ActionType={action_type}"
                        )
                    else:
                        logger.info(
                            f"[FLOW_SCHEDULER] 실행 상태 일시정지 중, 스킵 | "
                            f"FlowID={flow_id} | ActionType={action_type} | "
                            f"FlowStatus={flow.status} | IsInAutorun={flow.is_in_autorun}"
                        )
                        return

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
                        # 비활성 시간대 조기 반환 경로에서 실행 잠금 해제 필수.
                        # 누락 시 is_running=true 로 고착되어 다음 활성 발화(좀비
                        # 타임아웃 30분)까지 모든 실행이 스킵된다.
                        state.release_execution_lock()
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
                        # 모듈 단위 중복 디스패치 방지 (Redis TTL 락)
                        # collect task 가 끝나기 전 다음 trigger 가 또 디스패치하는 것을 차단
                        if not self._acquire_module_dispatch_lock(
                            "collect", module.id
                        ):
                            logger.info(
                                f"[FLOW_SCHEDULER] 수집 모듈 이전 디스패치 처리 중, 스킵 | "
                                f"FlowID={flow_id} | module_id={module.id}"
                            )
                            result = {
                                "success": True,
                                "skipped": True,
                                "message": "이전 수집 작업 진행 중",
                            }
                        else:
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

                elif action_type == "bulk_collect":
                    # 대량 수집: 기존 수동/테스트와 동일 실행기로 연결.
                    # 모듈 단위 중복 디스패치 방지(이전 사이클 진행 중 스킵).
                    if not self._acquire_module_dispatch_lock(
                        "bulk_collect", module.id
                    ):
                        logger.info(
                            f"[FLOW_SCHEDULER] 대량수집 모듈 이전 디스패치 처리 중, 스킵 | "
                            f"FlowID={flow_id} | module_id={module.id}"
                        )
                        result = {
                            "success": True,
                            "skipped": True,
                            "message": "이전 대량수집 사이클 진행 중",
                        }
                    else:
                        from app.routers.flows_execute import (
                            _execute_bulk_collect_module,
                        )
                        result = await _execute_bulk_collect_module(
                            module, db, flow_id=flow.id,
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
                        action="bulk_collect"
                    )

                    logger.info(
                        f"[FLOW_SCHEDULER] 대량수집 모듈 실행 완료 | FlowID={flow_id} | "
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
                        # 모듈 단위 중복 디스패치 방지 (Redis TTL 락)
                        if not self._acquire_module_dispatch_lock(
                            "data", module.id
                        ):
                            logger.info(
                                f"[FLOW_SCHEDULER] 데이터 모듈 이전 디스패치 처리 중, 스킵 | "
                                f"FlowID={flow_id} | module_id={module.id}"
                            )
                            result = {
                                "success": True,
                                "skipped": True,
                                "message": "이전 데이터 작업 진행 중",
                            }
                        else:
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

                    # 블로그별 AutorunLog는 _execute_generate_module 내부에서 저장됨
                    # Celery 사용 시 celery_tasks.py에서도 상세 로그 저장
                    # 여기서 요약 로그를 추가 저장하면 중복이 발생하므로 생략

                    logger.info(
                        f"[FLOW_SCHEDULER] 생성 모듈 실행 완료 | FlowID={flow_id} | "
                        f"Success={result.get('success', False)} | Duration={duration_ms}ms"
                    )
                elif action_type == "keyword":
                    result = await self._execute_keyword_module(
                        module, db, blogs
                    )
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                    logger.info(
                        f"[FLOW_SCHEDULER] 키워드 모듈 실행 완료 | FlowID={flow_id} | "
                        f"Success={result.get('success', False)} | Duration={duration_ms}ms"
                    )
                elif action_type == "contact_form":
                    result = await self._execute_contact_form_module(
                        module, blogs, db,
                    )
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                    logger.info(
                        f"[FLOW_SCHEDULER] 문의폼 모듈 실행 완료 | FlowID={flow_id} | "
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

                # === 공통 후처리 (Celery/직접 실행 무관하게 동일 패턴) ===
                if state:
                    if result.get("await_generation"):
                        # 발행할 글이 없다. 10분마다 되묻지 않고 **다음 생성
                        # 직후**로 미룬다. 생성 전에는 아무리 되물어도 결과가
                        # 같다.
                        #
                        # 다만 발행 주기보다 더 오래 기다리지는 않는다.
                        # 수동 생성 등 다른 경로로 글이 생길 수 있어서다.
                        state.record_execution(True)
                        state.release_execution_lock()
                        run_time = await self._next_publish_attempt(
                            flow, action_type, gp_settings, blogs, db=db
                        )
                        await self._schedule_at_time(
                            flow, action_type=action_type,
                            state=state, run_time=run_time,
                        )
                        logger.info(
                            f"[FLOW_SCHEDULER] 생성 대기 | FlowID={flow_id} | "
                            f"ActionType={action_type} | "
                            f"Next={run_time.strftime('%m-%d %H:%M:%S')}"
                        )
                    elif result.get("skip_interval"):
                        # 최초 실행이라 간격을 소비하지 않는다. 다만 10분
                        # 고정으로 되묻지는 않는다 — 생성 전에는 결과가 같다.
                        state.release_execution_lock()
                        recheck_time = await self._next_publish_attempt(
                            flow, action_type, gp_settings, blogs, db=db
                        )
                        await self._schedule_at_time(
                            flow, action_type=action_type,
                            state=state, run_time=recheck_time
                        )
                        logger.info(
                            f"[FLOW_SCHEDULER] 재고 대기 (간격 미소비) | "
                            f"FlowID={flow_id} | ActionType={action_type} | "
                            f"Recheck={recheck_time.strftime('%H:%M:%S')}"
                        )
                    elif (
                        "일일" in result.get("message", "")
                        and "한도" in result.get("message", "")
                    ):
                        # 일일 한도: 다음 날 첫 활성 시간으로 스케줄
                        state.record_execution(True)
                        state.release_execution_lock()
                        next_day_active = self._get_next_day_active_start(
                            gp_settings
                        )
                        if next_day_active:
                            await self._schedule_at_time(
                                flow, action_type=action_type,
                                state=state, run_time=next_day_active,
                            )
                        logger.info(
                            f"[FLOW_SCHEDULER] 일일 한도 → 다음 날 스케줄 | "
                            f"FlowID={flow_id} | ActionType={action_type} | "
                            f"NextDay={next_day_active}"
                        )
                    elif result.get("hold"):
                        # 보류: 간격 소비하고 다음 정규 스케줄로 진행
                        state.record_execution(True)
                        state.release_execution_lock()
                        await self._reschedule_next(
                            db, flow, action_type, state, gp_settings, blogs
                        )
                        logger.info(
                            f"[FLOW_SCHEDULER] 보류 (간격 소비) | "
                            f"FlowID={flow_id} | ActionType={action_type}"
                        )
                    else:
                        # 정상 실행 (성공/실패/Celery 위임 모두): 간격 소비 + 다음 스케줄
                        state.record_execution(result.get("success", False))
                        state.release_execution_lock()
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

        # fixed_time 모드 우선 처리 (GP 없는 collect/data/bulk_collect 등에 해당)
        # 정해진 시각에만 실행하므로 interval 계산 없이 직접 schedule
        if (
            fallback_interval <= 0
            and not gp_settings
            and action_type in ("collect", "data", "bulk_collect")
        ):
            fixed_next = self._get_module_next_fixed_time(flow, action_type)
            if fixed_next:
                await self._schedule_at_time(
                    flow, action_type=action_type, state=state,
                    run_time=fixed_next,
                )
                logger.info(
                    f"[FLOW_SCHEDULER] fixed_time 다음 실행 등록 | "
                    f"FlowID={flow.id} | ActionType={action_type} | "
                    f"RunTime={fixed_next.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
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

        # 지터 적용: GP > bulk_collect 모듈 settings > 비활성
        if gp_settings:
            _jitter = gp_settings.get("jitter", {})
            next_execution = state.calculate_next_execution(
                interval_minutes=interval_minutes,
                schedule_matrix=gp_settings.get("schedule_matrix"),
                jitter_enabled=_jitter.get("enabled", False),
                jitter_min_percent=_jitter.get("min_percent", -15),
                jitter_max_percent=_jitter.get("max_percent", 25),
            )
        elif action_type == "bulk_collect":
            # bulk_collect 사이클 재스케줄링도 GP 와 동일 지터 함수 재사용.
            from app.scheduler.jitter import resolve_module_jitter
            mod_settings = self._get_module_settings_for_action(
                flow, action_type
            ) or {}
            mod_jitter = resolve_module_jitter(mod_settings)
            next_execution = state.calculate_next_execution(
                interval_minutes=interval_minutes,
                jitter_enabled=mod_jitter["enabled"],
                jitter_min_percent=mod_jitter["min_percent"],
                jitter_max_percent=mod_jitter["max_percent"],
            )
            if mod_jitter["enabled"]:
                logger.info(
                    f"[FLOW_SCHEDULER] bulk_collect 재스케줄 지터 적용 | "
                    f"FlowID={flow.id} | "
                    f"jitter=±{mod_jitter['min_percent']}~{mod_jitter['max_percent']}%"
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

                # 잠금 해제 + 실행 기록 (last_executed_at 갱신으로 스케줄 진행 보장)
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

    def _get_module_settings_for_action(
        self,
        flow: Flow,
        action_type: str,
    ) -> Optional[dict]:
        """플로우 내 ``action_type`` 에 해당하는 모듈의 settings dict 조회.

        지터/스케줄 등 모듈 단위 설정을 _reschedule_next 같은 콜백에서
        다시 읽을 때 사용한다. 매칭되는 모듈이 없거나 settings 가 없으면
        ``None`` 반환.
        """
        for link in flow.module_links:
            module = link.module
            if not module or not module.module_type:
                continue
            if module.module_type.code == action_type:
                return module.settings or {}
        return None

    def _get_module_fallback_interval(
        self,
        flow: Flow,
        action_type: str,
        default_minutes: int = 60
    ) -> int:
        """
        GP가 없을 때 모듈 자체 settings에서 폴백 간격(분) 조회

        우선순위: interval_minutes → interval_hours(× 60) → default_minutes

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
                        f"[FLOW_SCHEDULER] 모듈 폴백 간격 (분) | "
                        f"ActionType={action_type} | Interval={int(interval)}분"
                    )
                    return int(interval)

                hours = module_settings.get("interval_hours")
                if hours and isinstance(hours, (int, float)) and hours > 0:
                    logger.debug(
                        f"[FLOW_SCHEDULER] 모듈 폴백 간격 (시 → 분) | "
                        f"ActionType={action_type} | Interval={int(hours * 60)}분"
                    )
                    return int(hours * 60)
                break
        logger.debug(
            f"[FLOW_SCHEDULER] 기본 폴백 간격 사용 | "
            f"ActionType={action_type} | Interval={default_minutes}분"
        )
        return default_minutes

    def _get_module_next_fixed_time(
        self,
        flow: Flow,
        action_type: str,
    ) -> Optional[datetime]:
        """모듈 settings 의 schedule_mode/fixed_times 기반 다음 실행 시각

        fixed_time 모드가 아니거나 유효한 fixed_times 가 없으면 None 반환.
        반환 시각은 KST 기준 가장 가까운 미래 시각.
        """
        for link in flow.module_links:
            module = link.module
            if not module or not module.module_type:
                continue
            if module.module_type.code != action_type:
                continue
            settings = module.settings or {}
            # bulk_collect 는 스케줄 설정을 settings.schedule.* 중첩에 저장한다.
            # collect/data 는 top-level(settings.schedule_mode/fixed_times).
            if action_type == "bulk_collect":
                sched = settings.get("schedule") or {}
                schedule_mode = sched.get("schedule_mode")
                fixed_times = sched.get("fixed_times") or []
            else:
                schedule_mode = settings.get("schedule_mode")
                fixed_times = settings.get("fixed_times") or []
            if schedule_mode != "fixed_time":
                return None
            if not fixed_times:
                return None

            now = datetime.now(KST)
            today_midnight = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            candidates: list[datetime] = []
            for t_str in fixed_times:
                try:
                    h_str, m_str = str(t_str).split(":")
                    h, m = int(h_str), int(m_str)
                except (ValueError, AttributeError):
                    logger.warning(
                        f"[FLOW_SCHEDULER] fixed_times 파싱 실패 | "
                        f"value={t_str!r}"
                    )
                    continue
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    continue
                candidate = today_midnight.replace(hour=h, minute=m)
                # 이미 지난 시각이면 다음 날로
                if candidate <= now:
                    candidate = candidate + timedelta(days=1)
                candidates.append(candidate)
            if not candidates:
                return None
            return min(candidates)
        return None

    def _acquire_module_dispatch_lock(
        self,
        action_type: str,
        module_id: int,
        ttl_seconds: int = 1800,
    ) -> bool:
        """모듈 단위 디스패치 중복 방지 락 (Redis SETNX, TTL 30분 기본)

        같은 모듈의 이전 task 가 워커에서 처리되는 동안 새 trigger 가 또
        디스패치하는 것을 차단. TTL 이 만료되면 자동 해제되므로
        task 가 오래 걸려도 결국 다시 잡힌다.

        Returns:
            True: 락 획득 (디스패치 가능)
            False: 이미 락 보유 중 (디스패치 스킵)
        """
        try:
            import os
            import redis as redis_lib

            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            redis_client = redis_lib.from_url(redis_url)
            lock_key = f"flow_module_dispatch_lock:{action_type}:{module_id}"
            acquired = redis_client.set(lock_key, "1", nx=True, ex=ttl_seconds)
            return bool(acquired)
        except Exception as e:
            # Redis 장애 시 락 없이 디스패치 허용 (보수적이지 않게, 가용성 우선)
            logger.warning(
                f"[FLOW_SCHEDULER] 디스패치 락 조회 실패 (락 없이 진행) | "
                f"action={action_type} | module_id={module_id} | error={e}"
            )
            return True

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

    async def _execute_keyword_module(
        self,
        module: Module,
        db: AsyncSession,
        blogs: List[Blog],
    ) -> Dict[str, Any]:
        """키워드 모듈 — 수집 → 측정 → 제목 생성 한 회차.

        재고가 충분한 블로그는 실행기가 스스로 건너뛴다. 매번 도는 것은 API
        낭비다. 수동 화면·플로우와 **같은 실행기**를 부른다 — 다른 코드를
        타면 한쪽에서만 나는 버그가 생긴다.

        Args:
            module: 키워드 타입 모듈
            db: DB 세션
            blogs: 플로우에 연결된 블로그 목록

        Returns:
            {"success": bool, "message": str, ...}
        """
        from app.services.flow.module_blog_scope import blogs_for_module
        from app.services.keyword_lab.runner import KeywordModuleRunner

        try:
            targets = blogs_for_module(module, list(blogs or []))
            runner = KeywordModuleRunner(db, module.user_id)
            return await runner.run_for_blogs(module.settings or {}, targets)
        except Exception as e:
            logger.error(f"[FLOW_SCHEDULER] 키워드 모듈 실행 오류: {e}")
            return {"success": False, "error": str(e), "message": str(e)}

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

    async def _execute_contact_form_module(
        self,
        contact_module: Module,
        blogs: List[Blog],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """애드센스 필수구성 모듈 실행: 블로그마다 문의폼 + 필수 4페이지 보장(멱등).

        폼 없음→생성, 구성 변경→PATCH/갱신, 동일→스킵. 반복 실행돼도 저부하.
        generate_pages=false면 문의폼만 보장(하위호환).
        """
        from sqlalchemy import select as _select
        from ..models.user import User
        from ..services.publishing.contact_form_provisioner import ensure_contact_form
        from ..services.publishing.contact_form_templates import get_template
        from ..services.publishing.contact_form_designs import get_design
        from ..services.publishing.required_pages_service import RequiredPagesService

        settings = contact_module.settings or {}
        try:
            template = get_template(settings.get("template_code") or "basic")
        except KeyError:
            template = None
        try:
            design = get_design(settings.get("design_code") or "default")
        except KeyError:
            design = None
        generate_pages = settings.get("generate_pages", True)
        preset_code = settings.get("pages_preset_code") or "standard"
        overrides = settings.get("pages_overrides") or {}
        if not blogs:
            return {"success": True, "skipped": True, "message": "연결된 블로그 없음"}

        svc = RequiredPagesService(db)
        ok = 0
        for blog in blogs:
            try:
                if generate_pages:
                    email = (blog.author_profile or {}).get("contact_email")
                    if not email:
                        row = await db.execute(
                            _select(User.email).where(User.id == blog.user_id)
                        )
                        email = row.scalar_one_or_none() or ""
                    outcome = await svc.generate_all(
                        blog, email, preset_code=preset_code, overrides=overrides,
                        contact_template=template, contact_design=design,
                    )
                    if outcome.get("success"):
                        ok += 1
                else:
                    url = await ensure_contact_form(blog, db, template=template, design=design)
                    if url:
                        ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("[CONTACT_FORM] 실패 | blog=%s | %s", blog.name, exc)
        label = "필수구성" if generate_pages else "문의폼"
        return {
            "success": True,
            "message": f"{label} 보장 {ok}/{len(blogs)}",
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

            # 일일 횟수 제한 체크 (Phase 3)
            # 한도는 블로그별로 판정한다. 예전에는 한 블로그가 한도에 걸리면
            # 전체를 return 해 같은 플로우의 다른 블로그까지 그날 생성이 멈췄다.
            limit_reached_blog_ids: set = set()
            if gp_settings:
                stages = gp_settings.get("stages", [])
                fallback_daily = None
                for stage in stages:
                    gen_config = stage.get("generate", {})
                    if gen_config.get("daily_count"):
                        fallback_daily = gen_config["daily_count"]
                        break  # 첫 매칭 stage를 폴백으로 사용

                for blog in blogs:
                    # 블로그별 단계가 계산돼 있으면 그 단계의 한도를 우선 적용
                    stage_params = blog_stage_map.get(blog.id)
                    daily_count = (
                        stage_params.generate.daily_count
                        if stage_params and stage_params.generate.daily_count
                        else fallback_daily
                    )
                    if not daily_count:
                        continue
                    exceeded, today_count = await self._check_daily_limit(
                        db, blog.id, "generate", daily_count,
                    )
                    if exceeded:
                        limit_reached_blog_ids.add(blog.id)
                        logger.info(
                            f"[SCHED:GENERATE] 일일 한도 도달(이 블로그만 건너뜀) | "
                            f"blog={blog.name} | today={today_count}/{daily_count}"
                        )

                if limit_reached_blog_ids and len(limit_reached_blog_ids) == len(blogs):
                    return {
                        "success": True,
                        "skipped": True,
                        "message": "모든 블로그가 일일 생성 한도에 도달했습니다",
                    }

            gen_executor = FlowGenerateExecutor(db, flow.user_id)

            total_success = 0
            total_skipped = 0
            total_failed = 0

            from app.services.flow.module_blog_scope import blogs_for_module

            for prompt_module in prompt_modules:
                # 모듈에 블로그가 연동돼 있으면 그 블로그에만 영향을 준다.
                # (연동이 없는 카테고리 모드 모듈만 플로우 전체 블로그 대상)
                module_blogs = blogs_for_module(prompt_module, blogs)
                if not module_blogs:
                    logger.info(
                        f"[FLOW_SCHEDULER] 대상 블로그 없음(연동 범위 밖) | "
                        f"module={prompt_module.name}"
                    )
                    continue
                for blog in module_blogs:
                    if blog.id in limit_reached_blog_ids:
                        total_skipped += 1
                        continue
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
                            from dataclasses import asdict
                            dispatcher = get_dispatcher()
                            module_settings = (
                                prompt_module.settings if prompt_module.settings else {}
                            )

                            # GP 재고 정책 검증 (min_inventory 미준수 방지).
                            # check_inventory 한 번으로 재고 체크 + 제목 결정 통합:
                            #   - inventory_count >= threshold면 needs_generation=False
                            #   - 사용 가능 제목 없어도 needs_generation=False
                            min_inv = (
                                stage_params.generate.min_inventory
                                if stage_params
                                and stage_params.generate.min_inventory is not None
                                else None
                            )
                            inv_check = await gen_executor.inventory_trigger.check_inventory(
                                blog.id,
                                min_inventory=min_inv,
                                module_settings=module_settings,
                            )

                            if not inv_check.needs_generation:
                                # 재고 충분 또는 사용 가능 제목 없음 → 큐 등록 skip
                                if inv_check.current_inventory >= inv_check.threshold:
                                    skip_reason = (
                                        f"재고 충분 ({inv_check.current_inventory}/"
                                        f"{inv_check.threshold})"
                                    )
                                else:
                                    skip_reason = "사용 가능 제목 없음"
                                skip_msg = (
                                    f"{blog.name} - 생성 큐 등록 생략 ({skip_reason})"
                                )
                                await self._save_autorun_log(
                                    db=db, user_id=flow.user_id, flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=prompt_module.name,
                                    blog_name=blog.name,
                                    result={
                                        "success": True, "skipped": True,
                                        "message": skip_msg,
                                    },
                                    duration_ms=0, action="queue_register",
                                )
                                result = {
                                    "success": True, "skipped": True,
                                    "message": skip_reason,
                                    "post_title": "",
                                }
                                logger.info(
                                    f"[FLOW_SCHEDULER] 큐 등록 skip ({skip_reason}) | "
                                    f"blog={blog.name} | "
                                    f"재고={inv_check.current_inventory}/"
                                    f"{inv_check.threshold}"
                                )
                                pre_title_id = 0  # dispatch 분기 통과용
                                pre_title = ""
                            else:
                                # 재고 부족 + 사용 가능 제목 있음 → 큐 등록 진행
                                pre_title_id = inv_check.available_title_id or 0
                                pre_title = inv_check.available_title_text or ""

                            if not pre_title_id:
                                pass  # 위 분기에서 이미 처리됨
                            else:
                                try:
                                    # GP StageParams를 dict로 직렬화하여 Celery 워커에 전달
                                    sp_dict = asdict(stage_params) if stage_params else None
                                    task_id = dispatcher.dispatch_generation(
                                        blog_id=blog.id,
                                        module_id=prompt_module.id,
                                        title_id=pre_title_id,
                                        priority=PRIORITY_NORMAL,
                                        flow_id=flow.id,
                                        stage_params_dict=sp_dict,
                                    )
                                    result = {
                                        "success": True,
                                        "message": f"Celery 큐 등록: {task_id}",
                                        "post_title": pre_title,
                                    }
                                    logger.info(
                                        f"[FLOW_SCHEDULER] Celery 디스패치 성공 | "
                                        f"blog={blog.name} | title_id={pre_title_id} | "
                                        f"task_id={task_id}"
                                    )
                                except Exception as e:
                                    result = {
                                        "success": False,
                                        "message": f"Celery 디스패치 실패: {e}",
                                        "post_title": pre_title,
                                    }
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
            # 임계값: 모듈 settings 우선, 없으면 시스템 설정(수동 승격과 통일).
            auto_group = settings.get("auto_group", True)
            threshold = settings.get("similarity_threshold")
            if threshold is None:
                from app.services.system_settings_service import (
                    SystemSettingsService,
                )
                threshold = await SystemSettingsService.get_float(
                    "similarity_threshold", db, 75.0
                )

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
        from ..services.publishing.publisher_pipeline import PublisherPipeline
        from ..services.generation.flow_execution_context import FlowExecutionContext
        from ..services.generation.growth_profile_resolver import GrowthProfileResolver

        # 재고 선확인 — 무거운 준비(GP 컨텍스트·발행 파이프라인) 전에 본다.
        # 발행할 글이 하나도 없으면 준비할 이유가 없다.
        from ..services.generation.inventory_manager import InventoryManager as _IM

        _pre = _IM(db)
        _has_any = False
        for _blog in blogs:
            if await _pre.get_post_for_publish(_blog.id):
                _has_any = True
                break

        if not _has_any:
            reasons = []
            for _blog in blogs:
                _why = await _pre.describe_publish_block(_blog.id)
                reasons.append(f"{_blog.name}: {_why}" if _why else _blog.name)
            # 사유를 남긴다. 지금까지는 "발행 가능 글 없음" 만 보여
            # 카테고리 불일치인지 재고가 없는 것인지 알 수 없었다.
            msg = "발행할 글 없음 — " + " / ".join(reasons[:3])
            logger.info("[SCHED:PUBLISH] %s | FlowID=%s", msg, flow.id)
            return {
                "success": True,
                "skipped": True,
                "await_generation": True,   # 다음 생성 시각 뒤로 미룬다
                "message": msg,
            }

        gp_context = None
        if gp_settings:
            gp_context = GrowthProfileResolver.build_execution_context(
                flow.id, gp_settings,
                await build_effective_post_counts(db, blogs)
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

        from ..services.generation.inventory_manager import InventoryManager
        from ..models.flow_execution_state import MIN_CHECK_INTERVAL

        inv_mgr = InventoryManager(db)

        # 일일 횟수 제한 체크 (Phase 3)
        if gp_context:
            for blog in blogs:
                stage_params = gp_context.get_stage_for_blog(blog.id)
                if (
                    stage_params
                    and stage_params.publish
                    and stage_params.publish.daily_count
                ):
                    exceeded, today_count = await self._check_daily_limit(
                        db, blog.id, "publish",
                        stage_params.publish.daily_count,
                    )
                    if exceeded:
                        logger.info(
                            f"[SCHED:PUBLISH] 일일 한도 도달 | "
                            f"blog={blog.name} | "
                            f"today={today_count}/"
                            f"{stage_params.publish.daily_count}"
                        )
                        return {
                            "success": True,
                            "skipped": True,
                            "message": (
                                f"일일 발행 한도 도달 "
                                f"({today_count}/"
                                f"{stage_params.publish.daily_count})"
                            ),
                        }

        success_count = 0
        fail_count = 0
        hold_count = 0
        skip_count = 0
        for blog in blogs:
            blog_start = datetime.now()
            try:
                stage_params = gp_context.get_stage_for_blog(blog.id) if gp_context else None
                if not stage_params or not stage_params.publish.enabled:
                    continue

                # 재고 ON/OFF 체크 (발행 가능 글 존재 여부)
                inventory_post = await inv_mgr.get_post_for_publish(blog.id)
                has_inventory = inventory_post is not None

                if not has_inventory:
                    # 최초 실행 판별: successful_executions == 0
                    state = await self._get_execution_state(db, flow.id, "publish")
                    is_first = state and state.successful_executions == 0

                    if is_first:
                        # 최초 실행 + 재고 OFF: 간격 미소비, 재체크 대기
                        pub_result = {
                            "success": True,
                            "skipped": True,
                            "skip_interval": True,
                            "message": "재고 대기 (최초 실행, 발행 가능 글 없음)"
                        }
                        skip_count += 1
                    else:
                        # 후속 실행 + 재고 OFF: 보류, 간격 소비
                        # 재고가 없는 것과 카테고리 불일치로 걸러진 것은 조치가
                        # 다르므로 사유를 구분해 남긴다.
                        block_reason = await inv_mgr.describe_publish_block(blog.id)
                        pub_result = {
                            "success": True,
                            "hold": True,
                            "message": (
                                f"보류 ({block_reason})" if block_reason
                                else "보류 (발행 가능 글 없음)"
                            ),
                        }
                        hold_count += 1

                    # AutorunLog 저장
                    blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                    await self._save_autorun_log(
                        db=db, user_id=flow.user_id, flow_id=flow.id,
                        flow_name=flow.name, module_name=gp_module_name,
                        blog_name=blog.name, result=pub_result,
                        duration_ms=blog_duration, action="publish")

                    logger.info(
                        f"[SCHED:PUBLISH] 재고 OFF | blog={blog.name} | "
                        f"first={is_first} | status={'skip' if is_first else 'hold'}"
                    )
                    continue  # 다음 블로그로

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
                    from app.services.generation.title_peek import (
                        peek_next_publish_post,
                    )
                    dispatcher = get_dispatcher()
                    # 디스패치 시점에 발행 대상 결정 (워커도 동일 ID 사용)
                    pre_title, pre_post_id = await peek_next_publish_post(
                        db, blog.id,
                    )
                    if not pre_post_id:
                        # 큐 등록 skip — 활동 탭 표시용 queue_register 로그 저장
                        skip_msg = (
                            f"{blog.name} - 발행 큐 등록 생략 "
                            f"(발행할 글 없음)"
                        )
                        await self._save_autorun_log(
                            db=db, user_id=flow.user_id, flow_id=flow.id,
                            flow_name=flow.name, module_name=gp_module_name,
                            blog_name=blog.name,
                            result={
                                "success": True, "skipped": True,
                                "message": skip_msg,
                            },
                            duration_ms=0, action="queue_register",
                        )
                        pub_result = {
                            "success": True, "skipped": True,
                            "message": "발행할 글 없음",
                            "post_title": "",
                        }
                        logger.info(
                            f"[SCHED:PUBLISH] 발행 대상 없음, 큐 등록 skip | "
                            f"blog={blog.name}"
                        )
                    else:
                        try:
                            task_id = dispatcher.dispatch_publish(
                                blog_id=blog.id,
                                post_id=pre_post_id,
                                priority=PRIORITY_NORMAL,
                                flow_id=flow.id,
                            )
                            pub_result = {
                                "success": True,
                                "message": f"Celery 큐 등록: {task_id}",
                                "post_title": pre_title,
                            }
                            logger.info(
                                f"[SCHED:PUBLISH] Celery 디스패치 | "
                                f"blog={blog.name} | post_id={pre_post_id} | "
                                f"task={task_id}"
                            )
                        except Exception as e:
                            pub_result = {
                                "success": False,
                                "message": f"Celery 디스패치 실패: {e}",
                                "post_title": pre_title,
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
                    # 인자 순서: (blog, crawled_post, credential)
                    credential = None
                    if blog.google_credential_id:
                        from ..models.google_credential import GoogleCredential
                        credential = await db.get(
                            GoogleCredential, blog.google_credential_id,
                        )
                    pipeline_result = await pipeline.publish_post(
                        blog, crawled_post, credential=credential,
                    )

                    if pipeline_result.success:
                        # complete_publish 시그니처: (blog_id, crawled_post_id, published_url)
                        await publisher.complete_publish(
                            blog.id, crawled_post.id,
                            published_url=pipeline_result.published_url,
                        )
                        success_count += 1
                    else:
                        fail_count += 1
                elif pub_result.get("skipped"):
                    pass  # 스킵
                elif pub_result.get("success"):
                    # Celery 위임. 실제 발행 결과는 워커가 따로 기록한다.
                    # 여기서 실패로 세면 **성공한 발행이 연속 실패로 쌓인다**
                    # — 인포노트가 08-30 정상 발행하고도 연속 실패 2가 된 이유.
                    # 직접 발행 경로는 crawled_post 나 skipped 중 하나를 늘
                    # 달고 오므로 이 가지로 오지 않는다.
                    success_count += 1
                else:
                    fail_count += 1

                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                # 큐 등록 로그도 별도로 저장(action=queue_register, INFO 레벨).
                # 작업 완료 시점(SUCCESS/ERROR) 로그는 celery_publish_tasks에서 별도 저장됨.
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

        # 모든 블로그가 hold/skip인 경우 결과에 플래그 전파
        all_hold = hold_count > 0 and success_count == 0 and fail_count == 0 and skip_count == 0
        all_skip = skip_count > 0 and success_count == 0 and fail_count == 0 and hold_count == 0

        result = {
            "success": fail_count == 0,
            "message": (
                f"발행 성공 {success_count}/{len(blogs)}, "
                f"실패 {fail_count}/{len(blogs)}"
                + (f", 보류 {hold_count}" if hold_count else "")
                + (f", 재고대기 {skip_count}" if skip_count else "")
            ),
        }

        if all_hold:
            result["hold"] = True
        elif all_skip:
            result["skip_interval"] = True
            result["skipped"] = True

        return result

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
                await build_effective_post_counts(db, blogs)
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

                # 재발행 일일 한도 체크 (발행과 동일 기준).
                # daily_count 설정 시 해당 블로그의 오늘 재발행 성공 수와 비교.
                if stage_params.republish and stage_params.republish.daily_count:
                    exceeded, today_count = await self._check_daily_limit(
                        db, blog.id, "republish",
                        stage_params.republish.daily_count,
                    )
                    if exceeded:
                        logger.info(
                            f"[SCHED:REPUBLISH] 일일 한도 도달 | "
                            f"blog={blog.name} | "
                            f"today={today_count}/"
                            f"{stage_params.republish.daily_count}"
                        )
                        # 한도 도달 시 다음 날 재스케줄을 위한 message 사용
                        continue

                if await _use_celery("use_celery_publish", db):
                    # Celery 워커에 재발행 위임
                    from app.core.task_dispatcher import (
                        get_dispatcher, PRIORITY_NORMAL,
                    )
                    from app.services.generation.title_peek import (
                        peek_next_republish_title,
                    )
                    dispatcher = get_dispatcher()
                    # 큐 등록 로그용 제목 미리 조회 (실패해도 dispatch는 진행)
                    pre_title = await peek_next_republish_title(db, blog.id)
                    try:
                        task_id = dispatcher.dispatch_republish(
                            blog_id=blog.id,
                            priority=PRIORITY_NORMAL,
                            flow_id=flow.id,
                        )
                        blog_result = {
                            "success": True,
                            "message": f"Celery 큐 등록: {task_id}",
                            "post_title": pre_title,
                        }
                        logger.info(
                            f"[SCHED:REPUBLISH] Celery 디스패치 | "
                            f"blog={blog.name} | task={task_id}"
                        )
                    except Exception as e:
                        blog_result = {
                            "success": False,
                            "message": f"Celery 디스패치 실패: {e}",
                            "post_title": pre_title,
                        }
                        logger.error(
                            f"[SCHED:REPUBLISH] Celery 디스패치 오류 | "
                            f"blog={blog.name} | {e}"
                        )
                else:
                    blog_result = await self._execute_republish_for_blog(blog)

                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)

                # 큐 등록 로그도 별도로 저장(action=queue_register, INFO 레벨).
                # 작업 완료 시점(SUCCESS/ERROR) 로그는 celery_publish_tasks에서 별도 저장됨.
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
        """AutorunLog DB 저장 (flows_execute.py와 동일).

        수집/대량수집 액션의 경우 ``autorun_message_builder`` 를 통해
        통계가 포함된 한국어 메시지로 재가공하고, NULL 로 남던
        ``posts_processed/success/failed`` 컬럼도 함께 채운다.
        """
        from app.services.autorun_message_builder import build_collect_log_stats

        try:
            # Celery 큐 등록 메시지는 action을 "queue_register"로 변경
            log_message = result.get("message", "")
            is_queue_dispatch = "Celery 큐 등록" in log_message
            is_dispatch_failed = "Celery 디스패치 실패" in log_message
            if is_queue_dispatch or is_dispatch_failed:
                worker_kind_map = {
                    "generate": "생성",
                    "publish": "발행",
                    "republish": "재발행",
                    "collect": "수집",
                    "bulk_collect": "대량 수집",
                    "data": "데이터",
                }
                worker_kind = worker_kind_map.get(action, "유틸")
                title_part = ""
                pre_title = result.get("post_title") or ""
                if pre_title.strip():
                    title_text = pre_title.strip()
                    if len(title_text) > 30:
                        title_text = title_text[:30] + "..."
                    title_part = f" - {title_text}"
                suffix = "등록 완료" if is_queue_dispatch else "등록 실패"
                action = "queue_register"
                log_message = (
                    f"{blog_name}{title_part} - {worker_kind} {suffix}"
                )

            # 수집/대량수집은 통계 기반 메시지로 재구성 (queue_register 제외).
            collect_stats = None
            if action in ("collect", "bulk_collect"):
                collect_stats = build_collect_log_stats(result, action)
                if collect_stats is not None:
                    log_message = collect_stats.message

            # 상태 결정: hold > skipped > success/failed
            if result.get("hold"):
                status = "hold"
            elif result.get("skipped"):
                status = "skipped"
            else:
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

            # 수집/대량수집 액션의 카운트 컬럼 채우기.
            if collect_stats is not None:
                log.posts_processed = collect_stats.posts_processed
                log.posts_success = collect_stats.posts_success
                log.posts_failed = collect_stats.posts_failed

            db.add(log)
            logger.info(f"[FLOW_SCHEDULER] AutorunLog 저장 | blog={blog_name} | action={action} | status={status}")

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


# 애드센스 상태 확인 주기(시간). 사용자가 설정 화면에서 바꿀 수 있다.
SETTING_ADSENSE_SYNC_HOURS = "adsense_sync_interval_hours"
DEFAULT_ADSENSE_SYNC_HOURS = 12
MIN_ADSENSE_SYNC_HOURS = 1
MAX_ADSENSE_SYNC_HOURS = 168


def _adsense_sync_hours() -> int:
    """저장된 확인 주기를 읽는다. 없으면 기본값.

    스케줄러 등록은 동기 문맥이라 DB 를 조회하지 않고 캐시된 설정을 쓴다.
    변경은 앱 재시작 또는 설정 저장 시 Job 재등록으로 반영된다.
    """
    from ..services.system_settings_service import SystemSettingsService

    try:
        raw = SystemSettingsService.get_cached(SETTING_ADSENSE_SYNC_HOURS)
        hours = int(raw) if raw else DEFAULT_ADSENSE_SYNC_HOURS
    except Exception:  # noqa: BLE001
        hours = DEFAULT_ADSENSE_SYNC_HOURS
    return max(MIN_ADSENSE_SYNC_HOURS, min(hours, MAX_ADSENSE_SYNC_HOURS))


async def _adsense_sync_callback() -> None:
    """애드센스 사이트 상태 동기화 콜백.

    등록된 계정이 있는 사용자별로 동기화한다. 한 계정이 실패해도 나머지는
    계속 진행한다(서비스 내부에서 처리).
    """
    try:
        from sqlalchemy import select as _select
        from ..core.database import db_manager
        from ..models.adsense_account import AdsenseAccount
        from ..services.publishing.adsense_account_service import (
            AdsenseAccountService,
        )

        async with db_manager.get_session() as session:
            user_ids = (
                await session.execute(
                    _select(AdsenseAccount.user_id)
                    .where(AdsenseAccount.is_active == True)  # noqa: E712
                    .distinct()
                )
            ).scalars().all()

            if not user_ids:
                logger.debug("[ADSENSE_SYNC] 등록된 계정 없음 — 건너뜀")
                return

            service = AdsenseAccountService(session)
            for user_id in user_ids:
                result = await service.sync_all(user_id)
                logger.info(
                    "[ADSENSE_SYNC] user=%s | %s/%s 계정 동기화",
                    user_id, result.get("synced"), result.get("total"),
                )
    except Exception as exc:  # noqa: BLE001
        logger.error("[ADSENSE_SYNC] 동기화 실패: %s", exc)


# AI 모델 목록 동기화 주기(시간). 사용자가 설정 화면에서 바꿀 수 있다.
# 0 이면 자동 동기화를 하지 않는다('지금 갱신' 버튼만 사용).
SETTING_MODEL_SYNC_HOURS = "ai_model_sync_interval_hours"
DEFAULT_MODEL_SYNC_HOURS = 24
MAX_MODEL_SYNC_HOURS = 168


def _model_sync_hours() -> int:
    """저장된 동기화 주기. 없으면 하루."""
    from ..services.system_settings_service import SystemSettingsService

    try:
        raw = SystemSettingsService.get_cached(SETTING_MODEL_SYNC_HOURS)
        hours = int(raw) if raw is not None and raw != "" else DEFAULT_MODEL_SYNC_HOURS
    except Exception:  # noqa: BLE001
        hours = DEFAULT_MODEL_SYNC_HOURS
    if hours <= 0:
        return 0
    return min(hours, MAX_MODEL_SYNC_HOURS)


async def _model_catalog_sync_callback() -> None:
    """AI 모델 목록 동기화 콜백.

    목록을 갱신하고, 사라진 모델을 쓰는 블로그가 있으면 경고를 남긴다.
    자동으로 다른 모델로 바꾸지는 않는다 — 모델이 바뀌면 글 품질과 요금이
    달라지므로 사람이 골라야 한다.
    """
    try:
        from ..core.database import db_manager
        from ..services.ai.model_catalog import ModelCatalogService
        from ..services.ai.model_warnings import warn_unavailable_models

        async with db_manager.get_session() as session:
            out = await ModelCatalogService(session).sync_all()
            t = out["total"]
            logger.info(
                "[MODEL_SYNC] 신규 %d / 사라짐 %d / 유지 %d",
                t["added"], t["gone"], t["kept"],
            )
            await warn_unavailable_models(session)
    except Exception as exc:  # noqa: BLE001
        logger.error("[MODEL_SYNC] 동기화 실패: %s", exc)


def _rate_limit_recovery_callback() -> None:
    """AI API 키 rate_limited 자동 복구 콜백 (동기 래퍼)"""
    import asyncio

    async def _do_recovery():
        from ..services.ai_key_manager import AIKeyManager
        # ensure_future로 던져진 코루틴 내부 예외는 바깥 try/except가 못 잡아
        # 조용히 삼켜지므로(과거 db_manager.session 오타가 이렇게 은폐됨),
        # 코루틴 내부에서 직접 로깅한다.
        try:
            async with db_manager.get_session() as db:
                key_manager = AIKeyManager(db, user_id=1)
                count = await key_manager.reset_rate_limited_keys()
                if count > 0:
                    logger.info(
                        f"[RATE_LIMIT_RECOVERY] {count}개 키 자동 복구 완료"
                    )
        except Exception as e:
            logger.error(f"[RATE_LIMIT_RECOVERY] 복구 코루틴 실패: {e}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_recovery())
        else:
            loop.run_until_complete(_do_recovery())
    except Exception as e:
        logger.error(f"[RATE_LIMIT_RECOVERY] 복구 실패: {e}")
