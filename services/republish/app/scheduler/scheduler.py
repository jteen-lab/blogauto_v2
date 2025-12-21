"""
APScheduler 스케줄러 설정

Features:
- Redis 기반 Job Store
- 동적 프로파일 스케줄링
- 안전한 종료 처리
- Job 상태 모니터링
"""

import os
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from ..core.logger import get_logger

logger = get_logger("scheduler", "republish.log")


class Scheduler:
    """APScheduler 래퍼 클래스"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._setup_scheduler()

    def _setup_scheduler(self):
        """스케줄러 설정"""
        try:
            # Job Store 설정 (환경에 따라)
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")

            if os.getenv("ENVIRONMENT") == "production":
                jobstore = RedisJobStore.from_url(redis_url)
                logger.info("Redis Job Store 사용")
            else:
                jobstore = MemoryJobStore()
                logger.info("Memory Job Store 사용 (개발 환경)")

            # Executor 설정
            executor = AsyncIOExecutor()

            # Scheduler 생성
            self.scheduler = AsyncIOScheduler(
                jobstores={'default': jobstore},
                executors={'default': executor},
                job_defaults={
                    'coalesce': False,  # 중복 실행 방지
                    'max_instances': 1,  # 동시 실행 인스턴스 제한
                    'misfire_grace_time': 300  # 5분 유예시간
                },
                timezone='Asia/Seoul'
            )

            # 이벤트 리스너 등록
            self._setup_event_listeners()

            logger.info("스케줄러 설정 완료")

        except Exception as e:
            logger.error(f"스케줄러 설정 실패: {e}")
            raise

    def _setup_event_listeners(self):
        """이벤트 리스너 설정"""
        self.scheduler.add_listener(
            self._job_executed_listener,
            EVENT_JOB_EXECUTED
        )

        self.scheduler.add_listener(
            self._job_error_listener,
            EVENT_JOB_ERROR
        )

    def _job_executed_listener(self, event):
        """Job 실행 완료 리스너"""
        logger.info(f"Job 실행 완료: {event.job_id}")

    def _job_error_listener(self, event):
        """Job 실행 오류 리스너"""
        logger.error(f"Job 실행 오류: {event.job_id} | {event.exception}")

    async def start(self):
        """스케줄러 시작"""
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("스케줄러 시작됨")
            else:
                logger.warning("스케줄러가 이미 실행 중입니다")
        except Exception as e:
            logger.error(f"스케줄러 시작 실패: {e}")
            raise

    async def shutdown(self, wait: bool = True):
        """스케줄러 종료"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=wait)
                logger.info("스케줄러 종료됨")
            else:
                logger.warning("스케줄러가 실행 중이 아닙니다")
        except Exception as e:
            logger.error(f"스케줄러 종료 실패: {e}")
            raise

    def add_job(self, func, trigger, **kwargs):
        """Job 추가"""
        try:
            job = self.scheduler.add_job(func, trigger, **kwargs)
            logger.info(f"Job 추가 완료: {job.id}")
            return job
        except Exception as e:
            logger.error(f"Job 추가 실패: {e}")
            raise

    def remove_job(self, job_id: str):
        """Job 제거"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Job 제거 완료: {job_id}")
        except Exception as e:
            logger.error(f"Job 제거 실패: {job_id} | {e}")
            raise

    def get_job(self, job_id: str):
        """Job 조회"""
        return self.scheduler.get_job(job_id)

    def get_jobs(self):
        """모든 Job 조회"""
        return self.scheduler.get_jobs()


# 글로벌 스케줄러 인스턴스
scheduler_instance = Scheduler()


async def get_scheduler() -> Scheduler:
    """스케줄러 인스턴스 반환"""
    return scheduler_instance