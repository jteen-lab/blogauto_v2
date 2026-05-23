"""Celery 태스크 정의 모듈."""
import logging
import os

from app.core.celery_async_bridge import TaskSkipped, run_async
from app.core.celery_config import celery_app

logger = logging.getLogger(__name__)


async def _async_recombine_title(
    original_title: str,
    prompt_module_id: int,
    blog_id: int,
) -> dict:
    """제목 재조합 비동기 로직"""
    from app.core.database import db_manager
    from app.services.generation.title_recombiner import TitleRecombiner

    async with db_manager.get_session() as db:
        service = TitleRecombiner(db, user_id=1)
        result = await service.recombine(
            original_title=original_title,
            module_id=prompt_module_id,
        )
        return {
            "recombined_title": result.recombined_title,
            "ai_model": result.ai_model,
            "ai_provider": result.ai_provider,
            "is_modified": result.is_modified,
        }


async def _async_generate_via_executor(
    blog_id: int,
    module_id: int,
    user_id: int = 1,
    stage_params_dict: dict = None,
    force: bool = False,
    flow_id: int = None,
    force_title_id: int = 0,
) -> dict:
    """FlowGenerateExecutor를 사용하여 OFF 모드와 동일한 생성 로직 실행.

    Args:
        blog_id: 블로그 ID
        module_id: 모듈 ID
        user_id: 사용자 ID
        stage_params_dict: StageParams dict 직렬화 (None이면 기본값)
        force: 재고 체크 없이 강제 생성
        flow_id: 플로우 ID (AutorunLog용)
        force_title_id: 디스패치 시 결정된 MainTitle.id (0이면 자동 선택)

    Returns:
        FlowGenerateExecutor.execute_for_blog()의 반환값
    """
    from app.core.database import db_manager
    from app.models.blog import Blog
    from app.models.module import Module
    from app.services.generation.flow_generate_executor import FlowGenerateExecutor
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with db_manager.get_session() as db:
        module_result = await db.execute(
            select(Module)
            .where(Module.id == module_id)
            .options(selectinload(Module.module_type))
        )
        module = module_result.scalar_one_or_none()
        blog = await db.get(Blog, blog_id)

        if not module or not blog:
            return {
                "success": False,
                "message": f"Module({module_id}) 또는 Blog({blog_id}) 없음",
            }

        stage_params = None
        if stage_params_dict:
            from app.services.generation.flow_execution_context import (
                ModuleIntervalParams, StageParams,
            )
            stage_params = StageParams(
                stage_name=stage_params_dict["stage_name"],
                stage_label=stage_params_dict["stage_label"],
                generate=ModuleIntervalParams(
                    **stage_params_dict["generate"]
                ),
                publish=ModuleIntervalParams(
                    **stage_params_dict["publish"]
                ),
                republish=ModuleIntervalParams(
                    **stage_params_dict["republish"]
                ),
            )

        executor = FlowGenerateExecutor(db, user_id)
        result = await executor.execute_for_blog(
            module, blog, stage_params=stage_params, force=force,
            force_title_id=force_title_id,
        )

        try:
            from app.models.autorun_log import AutorunLog
            if result.get("skipped"):
                status = "skipped"
            elif result.get("success"):
                status = "success"
            else:
                status = "failed"
            log = AutorunLog.create_execution_log(
                user_id=user_id,
                flow_id=flow_id or None,
                action="generate",
                status=status,
                flow_name="",
                module_name=module.name if module else "",
                blog_name=blog.name if blog else "",
                post_title=result.get("post_title", ""),
                action_time=None,
                duration_ms=int(result.get("generation_time_seconds", 0) * 1000),
                message=result.get("message", ""),
            )
            db.add(log)
            await db.commit()
        except Exception as log_err:
            logger.warning(f"[GENERATE] AutorunLog 저장 실패: {log_err}")

        # 스케줄 상태 업데이트: 성공 시 last_success_at만 갱신
        # record_execution은 스케줄러의 _execute_module_callback()에서 디스패치 시점에 처리
        try:
            from sqlalchemy import select, and_
            from app.models.flow_blog import FlowBlog
            from app.models.flow_execution_state import FlowExecutionState

            is_ok = result.get("success") and not result.get("skipped")
            if is_ok:
                fb_result = await db.execute(
                    select(FlowBlog.flow_id).where(FlowBlog.blog_id == blog_id)
                )
                for (fid,) in fb_result.fetchall():
                    st_result = await db.execute(
                        select(FlowExecutionState).where(and_(
                            FlowExecutionState.flow_id == fid,
                            FlowExecutionState.action_type == "generate",
                        ))
                    )
                    st = st_result.scalar_one_or_none()
                    if st:
                        from datetime import datetime
                        import pytz
                        st.last_success_at = datetime.now(
                            pytz.timezone('Asia/Seoul')
                        )
                        await db.commit()
                        logger.info(
                            f"[CELERY:GENERATE] last_success_at 갱신 | "
                            f"flow_id={fid}"
                        )
        except Exception as se:
            logger.warning(f"[CELERY:GENERATE] 상태 업데이트 실패: {se}")

        return result


async def _async_on_generation_complete(
    generation_history_id: int,
    blog_id: int,
    source_title_id: int,
) -> dict:
    """생성 완료 후처리 비동기 로직"""
    from app.core.database import db_manager
    from app.models.title import MainTitle
    from app.models.generation_history import GenerationHistory

    async with db_manager.get_session() as db:
        history = await db.get(GenerationHistory, generation_history_id)
        if not history:
            return {
                "success": False,
                "message": f"이력 없음: id={generation_history_id}",
            }

        # CrawledPost가 실제로 존재할 때만 제목을 used 처리
        if not history.crawling_post_id:
            logger.warning(
                f"[COMPLETE] CrawledPost 없음 → 제목 used 처리 스킵 "
                f"| title_id={source_title_id}"
            )
        else:
            title = await db.get(MainTitle, source_title_id)
            if title and title.status != "used":
                title.mark_used()
                await db.commit()
                logger.info(
                    f"[COMPLETE] 제목 사용 처리 완료 "
                    f"| title_id={source_title_id}"
                )

        return {
            "success": True,
            "message": "생성 완료 후처리 성공",
            "generation_history_id": generation_history_id,
            "blog_id": blog_id,
        }


@celery_app.task(
    bind=True,
    name="tasks.recombine_title",
    max_retries=2,
    default_retry_delay=10,
)
def recombine_title(
    self, original_title: str, prompt_module_id: int,
    blog_id: int, generation_request_id: str,
) -> dict:
    """제목 재조합 태스크."""
    logger.info(
        f"[TASK:RECOMBINE] 시작 | title='{original_title[:30]}...' "
        f"| request_id={generation_request_id}"
    )

    try:
        result = run_async(
            _async_recombine_title(
                original_title, prompt_module_id, blog_id
            )
        )
        logger.info(
            f"[TASK:RECOMBINE] 완료 | "
            f"재조합: '{result['recombined_title'][:30]}...' "
            f"| model={result['ai_model']}"
        )
        return result

    except Exception as exc:
        logger.error(f"[TASK:RECOMBINE] 실패: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@celery_app.task(
    bind=True,
    name="tasks.generate_content",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_content(
    self,
    blog_id: int,
    module_id: int,
    title_id: int = 0,
    flow_id: int = None,
    user_id: int = 1,
    stage_params_dict: dict = None,
    force: bool = False,
) -> dict:
    """글 생성 태스크. FlowGenerateExecutor를 호출하여 OFF 모드와 동일한 로직 실행.

    Args:
        blog_id: 블로그 ID
        module_id: 모듈 ID
        title_id: 디스패치 시 결정된 MainTitle.id (0이면 워커가 자동 선택,
                  명시 시 워커가 강제 사용 — 큐/워커 결정성 보장)
        flow_id: 플로우 ID (선택)
        user_id: 사용자 ID
        stage_params_dict: GP StageParams dict 직렬화
        force: 재고 체크 없이 강제 생성
    """
    import redis as redis_lib
    from app.core.blog_lock import BlogLock
    from app.core.rate_limiter import AIRateLimiter

    logger.info(
        f"[TASK:GENERATE] 시작 | blog={blog_id} "
        f"| module={module_id} | force={force}"
    )

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url)

    blog_lock = BlogLock(redis_client)
    if not blog_lock.acquire(blog_id, "generate"):
        logger.info(f"[TASK:GENERATE] 블로그 락 대기 | blog={blog_id}")
        raise self.retry(countdown=30, max_retries=5)

    try:
        rate_limiter = AIRateLimiter(redis_client)
        can_call, wait_time = rate_limiter.can_call("openai")
        if not can_call:
            logger.info(
                f"[TASK:GENERATE] Rate Limit 대기 | wait={wait_time}s"
            )
            blog_lock.release(blog_id, "generate")
            raise self.retry(countdown=wait_time)

        result = run_async(
            _async_generate_via_executor(
                blog_id, module_id, user_id,
                stage_params_dict, force, flow_id,
                force_title_id=title_id,
            )
        )

        if result.get("skipped"):
            msg = result.get("message", "스킵")
            logger.warning(
                f"[TASK:GENERATE] 생성 스킵 (실패 처리) | blog={blog_id} "
                f"| 사유: {msg}"
            )
            raise TaskSkipped(msg)

        if result.get("success"):
            logger.info(
                f"[TASK:GENERATE] 완료 | blog={blog_id} "
                f"| title='{result.get('post_title', '')[:30]}'"
            )
            return result

        error_msg = result.get("error") or result.get("message") or "생성 실패"
        raise RuntimeError(f"생성 실패: {error_msg}")

    except TaskSkipped:
        raise
    except Exception as exc:
        logger.error(
            f"[TASK:GENERATE] 예외 | blog={blog_id} | {exc}"
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        blog_lock.release(blog_id, "generate")


async def _async_generate_image(
    blog_id: int, title: str, module_settings: dict,
    generation_history_id: int = None,
    crawled_post_id: int = None,
) -> dict:
    """이미지 생성 비동기 로직. 성공 시 DB(history/post)에 image_url 반영."""
    from app.core.database import db_manager
    from app.models.blog import Blog
    from app.services.generation.image_generator import ImageGenerator

    async with db_manager.get_session() as db:
        blog = await db.get(Blog, blog_id)
        if not blog:
            return {"success": False, "error": f"Blog({blog_id}) 없음"}

        generator = ImageGenerator(db, user_id=1)
        result = await generator.generate(
            blog=blog, title=title,
            module_settings=module_settings or {},
        )

        # DB 업데이트 (이미지 URL 반영)
        if result.success and result.image_url:
            if generation_history_id:
                from app.models.generation_history import GenerationHistory
                history = await db.get(
                    GenerationHistory, generation_history_id,
                )
                if history:
                    history.image_url = result.image_url
            if crawled_post_id:
                from app.models.crawled_post import CrawledPost
                post = await db.get(CrawledPost, crawled_post_id)
                if post:
                    post.image_url = result.image_url
            await db.commit()

        return {
            "success": result.success,
            "image_url": result.image_url,
            "ai_model": result.ai_model,
            "status": "completed" if result.success else "failed",
            "error": getattr(result, "error", None),
        }


@celery_app.task(
    bind=True,
    name="tasks.generate_image",
    max_retries=1,
    default_retry_delay=15,
    soft_time_limit=120,
    time_limit=150,
    acks_late=True,
)
def generate_image(
    self, blog_id: int, title: str,
    module_settings: dict = None,
    generation_history_id: int = None,
    crawled_post_id: int = None,
) -> dict:
    """이미지 생성 태스크 (블로그 락 적용). DB에 image_url 반영."""
    import redis as redis_lib
    from app.core.blog_lock import BlogLock
    logger.info(f"[TASK:IMAGE] 시작 | blog={blog_id} | title='{title[:30]}'")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url)
    blog_lock = BlogLock(redis_client)

    if not blog_lock.acquire(blog_id, "image", ttl=180):
        logger.info(f"[TASK:IMAGE] 블로그 락 대기 | blog={blog_id}")
        raise self.retry(countdown=10, max_retries=3)

    try:
        result = run_async(_async_generate_image(
            blog_id, title, module_settings or {},
            generation_history_id, crawled_post_id,
        ))
        lvl = "info" if result.get("success") else "warning"
        getattr(logger, lvl)(
            f"[TASK:IMAGE] {'완료' if result.get('success') else '실패'} "
            f"| blog={blog_id} | {result.get('image_url', result.get('error', ''))[:60]}"
        )
        return result
    except Exception as exc:
        logger.error(f"[TASK:IMAGE] 예외 | blog={blog_id} | {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        handle_dead_letter.delay(
            task_name="tasks.generate_image",
            task_args={"blog_id": blog_id, "title": title},
            exception_info=str(exc),
        )
        raise
    finally:
        blog_lock.release(blog_id, "image")


@celery_app.task(
    bind=True,
    name="tasks.on_generation_complete",
    max_retries=1,
    default_retry_delay=5,
)
def on_generation_complete(
    self, generation_request_id: str, blog_id: int,
    source_title_id: int, crawling_post_id: int,
    generation_history_id: int,
) -> dict:
    """생성 완료 후 콜백 태스크 (제목 사용 처리 안전장치)."""
    logger.info(
        f"[TASK:COMPLETE] 시작 | request_id={generation_request_id} "
        f"| history_id={generation_history_id}"
    )

    try:
        result = run_async(
            _async_on_generation_complete(
                generation_history_id, blog_id, source_title_id
            )
        )
        logger.info(
            f"[TASK:COMPLETE] 완료 | success={result['success']}"
        )
        return result

    except Exception as exc:
        logger.error(f"[TASK:COMPLETE] 실패: {exc}")
        raise


async def _async_record_dead_letter(
    task_name: str, task_args: dict, exception_info: str,
) -> None:
    """DLQ 실패 기록을 task_executions에 저장."""
    from app.core.database import db_manager
    from app.models.task_execution import TaskExecution
    async with db_manager.get_session() as db:
        db.add(TaskExecution(
            task_id=f"dlq-{task_name}-{id(exception_info)}",
            task_name=task_name, queue="dead_letter",
            status="dead_letter", params=task_args,
            error_message=exception_info[:2000],
            blog_id=task_args.get("blog_id"),
        ))
        await db.commit()


@celery_app.task(name="tasks.handle_dead_letter", queue="callback_queue")
def handle_dead_letter(
    task_name: str, task_args: dict, exception_info: str,
) -> dict:
    """DLQ 핸들러: 최대 재시도 초과 작업을 DB에 기록."""
    logger.error(f"[DLQ] 최종 실패 | task={task_name} | error={exception_info[:200]}")
    try:
        run_async(_async_record_dead_letter(task_name, task_args, exception_info))
    except Exception as e:
        logger.error(f"[DLQ] DB 기록 실패: {e}")
    return {"recorded": True, "task_name": task_name}


from app.core.celery_publish_tasks import (  # noqa: F401, E402
    publish_post,
    publish_batch,
    republish_post,
)
from app.core.celery_utility_tasks import (  # noqa: F401, E402
    collect_keywords,
    transfer_titles,
)
