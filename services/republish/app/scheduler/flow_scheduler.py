"""
플로우 스케줄러 (모듈 방식)

Features:
- IntervalTrigger 기반 분 단위 스케줄링
- 오토런 등록 시 즉시 실행
- 일시정지/재개 시 남은 시간 보존
- schedule_matrix를 활성화 시간대로 해석
- 개별 Job 등록/관리
- 모듈 방식 실행 (flows_execute.py와 동일)
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

                # 모듈 타입별로 하나씩만 실행 (중복 방지)
                # 같은 타입의 모듈이 여러 개 연결되어 있어도 첫 번째만 실행
                registered_count = 0
                registered_types = set()  # 이미 등록된 모듈 타입 추적

                for link in flow.module_links:
                    module = link.module
                    if not module:
                        continue

                    # 모듈 타입 확인 (module_type이 있으면 code 사용, 없으면 "unknown")
                    module_type_code = "unknown"
                    if module.module_type:
                        module_type_code = module.module_type.code

                    # 이미 같은 타입의 모듈이 등록되었으면 스킵
                    if module_type_code in registered_types:
                        logger.info(
                            f"[FLOW_SCHEDULER] 중복 모듈 타입 스킵 | FlowID={flow_id} | "
                            f"ModuleID={module.id} | Type={module_type_code}"
                        )
                        continue

                    registered_types.add(module_type_code)

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
                    logger.info(
                        f"[FLOW_SCHEDULER] 모듈 등록 | FlowID={flow_id} | "
                        f"ModuleID={module.id} | Type={module_type_code}"
                    )

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

                # 해당 액션 타입의 모듈 찾기
                target_module = None
                for link in flow.module_links:
                    module = link.module
                    if module and module.module_type:
                        if module.module_type.code == action_type:
                            target_module = module
                            break

                if not target_module:
                    return {
                        "success": False,
                        "message": f"액션 타입에 해당하는 모듈이 없습니다: {action_type}"
                    }

                # 블로그 목록 가져오기
                blogs = [link.blog for link in flow.blog_links if link.blog]

                # 모듈 방식 실행 (flows_execute.py와 동일)
                if action_type == "collect":
                    result = await self._execute_collect_module(target_module, db, flow)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    # AutorunLog 저장
                    await self._save_autorun_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=target_module.name,
                        blog_name="-",
                        result=result,
                        duration_ms=duration_ms,
                        action="collect"
                    )

                elif action_type == "republish":
                    if not blogs:
                        result = {"success": False, "message": "블로그가 연결되지 않았습니다"}
                    else:
                        success_count = 0
                        fail_count = 0
                        for blog in blogs:
                            blog_start = datetime.now()
                            try:
                                blog_result = await self._execute_republish_for_blog(blog)
                                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)

                                await self._save_autorun_log(
                                    db=db,
                                    user_id=flow.user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=target_module.name,
                                    blog_name=blog.name,
                                    result=blog_result,
                                    duration_ms=blog_duration,
                                    action="republish"
                                )

                                if blog_result.get("success"):
                                    success_count += 1
                                else:
                                    fail_count += 1

                            except Exception as e:
                                fail_count += 1
                                blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                                await self._save_autorun_log(
                                    db=db,
                                    user_id=flow.user_id,
                                    flow_id=flow.id,
                                    flow_name=flow.name,
                                    module_name=target_module.name,
                                    blog_name=blog.name,
                                    result={"success": False, "message": str(e)},
                                    duration_ms=blog_duration,
                                    action="republish"
                                )

                        result = {
                            "success": fail_count == 0,
                            "message": f"성공 {success_count}/{len(blogs)}, 실패 {fail_count}/{len(blogs)}"
                        }
                else:
                    result = {"success": False, "message": f"지원하지 않는 액션 타입: {action_type}"}

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                result["duration_ms"] = duration_ms

                logger.info(
                    f"[FLOW_SCHEDULER] Manual execution completed | "
                    f"FlowID={flow_id} | Success={result.get('success', False)} | "
                    f"Duration={duration_ms}ms"
                )

                # 실행 상태 업데이트
                state = await self._get_or_create_execution_state(
                    db, flow.id, target_module.id
                )
                state.record_execution(result.get("success", False))

                # 다음 실행 시간 계산
                interval_minutes = target_module.calculated_interval_minutes
                state.calculate_next_execution(
                    interval_minutes=interval_minutes,
                    schedule_matrix=target_module.schedule_matrix,
                    jitter_enabled=target_module.jitter_enabled,
                    jitter_min_percent=target_module.jitter_min_percent,
                    jitter_max_percent=target_module.jitter_max_percent
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
        """
        모듈 실행 콜백 (모듈 방식 - flows_execute.py와 동일)

        노드 체인 방식 대신 직접 서비스를 호출하여 실행합니다.
        """
        started_at = datetime.now()

        try:
            logger.info(
                f"[FLOW_SCHEDULER] Executing | FlowID={flow_id} | ModuleID={module_id}"
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

                # 블로그 목록 가져오기
                blogs = [link.blog for link in flow.blog_links if link.blog]

                # 모듈 방식 실행 (flows_execute.py와 동일)
                if action_type == "collect":
                    result = await self._execute_collect_module(module, db, flow)
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)

                    # AutorunLog 저장
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

                elif action_type == "republish":
                    if not blogs:
                        logger.warning(
                            f"[FLOW_SCHEDULER] 재발행 모듈에 블로그 없음 | FlowID={flow_id}"
                        )
                        result = {"success": False, "message": "블로그가 연결되지 않았습니다"}
                    else:
                        # 포스트 범위로 블로그 필터링
                        post_range_start = module.post_range_start or 1
                        post_range_end = module.post_range_end  # None이면 무제한

                        filtered_blogs = []
                        for blog in blogs:
                            post_count = blog.total_post_count or 0

                            if post_range_end is None:
                                # 무제한: start 이상이면 통과
                                if post_count >= post_range_start:
                                    filtered_blogs.append(blog)
                                    logger.info(
                                        f"[FLOW_SCHEDULER] ✅ 범위 내 | {blog.name}: "
                                        f"{post_count}개 >= {post_range_start}"
                                    )
                                else:
                                    logger.info(
                                        f"[FLOW_SCHEDULER] ❌ 범위 외 | {blog.name}: "
                                        f"{post_count}개 < {post_range_start}"
                                    )
                            else:
                                # 범위 지정: start <= post_count <= end
                                if post_range_start <= post_count <= post_range_end:
                                    filtered_blogs.append(blog)
                                    logger.info(
                                        f"[FLOW_SCHEDULER] ✅ 범위 내 | {blog.name}: "
                                        f"{post_range_start} <= {post_count} <= {post_range_end}"
                                    )
                                else:
                                    logger.info(
                                        f"[FLOW_SCHEDULER] ❌ 범위 외 | {blog.name}: "
                                        f"{post_count}개 not in {post_range_start}~{post_range_end}"
                                    )

                        logger.info(
                            f"[FLOW_SCHEDULER] 포스트 범위 필터링 | "
                            f"전체={len(blogs)} → 대상={len(filtered_blogs)} | "
                            f"범위={post_range_start}~{post_range_end if post_range_end else '무제한'}"
                        )

                        if not filtered_blogs:
                            logger.info(
                                f"[FLOW_SCHEDULER] 포스트 범위에 해당하는 블로그 없음 | "
                                f"FlowID={flow_id} | 범위={post_range_start}~{post_range_end}"
                            )
                            result = {
                                "success": True,
                                "message": f"포스트 범위({post_range_start}~{post_range_end or '무제한'})에 해당하는 블로그 없음"
                            }
                        else:
                            # 필터링된 블로그에 대해 재발행 실행
                            success_count = 0
                            fail_count = 0
                            for blog in filtered_blogs:
                                blog_start = datetime.now()
                                try:
                                    blog_result = await self._execute_republish_for_blog(blog)
                                    blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)

                                    # AutorunLog 저장
                                    await self._save_autorun_log(
                                        db=db,
                                        user_id=flow.user_id,
                                        flow_id=flow.id,
                                        flow_name=flow.name,
                                        module_name=module.name,
                                        blog_name=blog.name,
                                        result=blog_result,
                                        duration_ms=blog_duration,
                                        action="republish"
                                    )

                                    if blog_result.get("success"):
                                        success_count += 1
                                        logger.info(
                                            f"[FLOW_SCHEDULER] 재발행 성공 | blog={blog.name} | "
                                            f"post={blog_result.get('post_title', '')[:30]}"
                                        )
                                    else:
                                        fail_count += 1
                                        logger.warning(
                                            f"[FLOW_SCHEDULER] 재발행 실패 | blog={blog.name} | "
                                            f"error={blog_result.get('message', '')}"
                                        )

                                except Exception as e:
                                    fail_count += 1
                                    blog_duration = int((datetime.now() - blog_start).total_seconds() * 1000)
                                    logger.error(f"[FLOW_SCHEDULER] 블로그 처리 오류 | blog={blog.name} | error={e}")
                                    await self._save_autorun_log(
                                        db=db,
                                        user_id=flow.user_id,
                                        flow_id=flow.id,
                                        flow_name=flow.name,
                                        module_name=module.name,
                                        blog_name=blog.name,
                                        result={"success": False, "message": str(e)},
                                        duration_ms=blog_duration,
                                        action="republish"
                                    )

                            result = {
                                "success": fail_count == 0,
                                "message": f"성공 {success_count}/{len(filtered_blogs)}, 실패 {fail_count}/{len(filtered_blogs)}"
                            }

                            logger.info(
                                f"[FLOW_SCHEDULER] 재발행 완료 | FlowID={flow_id} | "
                                f"성공={success_count} | 실패={fail_count}"
                            )
                else:
                    result = {"success": False, "message": f"지원하지 않는 액션 타입: {action_type}"}
                    logger.warning(f"[FLOW_SCHEDULER] Unknown action type | {action_type}")

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

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                logger.info(
                    f"[FLOW_SCHEDULER] Execution completed | FlowID={flow_id} | "
                    f"ModuleID={module_id} | Success={result.get('success', False)} | "
                    f"Duration={duration_ms}ms"
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

            # 에러 메시지
            error_msg = None if is_success else result.get("message", "")

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
                message=error_msg
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
