"""
스케줄러 매니저

Features:
- APScheduler 통합 관리
- 플로우 기반 작업 스케줄링
- 동적 스케줄 업데이트
- 실행 이력 추적
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job
import json
import asyncio

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.module import Module
from ..models.flow_blog import FlowBlog
from ..models.blog import Blog
from ..schemas.flow import FlowStatus
from ..core.logger import get_logger
from ..core.database import get_db_session

logger = get_logger("scheduler_manager", "app.log")


class SchedulerManager:
    """스케줄러 매니저"""

    def __init__(self):
        # APScheduler 설정
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # 중복 작업 병합
            'max_instances': 3,  # 최대 동시 실행 인스턴스
            'misfire_grace_time': 300  # 5분 내 미실행 허용
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Seoul'
        )

        self._running = False

    # ===========================================
    # 스케줄러 생명주기
    # ===========================================

    async def start(self) -> bool:
        """스케줄러 시작"""
        try:
            if self._running:
                logger.warning("[SCHEDULER] 이미 실행 중인 스케줄러")
                return True

            self.scheduler.start()
            self._running = True

            # 활성 플로우 스케줄 등록
            await self._register_active_flows()

            logger.info("[SCHEDULER] 스케줄러 시작 완료")
            return True

        except Exception as e:
            logger.error(f"[SCHEDULER] 시작 실패: {e}")
            self._running = False
            return False

    async def stop(self) -> bool:
        """스케줄러 중지"""
        try:
            if not self._running:
                logger.warning("[SCHEDULER] 스케줄러가 실행 중이지 않음")
                return True

            self.scheduler.shutdown()
            self._running = False

            logger.info("[SCHEDULER] 스케줄러 중지 완료")
            return True

        except Exception as e:
            logger.error(f"[SCHEDULER] 중지 실패: {e}")
            return False

    def is_running(self) -> bool:
        """스케줄러 실행 상태 확인"""
        return self._running and self.scheduler.running

    # ===========================================
    # 플로우 스케줄 관리
    # ===========================================

    async def register_flow_schedule(self, flow_id: int) -> bool:
        """플로우 스케줄 등록"""
        try:
            logger.info(f"[REGISTER_FLOW] 플로우 {flow_id} 스케줄 등록")

            # 플로우 정보 조회
            async for db in get_db_session():
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow or flow.status != FlowStatus.ACTIVE:
                    logger.warning(f"[REGISTER_FLOW] 활성 플로우 아님: {flow_id}")
                    return False

                # 모듈별 스케줄 추출
                schedules = await self._extract_flow_schedules(flow)
                if not schedules:
                    logger.warning(f"[REGISTER_FLOW] 스케줄이 없는 플로우: {flow_id}")
                    return False

                # 기존 작업 제거
                await self.unregister_flow_schedule(flow_id)

                # 새 작업 등록
                for schedule in schedules:
                    job_id = f"flow_{flow_id}_module_{schedule['module_id']}_day_{schedule['day_of_week']}_hour_{schedule['hour']}"

                    # Cron 트리거 생성 (매주 해당 요일 해당 시간)
                    trigger = CronTrigger(
                        day_of_week=schedule['day_of_week'],
                        hour=schedule['hour'],
                        minute=schedule['minute'],
                        timezone='Asia/Seoul'
                    )

                    # 작업 등록
                    self.scheduler.add_job(
                        func=self._execute_flow_module,
                        trigger=trigger,
                        args=[flow_id, schedule['module_id']],
                        id=job_id,
                        name=f"Flow {flow.name} - Module {schedule['module_name']}",
                        replace_existing=True
                    )

                    logger.info(f"[REGISTER_FLOW] 스케줄 등록: {job_id}")

                logger.info(f"[REGISTER_FLOW] 플로우 {flow_id} 스케줄 등록 완료 ({len(schedules)}개)")
                return True

        except Exception as e:
            logger.error(f"[REGISTER_FLOW] 플로우 {flow_id} 등록 실패: {e}")
            return False

    async def unregister_flow_schedule(self, flow_id: int) -> bool:
        """플로우 스케줄 해제"""
        try:
            logger.info(f"[UNREGISTER_FLOW] 플로우 {flow_id} 스케줄 해제")

            # 해당 플로우의 모든 작업 제거
            jobs = self.scheduler.get_jobs()
            removed_count = 0

            for job in jobs:
                if job.id.startswith(f"flow_{flow_id}_"):
                    self.scheduler.remove_job(job.id)
                    removed_count += 1

            logger.info(f"[UNREGISTER_FLOW] 플로우 {flow_id} 스케줄 해제 완료 ({removed_count}개)")
            return True

        except Exception as e:
            logger.error(f"[UNREGISTER_FLOW] 플로우 {flow_id} 해제 실패: {e}")
            return False

    async def update_flow_schedule(self, flow_id: int) -> bool:
        """플로우 스케줄 업데이트 (해제 후 재등록)"""
        try:
            await self.unregister_flow_schedule(flow_id)
            return await self.register_flow_schedule(flow_id)
        except Exception as e:
            logger.error(f"[UPDATE_FLOW] 플로우 {flow_id} 업데이트 실패: {e}")
            return False

    async def _register_active_flows(self) -> None:
        """모든 활성 플로우 스케줄 등록"""
        try:
            async for db in get_db_session():
                # 활성 플로우 조회
                query = select(Flow.id).where(Flow.status == FlowStatus.ACTIVE)
                result = await db.execute(query)
                active_flow_ids = [row[0] for row in result.fetchall()]

                logger.info(f"[REGISTER_ACTIVE_FLOWS] 활성 플로우 {len(active_flow_ids)}개 등록 시작")

                for flow_id in active_flow_ids:
                    await self.register_flow_schedule(flow_id)

                logger.info(f"[REGISTER_ACTIVE_FLOWS] 활성 플로우 등록 완료")

        except Exception as e:
            logger.error(f"[REGISTER_ACTIVE_FLOWS] 실패: {e}")

    # ===========================================
    # 스케줄 분석 및 추출
    # ===========================================

    async def _get_flow_with_modules(self, db: AsyncSession, flow_id: int) -> Optional[Flow]:
        """플로우 및 모듈 정보 조회"""
        query = (
            select(Flow)
            .options(
                selectinload(Flow.flow_modules).selectinload(FlowModule.module),
                selectinload(Flow.flow_blogs).selectinload(FlowBlog.blog)
            )
            .where(Flow.id == flow_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _extract_flow_schedules(self, flow: Flow) -> List[Dict[str, Any]]:
        """플로우의 모듈 스케줄 추출"""
        schedules = []

        if not flow.flow_modules:
            return schedules

        for flow_module in flow.flow_modules:
            module = flow_module.module
            if not module or not module.schedule_matrix:
                continue

            try:
                # 스케줄 매트릭스 파싱
                matrix_data = module.schedule_matrix
                module_interval = module.manual_interval_minutes or 60

                if isinstance(matrix_data, list) and len(matrix_data) == 7:
                    # 2D 배열 형식: [[false, true, ...], [...], ...]
                    for day, day_schedule in enumerate(matrix_data):
                        if isinstance(day_schedule, list) and len(day_schedule) == 24:
                            for hour, is_active in enumerate(day_schedule):
                                if is_active:
                                    # 모듈 간격에 따른 minute 계산
                                    minute = await self._calculate_optimal_minute(
                                        module.id, day, hour, module_interval
                                    )

                                    schedule = {
                                        'module_id': module.id,
                                        'module_name': module.name,
                                        'day_of_week': day,
                                        'hour': hour,
                                        'minute': minute
                                    }
                                    schedules.append(schedule)

                else:
                    logger.warning(f"[EXTRACT_SCHEDULES] 지원하지 않는 매트릭스 형식: module_id={module.id}")

            except Exception as e:
                logger.warning(f"[EXTRACT_SCHEDULES] 모듈 {module.id} 스케줄 파싱 오류: {e}")

        return schedules

    async def _calculate_optimal_minute(
        self,
        module_id: int,
        day_of_week: int,
        hour: int,
        interval_minutes: int
    ) -> int:
        """모듈 기반 최적 minute 계산"""
        # 15분 단위로 정규화
        normalized_interval = max(15, (interval_minutes // 15) * 15)

        # 모듈 ID와 시간 기반 일관된 minute 계산
        time_hash = hash((module_id, day_of_week, hour)) % (60 // normalized_interval)
        return (time_hash * normalized_interval) % 60

    # ===========================================
    # 플로우 실행 로직
    # ===========================================

    async def _execute_flow_module(self, flow_id: int, module_id: int) -> None:
        """플로우 모듈 실행"""
        start_time = datetime.now()
        logger.info(f"[EXECUTE_FLOW] 플로우 {flow_id} 모듈 {module_id} 실행 시작")

        try:
            async for db in get_db_session():
                # 플로우 상태 확인
                flow = await self._get_flow_with_modules(db, flow_id)
                if not flow or flow.status != FlowStatus.ACTIVE:
                    logger.warning(f"[EXECUTE_FLOW] 플로우가 활성 상태가 아님: {flow_id}")
                    return

                # 해당 모듈이 플로우에 포함되어 있는지 확인
                target_module = None
                for flow_module in flow.flow_modules:
                    if flow_module.module_id == module_id:
                        target_module = flow_module.module
                        break

                if not target_module:
                    logger.warning(f"[EXECUTE_FLOW] 플로우 {flow_id}에서 모듈 {module_id}를 찾을 수 없음")
                    return

                # 모듈 타입 확인
                module_type = target_module.type_code

                # collect 타입: 블로그 없이 독립 실행
                if module_type == "collect":
                    logger.info(f"[EXECUTE_FLOW] 수집 모듈 실행: {target_module.name}")
                    try:
                        result = await self._execute_collect_module(target_module, db, flow)
                        logger.info(
                            f"[EXECUTE_FLOW] 수집 모듈 완료 | module={target_module.name} | "
                            f"success={result.get('success', False)}"
                        )
                    except Exception as e:
                        logger.error(f"[EXECUTE_FLOW] 수집 모듈 실행 실패: {e}")
                else:
                    # 기타 타입: 블로그 기반 실행
                    if flow.flow_blogs:
                        for flow_blog in flow.flow_blogs:
                            blog = flow_blog.blog
                            try:
                                await self._execute_module_for_blog(target_module, blog)
                            except Exception as e:
                                logger.error(f"[EXECUTE_FLOW] 모듈 {module_id} 블로그 {blog.id} 실행 실패: {e}")
                    else:
                        logger.warning(f"[EXECUTE_FLOW] 플로우 {flow_id}에 연결된 블로그가 없음")

                execution_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"[EXECUTE_FLOW] 플로우 {flow_id} 모듈 {module_id} 실행 완료 ({execution_time:.2f}s)")

        except Exception as e:
            logger.error(f"[EXECUTE_FLOW] 플로우 {flow_id} 모듈 {module_id} 실행 오류: {e}")

    async def _execute_module_for_blog(self, module: Module, blog: Blog) -> None:
        """모듈을 특정 블로그에 대해 실행"""
        logger.info(f"[EXECUTE_MODULE] 모듈 {module.name} 블로그 {blog.name} 실행")

        # 모듈 타입별 실행 로직
        if module.type_code == "prompt":
            await self._execute_prompt_module(module, blog)
        elif module.type_code == "generate":
            await self._execute_generate_module(module, blog)
        elif module.type_code == "publish":
            await self._execute_publish_module(module, blog)
        elif module.type_code == "republish":
            await self._execute_republish_module(module, blog)
        else:
            logger.warning(f"[EXECUTE_MODULE] 지원하지 않는 모듈 타입: {module.type_code}")

    async def _execute_prompt_module(self, module: Module, blog: Blog) -> None:
        """프롬프트 모듈 실행"""
        # 프롬프트 생성 로직
        logger.info(f"[PROMPT_MODULE] 프롬프트 생성: {module.name} → {blog.name}")
        # 실제 구현 필요

    async def _execute_generate_module(self, module: Module, blog: Blog) -> None:
        """생성 모듈 실행"""
        # 콘텐츠 생성 로직
        logger.info(f"[GENERATE_MODULE] 콘텐츠 생성: {module.name} → {blog.name}")
        # 실제 구현 필요

    async def _execute_publish_module(self, module: Module, blog: Blog) -> None:
        """발행 모듈 실행"""
        # 콘텐츠 발행 로직
        logger.info(f"[PUBLISH_MODULE] 콘텐츠 발행: {module.name} → {blog.name}")
        # 실제 구현 필요

    async def _execute_republish_module(self, module: Module, blog: Blog) -> None:
        """재발행 모듈 실행"""
        # 콘텐츠 재발행 로직
        logger.info(f"[REPUBLISH_MODULE] 콘텐츠 재발행: {module.name} → {blog.name}")
        # 실제 구현 필요

    async def _execute_collect_module(
        self,
        module: Module,
        db: AsyncSession,
        flow: Flow
    ) -> Dict[str, Any]:
        """
        수집 모듈 실행 (블로그 없이 독립 실행)

        키워드/제목 수집 작업을 수행합니다.
        """
        from app.services.keyword_collector_service import KeywordCollectorService
        from app.models.user_settings import UserSettings
        from app.models.autorun_log import AutorunLog

        try:
            settings_data = module.settings or {}

            # 수집 유형 확인 (keyword, title, both)
            collect_type = settings_data.get("collect_type", "both")

            # 키워드 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
            keyword_sources = []
            if settings_data.get("source_google_trends", False):
                keyword_sources.append("google_trends")
            if settings_data.get("source_naver_datalab", False):
                keyword_sources.append("naver_datalab")
            if settings_data.get("source_naver_ads", False):
                keyword_sources.append("naver_ads")

            # 제목 소스 목록 (기본값 False - 명시적으로 선택된 소스만 사용)
            title_sources = []
            if settings_data.get("source_naver_news", False):
                title_sources.append("naver_news")
            if settings_data.get("source_google_news", False):
                title_sources.append("google_news")
            if settings_data.get("source_naver_webdoc", False):
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
                logger.warning(f"[COLLECT_MODULE] 수집 소스가 설정되지 않음: {module.name}")
                return {
                    "success": False,
                    "message": f"수집 소스가 설정되지 않았습니다 (타입: {collect_type})",
                    "collected_count": 0
                }

            logger.info(
                f"[COLLECT_MODULE] 모듈={module.name} | 타입={collect_type} | 소스={sources}"
            )

            # 사용자 설정 조회
            query = select(UserSettings).where(UserSettings.user_id == 1)
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

            # 수집 수량 제한 적용
            keyword_limit = settings_data.get("keyword_collect_limit", 100)
            keyword_limit = max(10, min(1000, keyword_limit))
            # title_limit: 0 또는 None이면 무제한
            title_limit_setting = settings_data.get("title_collect_limit", 0)
            title_limit = None if title_limit_setting == 0 else title_limit_setting

            # 연관검색 확장 옵션 (기본값 True)
            enable_related_search = settings_data.get("enable_related_search", True)

            # 수집 유형 옵션 (일반/대량) - 기본값 False (명시적으로 활성화해야 동작)
            enable_normal_collect = settings_data.get("enable_normal_collect", False)
            enable_bulk_collect = settings_data.get("enable_bulk_collect", False)
            bulk_collect_delay = settings_data.get("bulk_collect_delay", 0.5)
            bulk_urls_per_cycle = settings_data.get("bulk_urls_per_cycle", 3)

            logger.info(
                f"[COLLECT_MODULE] 옵션 | keyword_limit={keyword_limit}, "
                f"title_limit={'무제한' if not title_limit else title_limit}, "
                f"enable_related_search={enable_related_search}, "
                f"enable_normal_collect={enable_normal_collect}, enable_bulk_collect={enable_bulk_collect}"
            )

            # 선택된 소스에서 수집
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

            # AutorunLog 저장 (상세 정보 포함)
            try:
                action_time = datetime.now().strftime("%Y/%m/%d %H:%M")
                # 상세 메시지 생성
                if collect_result.get("success"):
                    total_collected = collect_result.get("total_collected", 0)
                    total_saved = collect_result.get("total_saved", 0)
                    log_message = f"키워드/제목 수집 완료: {total_collected}개 수집, {total_saved}개 저장"
                else:
                    log_message = collect_result.get("message", "수집 실패")[:500]

                log_entry = AutorunLog(
                    user_id=1,
                    flow_id=flow.id,
                    action="collect",
                    status="success" if collect_result.get("success") else "failed",
                    flow_name=flow.name,
                    module_name=module.name,
                    blog_name="-",
                    post_title="",
                    action_time=action_time,
                    message=log_message
                )
                db.add(log_entry)
                await db.commit()
            except Exception as log_error:
                logger.warning(f"[COLLECT_MODULE] AutorunLog 저장 실패: {log_error}")

            if collect_result.get("success"):

                logger.info(
                    f"[COLLECT_MODULE] 수집 완료 | module={module.name} | "
                    f"collected={total_collected} | saved={total_saved}"
                )

                return {
                    "success": True,
                    "message": f"총 {total_collected}개 수집, {total_saved}개 저장",
                    "collected_count": total_collected,
                    "saved_count": total_saved,
                    "sources": sources
                }
            else:
                return {
                    "success": False,
                    "message": collect_result.get("error", "수집 실패"),
                    "collected_count": 0
                }

        except Exception as e:
            logger.error(f"[COLLECT_MODULE] 수집 실패 | module={module.name} | error={e}")
            return {
                "success": False,
                "message": str(e),
                "collected_count": 0
            }

    # ===========================================
    # 스케줄러 상태 조회
    # ===========================================

    def get_scheduler_status(self) -> Dict[str, Any]:
        """스케줄러 상태 정보 조회"""
        if not self.is_running():
            return {
                "is_running": False,
                "active_jobs": 0,
                "total_jobs": 0,
                "jobs": []
            }

        jobs = self.scheduler.get_jobs()
        active_jobs = len([job for job in jobs if job.next_run_time])

        return {
            "is_running": True,
            "start_time": self.scheduler.start_time if hasattr(self.scheduler, 'start_time') else None,
            "active_jobs": active_jobs,
            "total_jobs": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time,
                    "trigger": str(job.trigger)
                }
                for job in jobs[:10]  # 최대 10개만
            ]
        }

    def get_flow_next_execution(self, flow_id: int) -> Optional[datetime]:
        """플로우의 다음 실행 시간 조회"""
        jobs = self.scheduler.get_jobs()
        next_times = []

        for job in jobs:
            if job.id.startswith(f"flow_{flow_id}_") and job.next_run_time:
                next_times.append(job.next_run_time)

        return min(next_times) if next_times else None


# 전역 스케줄러 매니저 인스턴스
scheduler_manager = SchedulerManager()