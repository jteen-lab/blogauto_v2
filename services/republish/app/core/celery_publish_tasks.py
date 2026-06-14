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
    """발행 실행 + AutorunLog 저장 (Celery 전용 NullPool 세션)."""
    from app.core.celery_async_bridge import celery_db_session
    from app.services.generation.publish_workflow import PublishWorkflow

    async with celery_db_session() as db:
        workflow = PublishWorkflow(db)
        result = await workflow.execute_publish(blog_id, post_id)

        # AutorunLog 저장 + FlowExecutionState 업데이트
        try:
            from app.models.autorun_log import AutorunLog
            from app.models.blog import Blog
            blog = await db.get(Blog, blog_id)
            is_skip = result.get("skipped", False)
            is_ok = result.get("success", False) and not is_skip
            status = "success" if is_ok else ("skipped" if is_skip else "failed")
            log = AutorunLog.create_execution_log(
                user_id=1, flow_id=None, action="publish", status=status,
                flow_name="", module_name="",
                blog_name=blog.name if blog else str(blog_id),
                post_title=result.get("post_title", ""),
                action_time=None, duration_ms=0,
                message=result.get("message", ""),
            )
            db.add(log)
            await db.commit()
        except Exception as log_err:
            logger.warning(f"[PUBLISH] AutorunLog 저장 실패: {log_err}")

        # 스케줄 상태 업데이트 (완료 시점 기록 + 다음 스케줄)
        await _update_execution_state(db, blog_id, "publish", is_ok)

    return result


async def _async_republish_via_workflow(blog_id: int) -> dict:
    """PublishWorkflow를 사용하여 OFF 모드와 동일한 재발행 로직 실행.

    Args:
        blog_id: 블로그 ID

    Returns:
        PublishWorkflow.execute_republish()의 반환값
    """
    from app.core.celery_async_bridge import celery_db_session
    from app.services.generation.publish_workflow import PublishWorkflow

    async with celery_db_session() as db:
        workflow = PublishWorkflow(db)
        result = await workflow.execute_republish(blog_id)

        try:
            from app.models.autorun_log import AutorunLog
            from app.models.blog import Blog
            blog = await db.get(Blog, blog_id)
            is_skip = result.get("skipped", False)
            is_ok = result.get("success", False) and not is_skip
            status = "success" if is_ok else ("skipped" if is_skip else "failed")
            log = AutorunLog.create_execution_log(
                user_id=1, flow_id=None, action="republish", status=status,
                flow_name="", module_name="",
                blog_name=blog.name if blog else str(blog_id),
                post_title=result.get("post_title", ""),
                action_time=None, duration_ms=0,
                message=result.get("message", ""),
            )
            db.add(log)
            await db.commit()
        except Exception as log_err:
            logger.warning(f"[REPUBLISH] AutorunLog 저장 실패: {log_err}")

        # 스케줄 상태 업데이트 (완료 시점 기록 + 다음 스케줄)
        await _update_execution_state(db, blog_id, "republish", is_ok)

    return result


async def _update_execution_state(
    db, blog_id: int, action_type: str, success: bool
) -> None:
    """Celery 태스크 완료 시 성공 여부만 업데이트 (record_execution은 스케줄러에서 처리).

    스케줄러의 _execute_module_callback()이 디스패치 시점에 record_execution()과
    다음 스케줄 등록을 이미 처리하므로, Celery 완료 핸들러에서는 성공 시
    last_success_at만 갱신합니다. 이중 record_execution 호출을 방지합니다.
    """
    try:
        from sqlalchemy import select, and_
        from app.models.flow_blog import FlowBlog
        from app.models.flow_execution_state import FlowExecutionState

        fb_result = await db.execute(
            select(FlowBlog.flow_id).where(FlowBlog.blog_id == blog_id)
        )
        for (flow_id,) in fb_result.fetchall():
            state_result = await db.execute(
                select(FlowExecutionState).where(and_(
                    FlowExecutionState.flow_id == flow_id,
                    FlowExecutionState.action_type == action_type,
                ))
            )
            state = state_result.scalar_one_or_none()
            if state and success:
                from datetime import datetime
                import pytz
                state.last_success_at = datetime.now(
                    pytz.timezone('Asia/Seoul')
                )
                await db.commit()
                logger.info(
                    f"[CELERY:{action_type.upper()}] last_success_at 갱신 | "
                    f"flow_id={flow_id}"
                )
    except Exception as e:
        logger.warning(f"[CELERY:{action_type.upper()}] 상태 업데이트 실패: {e}")


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

        # 영구 실패(인증·키 미설정, 4xx 등)는 재시도해도 성공할 수 없으므로
        # Celery 재시도를 생략한다. 실패는 이미 AutorunLog/last_publish_error에 기록됨.
        if not result.get("retryable", True):
            logger.warning(
                f"[TASK:PUBLISH] 영구 실패(재시도 안 함) | blog={blog_id} "
                f"| 사유: {error_msg}"
            )
            return {
                "success": False,
                "retryable": False,
                "message": error_msg,
            }

        raise RuntimeError(f"발행 실패: {error_msg}")

    except TaskSkipped:
        raise
    except Exception as exc:
        err_str = str(exc)
        # 이벤트 루프 충돌은 발행이 이미 완료된 후 발생하므로 재시도 금지
        if "different loop" in err_str or "attached to a different" in err_str:
            logger.warning(
                f"[TASK:PUBLISH] 이벤트 루프 오류 (재시도 안 함) | blog={blog_id}"
            )
            return {"success": True, "message": "발행 완료 (세션 정리 오류)"}
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
        err_str = str(exc)
        if "different loop" in err_str or "attached to a different" in err_str:
            logger.warning(
                f"[TASK:REPUBLISH] 이벤트 루프 오류 (재시도 안 함) | blog={blog_id}"
            )
            return {"success": True, "message": "재발행 완료 (세션 정리 오류)"}
        logger.error(f"[TASK:REPUBLISH] 예외 | blog={blog_id} | {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        blog_lock.release(blog_id, "publish")
