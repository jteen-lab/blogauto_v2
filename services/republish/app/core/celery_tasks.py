"""
Celery 태스크 정의

설계 문서: generation_module_workplan.md

Phase 3 업데이트:
- recombine_title: TitleRecombiner 서비스 연동 (Phase 2 완료)
- generate_content: ContentGenerator 전체 파이프라인 연동 (Phase 3 완료)
- on_generation_complete: 후처리 로직 구현 (Phase 3 완료)
- generate_image: 이미지 생성 (별도 서비스 연동 필요)
"""
import asyncio
import logging

from app.core.celery_config import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """비동기 코루틴을 동기 Celery 태스크에서 실행"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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


async def _async_generate_content(
    blog_id: int,
    prompt_module_id: int,
    source_title_id: int,
) -> dict:
    """전체 글 생성 파이프라인 비동기 로직"""
    from app.core.database import db_manager
    from app.services.generation.generator import ContentGenerator

    async with db_manager.get_session() as db:
        generator = ContentGenerator(db, user_id=1)
        result = await generator.generate(
            blog_id=blog_id,
            prompt_module_id=prompt_module_id,
            source_title_id=source_title_id,
        )
        return {
            "success": result.success,
            "crawling_post_id": result.crawling_post_id,
            "generation_history_id": result.generation_history_id,
            "recombined_title": result.recombined_title,
            "final_html": result.final_html,
            "reference_count": result.reference_count,
            "generation_time_seconds": result.generation_time_seconds,
            "content_length": result.content_length,
            "ai_model_title": result.ai_model_title,
            "ai_model_content": result.ai_model_content,
            "error": result.error,
            "status": "completed" if result.success else "failed",
        }


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

        # 원본 제목 사용 처리 (이미 generator에서 처리하지만 안전장치)
        title = await db.get(MainTitle, source_title_id)
        if title and title.status != "used":
            title.mark_used()
            await db.commit()
            logger.info(
                f"[COMPLETE] 제목 사용 처리 완료 | title_id={source_title_id}"
            )

        return {
            "success": True,
            "message": "생성 완료 후처리 성공",
            "generation_history_id": generation_history_id,
            "blog_id": blog_id,
        }


@celery_app.task(
    bind=True,
    name="app.core.celery_tasks.recombine_title",
    max_retries=2,
    default_retry_delay=10,
)
def recombine_title(
    self,
    original_title: str,
    prompt_module_id: int,
    blog_id: int,
    generation_request_id: str,
) -> dict:
    """
    제목 재조합 태스크

    Args:
        original_title: 원본 정식 제목
        prompt_module_id: 프롬프트 모듈 ID
        blog_id: 블로그 ID
        generation_request_id: 생성 요청 고유 ID

    Returns:
        dict: {"recombined_title": str, "ai_model": str, ...}
    """
    logger.info(
        f"[TASK:RECOMBINE] 시작 | title='{original_title[:30]}...' "
        f"| request_id={generation_request_id}"
    )

    try:
        result = _run_async(
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
        return {
            "recombined_title": original_title,
            "ai_model": "failed",
            "ai_provider": "failed",
            "is_modified": False,
            "error": str(exc),
        }


@celery_app.task(
    bind=True,
    name="app.core.celery_tasks.generate_content",
    max_retries=2,
    default_retry_delay=30,
)
def generate_content(
    self,
    recombined_title: str,
    prompt_module_id: int,
    blog_id: int,
    source_title_id: int,
    generation_request_id: str,
) -> dict:
    """
    글 생성 태스크 (전체 파이프라인)

    ContentGenerator를 사용하여 전체 파이프라인 실행:
    제목 재조합 → 참조자료 수집 → 글 생성 → 내부링크 → 치환 → 저장

    Args:
        recombined_title: 재조합된 제목 (로깅용, 실제는 파이프라인에서 재실행)
        prompt_module_id: 프롬프트 모듈 ID
        blog_id: 블로그 ID
        source_title_id: 원본 정식 제목 ID
        generation_request_id: 생성 요청 고유 ID

    Returns:
        dict: 생성 결과 (success, content, reference_count 등)
    """
    logger.info(
        f"[TASK:CONTENT] 시작 | title='{recombined_title[:30]}...' "
        f"| request_id={generation_request_id}"
    )

    try:
        result = _run_async(
            _async_generate_content(
                blog_id, prompt_module_id, source_title_id
            )
        )

        if result["success"]:
            logger.info(
                f"[TASK:CONTENT] 완료 | "
                f"title='{result.get('recombined_title', '')[:30]}' "
                f"| refs={result['reference_count']} "
                f"| length={result['content_length']} "
                f"| time={result['generation_time_seconds']}s"
            )
        else:
            logger.warning(
                f"[TASK:CONTENT] 실패 | error={result.get('error')}"
            )

        return result

    except Exception as exc:
        logger.error(f"[TASK:CONTENT] 실패: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {
            "success": False,
            "content": None,
            "reference_count": 0,
            "ai_model_content": "failed",
            "error": str(exc),
            "status": "failed",
        }


@celery_app.task(
    bind=True,
    name="app.core.celery_tasks.generate_image",
    max_retries=1,
    default_retry_delay=15,
)
def generate_image(
    self,
    title: str,
    content_summary: str,
    blog_id: int,
    generation_request_id: str,
) -> dict:
    """
    이미지 생성 태스크

    이미지 생성 서비스 연동은 별도 구현 필요.
    현재는 이미지 없이 진행 가능하도록 빈 결과 반환.

    Args:
        title: 글 제목
        content_summary: 글 요약 (이미지 생성 프롬프트용)
        blog_id: 블로그 ID
        generation_request_id: 생성 요청 고유 ID

    Returns:
        dict: {"image_urls": list, "ai_model": str}
    """
    logger.info(
        f"[TASK:IMAGE] 시작 | title='{title[:30]}...' "
        f"| request_id={generation_request_id}"
    )

    # 이미지 생성은 선택적 기능 - 미구현 시 빈 결과 반환
    logger.info("[TASK:IMAGE] 이미지 생성 서비스 미연동 - 스킵")
    return {
        "image_urls": [],
        "ai_model": None,
        "status": "skipped",
    }


@celery_app.task(
    bind=True,
    name="app.core.celery_tasks.on_generation_complete",
    max_retries=1,
    default_retry_delay=5,
)
def on_generation_complete(
    self,
    generation_request_id: str,
    blog_id: int,
    source_title_id: int,
    crawling_post_id: int,
    generation_history_id: int,
) -> dict:
    """
    생성 완료 후 콜백 태스크

    후처리:
    - 원본 제목 사용 처리 (안전장치)
    - 생성 완료 로그 기록

    Args:
        generation_request_id: 생성 요청 고유 ID
        blog_id: 블로그 ID
        source_title_id: 원본 정식 제목 ID
        crawling_post_id: 저장된 크롤링 포스트 ID
        generation_history_id: 생성 이력 ID

    Returns:
        dict: {"success": bool, "message": str}
    """
    logger.info(
        f"[TASK:COMPLETE] 시작 | request_id={generation_request_id} "
        f"| history_id={generation_history_id}"
    )

    try:
        result = _run_async(
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
        return {
            "success": False,
            "message": f"후처리 실패: {str(exc)}",
        }
