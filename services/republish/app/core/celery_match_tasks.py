"""
Phase 3 비동기화: 매칭/필터/전환 Celery 태스크.

app 동기로 화면을 멈추게 하던 매칭/필터/전환 작업을 Celery 워커로
이전한다. 라우터는 task.delay() 로 디스패치하고 task_id 를 반환하며,
프론트는 GET /api/v1/tasks/{task_id} 로 진행 상태를 폴링한다.

큐: utility_queue (수집·데이터 처리와 같은 계열)
"""
import logging

from app.core.celery_config import celery_app
from app.core.celery_async_bridge import run_async
from app.core.database import db_manager

logger = logging.getLogger(__name__)


@celery_app.task(
    name="match.auto_match_blog",
    queue="utility_queue",
    soft_time_limit=300,
    time_limit=360,
)
def task_auto_match_blog(blog_id: int, threshold: float) -> dict:
    """블로그 자동 매칭 (AutoMatchService) 비동기 실행."""
    from app.services.auto_match_service import AutoMatchService

    async def _run():
        async with db_manager.get_session() as s:
            svc = AutoMatchService(s)
            return await svc.auto_match(blog_id, threshold)

    result = run_async(_run())
    logger.info(
        f"[MATCH_TASK] auto_match_blog 완료 | blog={blog_id} | result={result}"
    )
    return {"blog_id": blog_id, **result}


@celery_app.task(
    name="match.rematch_blog",
    queue="utility_queue",
    soft_time_limit=300,
    time_limit=360,
)
def task_rematch_blog(blog_id: int, threshold: float) -> dict:
    """블로그 재매칭 (SimilarityMatcherService) 비동기 실행.

    1) 기존 매칭 상태를 pending 으로 리셋
    2) match_blog_posts 로 재매칭
    """
    from sqlalchemy import update as sql_update
    from app.models.crawled_post import CrawledPost
    from app.services.similarity_matcher_service import SimilarityMatcherService

    async def _run():
        async with db_manager.get_session() as s:
            reset = await s.execute(
                sql_update(CrawledPost)
                .where(CrawledPost.blog_id == blog_id)
                .values(
                    match_status="pending",
                    matched_main_title_id=None,
                    match_score=None,
                )
            )
            reset_count = reset.rowcount
            await s.commit()
            svc = SimilarityMatcherService(s)
            matched, unmatched = await svc.match_blog_posts(blog_id, threshold)
            return {
                "processed": reset_count,
                "matched": matched,
                "unmatched": unmatched,
            }

    result = run_async(_run())
    logger.info(
        f"[MATCH_TASK] rematch_blog 완료 | blog={blog_id} | result={result}"
    )
    return {"blog_id": blog_id, **result}


@celery_app.task(
    name="filter.apply_filters",
    queue="utility_queue",
    soft_time_limit=600,
    time_limit=720,
)
def task_apply_filters() -> dict:
    """활성 필터를 기존 임시제목·시드키워드에 적용 (대량 삭제) 비동기 실행."""
    from app.services.filter_apply_service import apply_filters_to_existing_data

    async def _run():
        async with db_manager.get_session() as s:
            res = await apply_filters_to_existing_data(s)
            return {
                "deleted_titles": res.deleted_titles,
                "deleted_keywords": res.deleted_keywords,
                "total": res.total,
            }

    result = run_async(_run())
    logger.info(f"[FILTER_TASK] apply_filters 완료 | result={result}")
    return result


@celery_app.task(
    name="title.transfer_to_main",
    queue="utility_queue",
    soft_time_limit=600,
    time_limit=720,
)
def task_transfer_temp_to_main(
    temp_title_ids: list,
    auto_group: bool = True,
    similarity_threshold: float = 0.7,
) -> dict:
    """임시제목을 정식제목으로 일괄 전환 (move_temp_to_main) 비동기 실행."""
    from app.services.title_transfer_service import move_temp_to_main

    async def _run():
        async with db_manager.get_session() as s:
            return await move_temp_to_main(
                db=s,
                temp_title_ids=temp_title_ids,
                auto_group=auto_group,
                threshold=similarity_threshold,
            )

    result = run_async(_run())
    logger.info(
        f"[TRANSFER_TASK] transfer_to_main 완료 | count={len(temp_title_ids)} | "
        f"result={result}"
    )
    return result
