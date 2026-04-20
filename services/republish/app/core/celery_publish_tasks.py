"""Celery 발행/재발행 태스크 정의 모듈.

PublishWorkflow를 호출하여 OFF 모드와 동일한 발행 로직을 실행합니다.
"""
import logging
import os

from app.core.celery_async_bridge import TaskSkipped, run_async
from app.core.celery_config import celery_app

logger = logging.getLogger(__name__)


async def _async_publish_via_workflow(
    blog_id: int, post_id: int = 0,
) -> dict:
    """PublishWorkflow를 사용하여 OFF 모드와 동일한 발행 로직 실행.

    Args:
        blog_id: 블로그 ID
        post_id: 발행할 포스트 ID (0이면 자동 선택)

    Returns:
        PublishWorkflow.execute_publish()의 반환값
    """
    from app.core.database import db_manager
    from app.services.generation.publish_workflow import PublishWorkflow

    async with db_manager.get_session() as db:
        workflow = PublishWorkflow(db)
        return await workflow.execute_publish(blog_id, post_id)


async def _async_republish_via_workflow(blog_id: int) -> dict:
    """PublishWorkflow를 사용하여 OFF 모드와 동일한 재발행 로직 실행.

    Args:
        blog_id: 블로그 ID

    Returns:
        PublishWorkflow.execute_republish()의 반환값
    """
    from app.core.database import db_manager
    from app.services.generation.publish_workflow import PublishWorkflow

    async with db_manager.get_session() as db:
        workflow = PublishWorkflow(db)
        return await workflow.execute_republish(blog_id)


@celery_app.task(
    bind=True,
    name="tasks.publish_post",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def publish_post(
    self,
    blog_id: int,
    post_id: int = 0,
    flow_id: int = None,
) -> dict:
    """단일 발행 태스크 (블로그 락 적용).

    PublishWorkflow를 호출하여 대상 선택 → 발행 → 후처리를 수행합니다.

    Args:
        blog_id: 블로그 ID
        post_id: 발행할 포스트 ID (0이면 자동 선택)
        flow_id: 플로우 ID (선택)

    Returns:
        dict: 발행 결과
    """
    import redis as redis_lib
    from app.core.blog_lock import BlogLock

    logger.info(
        f"[TASK:PUBLISH] 시작 | blog={blog_id} | post={post_id}"
    )

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url)
    blog_lock = BlogLock(redis_client)

    if not blog_lock.acquire(blog_id, "publish", ttl=300):
        logger.info(f"[TASK:PUBLISH] 블로그 락 대기 | blog={blog_id}")
        raise self.retry(countdown=15, max_retries=5)

    try:
        result = run_async(
            _async_publish_via_workflow(blog_id, post_id)
        )

        if result.get("skipped"):
            msg = result.get("message", "발행 대상 없음")
            logger.warning(
                f"[TASK:PUBLISH] 발행 스킵 (실패 처리) | blog={blog_id} "
                f"| 사유: {msg}"
            )
            raise TaskSkipped(msg)

        if result.get("success"):
            logger.info(
                f"[TASK:PUBLISH] 완료 | blog={blog_id} | "
                f"url={result.get('published_url', '')}"
            )
            return result

        error_msg = result.get("message") or result.get("error") or "발행 실패"
        raise RuntimeError(f"발행 실패: {error_msg}")

    except TaskSkipped:
        raise
    except Exception as exc:
        logger.error(f"[TASK:PUBLISH] 예외 | blog={blog_id} | {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        blog_lock.release(blog_id, "publish")


@celery_app.task(
    bind=True,
    name="tasks.publish_batch",
    soft_time_limit=600,
    time_limit=720,
)
def publish_batch(
    self,
    blog_id: int,
    count: int,
    flow_id: int = None,
) -> dict:
    """배치 발행 태스크 (미구현).

    Args:
        blog_id: 블로그 ID
        count: 발행할 포스트 수
        flow_id: 플로우 ID (선택)

    Returns:
        dict: 배치 발행 결과
    """
    logger.info(
        f"[TASK:PUBLISH_BATCH] 미구현 | blog={blog_id} | count={count}"
    )
    return {
        "success": False,
        "error": "Phase 4에서 구현 예정",
        "status": "not_implemented",
    }


@celery_app.task(
    bind=True,
    name="tasks.republish_post",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def republish_post(
    self,
    blog_id: int,
    flow_id: int = None,
) -> dict:
    """재발행 태스크 (블로그 락 적용).

    PublishWorkflow를 호출하여 OFF 모드와 동일한 재발행 로직을 실행합니다.

    Args:
        blog_id: 블로그 ID
        flow_id: 플로우 ID (선택)

    Returns:
        dict: 재발행 결과
    """
    import redis as redis_lib
    from app.core.blog_lock import BlogLock

    logger.info(f"[TASK:REPUBLISH] 시작 | blog={blog_id}")

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url)
    blog_lock = BlogLock(redis_client)

    if not blog_lock.acquire(blog_id, "publish", ttl=300):
        logger.info(f"[TASK:REPUBLISH] 블로그 락 대기 | blog={blog_id}")
        raise self.retry(countdown=15, max_retries=3)

    try:
        result = run_async(_async_republish_via_workflow(blog_id))
        if result.get("success"):
            logger.info(f"[TASK:REPUBLISH] 완료 | blog={blog_id}")
            return result

        error_msg = result.get("error") or result.get("message") or "재발행 실패"
        raise RuntimeError(f"재발행 실패: {error_msg}")
    except Exception as exc:
        logger.error(f"[TASK:REPUBLISH] 예외 | blog={blog_id} | {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        blog_lock.release(blog_id, "publish")
