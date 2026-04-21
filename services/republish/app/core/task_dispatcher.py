"""
Celery 태스크 디스패처

APScheduler/HTTP API와 Celery 사이의 중재자.
기존 asyncio.create_task() 호출을 celery_app.send_task() 호출로 대체합니다.
"""
from datetime import datetime
from typing import Optional, Dict, Any

from .celery_config import celery_app
from .blog_lock import BlogLock
from .rate_limiter import AIRateLimiter
from .task_idempotency import TaskIdempotency, DuplicateTaskError
from .database import db_manager
from .logger import get_logger

logger = get_logger("task_dispatcher", "app.log")

# 우선순위 상수
PRIORITY_CRITICAL = 9       # 수동 즉시 실행
PRIORITY_HIGH = 7           # 재고 부족 긴급 생성
PRIORITY_NORMAL = 5         # 스케줄 기반 자동 실행
PRIORITY_LOW = 3            # 배치 작업
PRIORITY_BACKGROUND = 1    # 유지보수 작업


class TaskDispatcher:
    """APScheduler/HTTP API와 Celery 사이의 중재자.

    블로그 락, AI Rate Limit, 작업 멱등성 체크를 거친 뒤
    Celery 큐에 태스크를 전송합니다.
    """

    def __init__(
        self,
        blog_lock: BlogLock,
        rate_limiter: AIRateLimiter,
        idempotency: TaskIdempotency,
    ) -> None:
        """TaskDispatcher 초기화.

        Args:
            blog_lock: 블로그 단위 분산 락
            rate_limiter: AI 프로바이더 Rate Limiter
            idempotency: 작업 멱등성 관리자
        """
        self.celery = celery_app
        self.lock = blog_lock
        self.limiter = rate_limiter
        self.dedup = idempotency

    def _record_task_execution(
        self,
        task_id: str,
        task_name: str,
        queue: str,
        priority: int,
        blog_id: Optional[int] = None,
        module_id: Optional[int] = None,
        flow_id: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> None:
        """task_executions 테이블에 작업 상태 기록 (비동기 안전)"""
        try:
            import asyncio
            asyncio.get_event_loop().create_task(
                self._async_record(
                    task_id, task_name, queue, priority,
                    blog_id, module_id, flow_id, params,
                )
            )
        except RuntimeError:
            # 이벤트 루프가 없는 환경 (Celery prefork 등)에서는 스킵
            logger.debug(f"[DISPATCH] DB 기록 스킵 (이벤트 루프 없음) | task_id={task_id}")

    @staticmethod
    async def _async_record(
        task_id: str, task_name: str, queue: str, priority: int,
        blog_id: Optional[int], module_id: Optional[int],
        flow_id: Optional[int], params: Optional[dict],
    ) -> None:
        """task_executions INSERT (async)"""
        try:
            from ..models.task_execution import TaskExecution
            async with db_manager.get_session() as db:
                execution = TaskExecution(
                    task_id=task_id,
                    task_name=task_name,
                    queue=queue,
                    blog_id=blog_id,
                    module_id=module_id,
                    flow_id=flow_id,
                    status="pending",
                    priority=priority,
                    params=params or {},
                )
                db.add(execution)
                await db.commit()
        except Exception as e:
            logger.warning(f"[DISPATCH] task_executions 기록 실패 | task_id={task_id} | {e}")

    def dispatch_generation(
        self,
        blog_id: int,
        module_id: int,
        title_id: int = 0,
        priority: int = PRIORITY_NORMAL,
        flow_id: Optional[int] = None,
        user_id: Optional[int] = None,
        stage_params_dict: Optional[dict] = None,
        force: bool = False,
    ) -> str:
        """글 생성 작업 디스패치.

        Args:
            blog_id: 블로그 ID
            module_id: 모듈 ID
            title_id: 제목 ID (0이면 자동 선택)
            priority: 우선순위 (1-9)
            flow_id: 플로우 ID (선택)
            user_id: 사용자 ID (선택, 미지정 시 기본값 1)
            stage_params_dict: GP StageParams dict 직렬화 (선택)
            force: 재고 체크 없이 강제 생성 (수동 실행용)

        Returns:
            Celery task_id

        Raises:
            DuplicateTaskError: 동일 작업이 이미 진행 중일 때
        """
        if not force:
            dedup_key = f"generate:{blog_id}:{module_id}:{title_id}"
            if self.dedup.is_duplicate(dedup_key):
                raise DuplicateTaskError(dedup_key)

        task_kwargs = {
            "blog_id": blog_id, "module_id": module_id,
            "title_id": title_id, "flow_id": flow_id,
            "user_id": user_id or 1,
            "stage_params_dict": stage_params_dict,
            "force": force,
        }
        result = self.celery.send_task(
            "tasks.generate_content",
            kwargs=task_kwargs,
            queue="generation_queue",
            priority=priority,
        )
        self._record_task_execution(
            result.id, "tasks.generate_content", "generation_queue",
            priority, blog_id=blog_id, module_id=module_id,
            flow_id=flow_id, params=task_kwargs,
        )
        logger.info(
            f"[DISPATCH] 글 생성 디스패치 | task_id={result.id} "
            f"| blog={blog_id} | module={module_id} | force={force}"
        )
        return result.id

    def dispatch_publish(
        self,
        blog_id: int,
        post_id: int,
        priority: int = PRIORITY_NORMAL,
        flow_id: Optional[int] = None,
    ) -> str:
        """발행 작업 디스패치.

        Args:
            blog_id: 블로그 ID
            post_id: 게시글 ID
            priority: 우선순위 (1-9)
            flow_id: 플로우 ID (선택)

        Returns:
            Celery task_id

        Raises:
            DuplicateTaskError: 동일 작업이 이미 진행 중일 때
        """
        dedup_key = f"publish:{blog_id}:{post_id}"
        if self.dedup.is_duplicate(dedup_key):
            raise DuplicateTaskError(dedup_key)

        task_kwargs = {
            "blog_id": blog_id, "post_id": post_id, "flow_id": flow_id,
        }
        result = self.celery.send_task(
            "tasks.publish_post",
            kwargs=task_kwargs,
            queue="publish_queue",
            priority=priority,
        )
        self._record_task_execution(
            result.id, "tasks.publish_post", "publish_queue",
            priority, blog_id=blog_id, flow_id=flow_id, params=task_kwargs,
        )
        logger.info(
            f"[DISPATCH] 발행 디스패치 | task_id={result.id} "
            f"| blog={blog_id} | post={post_id}"
        )
        return result.id

    def dispatch_publish_batch(
        self,
        blog_id: int,
        count: int,
        priority: int = PRIORITY_NORMAL,
        flow_id: Optional[int] = None,
    ) -> str:
        """배치 발행 디스패치.

        Args:
            blog_id: 블로그 ID
            count: 발행할 게시글 수
            priority: 우선순위 (1-9)
            flow_id: 플로우 ID (선택)

        Returns:
            Celery task_id
        """
        result = self.celery.send_task(
            "tasks.publish_batch",
            kwargs={
                "blog_id": blog_id,
                "count": count,
                "flow_id": flow_id,
            },
            queue="publish_queue",
            priority=priority,
        )
        logger.info(
            f"[DISPATCH] 배치 발행 디스패치 | task_id={result.id} "
            f"| blog={blog_id} | count={count}"
        )
        return result.id

    def dispatch_republish(
        self,
        blog_id: int,
        priority: int = PRIORITY_NORMAL,
        flow_id: Optional[int] = None,
    ) -> str:
        """재발행 디스패치.

        Args:
            blog_id: 블로그 ID
            priority: 우선순위 (1-9)
            flow_id: 플로우 ID (선택)

        Returns:
            Celery task_id
        """
        result = self.celery.send_task(
            "tasks.republish_post",
            kwargs={
                "blog_id": blog_id,
                "flow_id": flow_id,
            },
            queue="publish_queue",
            priority=priority,
        )
        logger.info(
            f"[DISPATCH] 재발행 디스패치 | task_id={result.id} "
            f"| blog={blog_id}"
        )
        return result.id

    def dispatch_image(
        self,
        blog_id: int,
        title: str,
        module_settings: Dict[str, Any],
        generation_history_id: Optional[int] = None,
        crawled_post_id: Optional[int] = None,
        priority: int = PRIORITY_NORMAL,
    ) -> str:
        """이미지 생성 디스패치.

        Args:
            blog_id: 블로그 ID
            title: 이미지 생성용 제목
            module_settings: 모듈 이미지 생성 설정
            generation_history_id: 생성 이력 ID (DB 업데이트용)
            crawled_post_id: 크롤링 포스트 ID (DB 업데이트용)
            priority: 우선순위 (1-9)

        Returns:
            Celery task_id
        """
        result = self.celery.send_task(
            "tasks.generate_image",
            kwargs={
                "blog_id": blog_id,
                "title": title,
                "module_settings": module_settings,
                "generation_history_id": generation_history_id,
                "crawled_post_id": crawled_post_id,
            },
            queue="image_queue",
            priority=priority,
        )
        logger.info(
            f"[DISPATCH] 이미지 생성 디스패치 | task_id={result.id} "
            f"| blog={blog_id} | history={generation_history_id}"
        )
        return result.id

    def dispatch_utility(
        self,
        task_name: str,
        kwargs: Dict[str, Any],
        priority: int = PRIORITY_BACKGROUND,
    ) -> str:
        """유틸리티 작업 디스패치.

        수집, 데이터 처리 등 부가 작업을 utility_queue로 전송합니다.

        Args:
            task_name: Celery 태스크 이름
            kwargs: 태스크 파라미터
            priority: 우선순위 (1-9)

        Returns:
            Celery task_id
        """
        result = self.celery.send_task(
            task_name,
            kwargs=kwargs,
            queue="utility_queue",
            priority=priority,
        )
        logger.info(
            f"[DISPATCH] 유틸리티 디스패치 | task_id={result.id} "
            f"| task={task_name}"
        )
        return result.id


# --- 싱글톤 팩토리 ---

_dispatcher_instance: Optional[TaskDispatcher] = None


def get_dispatcher() -> TaskDispatcher:
    """TaskDispatcher 싱글톤 인스턴스를 반환합니다.

    최초 호출 시 Redis 연결을 생성하고 BlogLock, AIRateLimiter,
    TaskIdempotency를 초기화합니다. 이후 호출에서는 캐시된 인스턴스를 반환합니다.

    Returns:
        TaskDispatcher 싱글톤 인스턴스
    """
    global _dispatcher_instance
    if _dispatcher_instance is None:
        import redis as redis_lib
        import os

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = redis_lib.from_url(redis_url)

        _dispatcher_instance = TaskDispatcher(
            blog_lock=BlogLock(redis_client),
            rate_limiter=AIRateLimiter(redis_client),
            idempotency=TaskIdempotency(redis_client),
        )
        logger.info(f"[DISPATCH] TaskDispatcher 싱글톤 초기화 완료 | redis={redis_url}")
    return _dispatcher_instance
