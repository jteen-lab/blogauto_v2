"""대량 수집(bulk_collect) 1 사이클 실행 러너.

Celery 태스크 `tasks.bulk_collect_cycle` 의 본문 로직을 분리한 모듈.

`celery_utility_tasks.py` 가 500줄 룰을 초과하여 분리되었으며, Celery 태스크
데코레이터는 `celery_utility_tasks.py` 에 남기고, 실제 비동기 사이클 본체와
모든 헬퍼는 이 모듈로 이전한다.

외부 진입점:
    - run_bulk_collect_cycle(module_id): Celery 태스크에서 호출.

내부 헬퍼는 모두 private(`_` 접두사) 로 유지된다.
"""
import logging
import time
from typing import Optional

from app.services.bulk_collect.cycle_tuning import (
    BACKLOG_THRESHOLD,
    build_skipped_cycle_result,
    check_callback_backlog,
)

logger = logging.getLogger(__name__)

__all__ = ["run_bulk_collect_cycle"]


async def run_bulk_collect_cycle(
    module_id: int, flow_id: Optional[int] = None,
) -> dict:
    """대량 수집 모듈 1 사이클 비동기 실행 본체.

    동작 순서:
        1. Module 로드 및 settings 파싱
        2. Timebox 생성 (cycle_max_duration_sec)
        3. DomainLimiter 생성 (parallel_titles, domain_concurrency)
        4. (Phase D-2) direct_input 모드 + 첫 사이클이면 input_urls 자동 적재
        5. ChunkProcessor 로 collected_urls pending 청크 처리
        6. LastmodTracker 로 사이클 통계 저장
        7. 결과 AutorunLog 저장 (동작 로그 노출)
        8. 결과 dict 반환

    Phase B-042 (W2) 적재 시 source_module_id 정책:
        - direct_input 모드: 적재 시 `CollectedUrl.source_module_id=module_id`
          명시 필요. Phase D-2 부터 본 태스크가 첫 사이클에서 자동 적재.
        - from_collect_module 모드: 레거시(keyword_collector_service) 적재
          row 는 NULL → ChunkProcessor 가 NULL 풀을 가져온다.

    Args:
        module_id: 대량 수집 모듈 ID.
        flow_id: 호출 플로우 ID (선택). 결과 로그 연결용.

    Returns:
        실행 결과 dict (success, processed, failed, duration_sec, message).

    Note:
        Celery prefork 워커는 ``run_async`` 가 태스크마다 새 이벤트 루프를
        만든다. 글로벌 ``db_manager`` 의 풀 커넥션은 첫 루프에 바인딩되어
        두 번째 태스크부터 "Event loop is closed" 로 죽으므로, NullPool
        기반의 ``celery_db_session`` 을 사용한다 (celery_publish_tasks 동일).
    """
    from app.core.celery_async_bridge import celery_db_session

    started_at = time.monotonic()
    async with celery_db_session() as db:
        module = await _load_bulk_module(db, module_id)
        if not module:
            return {
                "success": False,
                "message": f"모듈을 찾을 수 없습니다 id={module_id}",
                "processed": 0,
                "failed": 0,
                "duration_sec": 0,
            }
        result = await _run_bulk_cycle_with_module(db, module)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        await _save_bulk_collect_autorun_log(
            db, module, flow_id, result, duration_ms,
        )
        return result


async def _save_bulk_collect_autorun_log(
    db, module, flow_id, result: dict, duration_ms: int,
) -> None:
    """대량 수집 사이클 결과를 AutorunLog 에 저장.

    collect 모듈과 동일한 메시지 빌더(``build_collect_log_stats``)로
    "대량 수집 - 제목 N개 수집 (실패 M개, 소요 S초)" 메시지 + posts 통계
    컬럼을 남긴다. ``celery_utility_tasks`` 역참조(순환 import)를 피하기 위해
    저장 로직을 자체 구현한다. 로그 저장 실패가 사이클 결과를 깨지 않도록
    방어한다.

    Args:
        db: AsyncSession.
        module: 대량 수집 Module.
        flow_id: 플로우 ID (선택).
        result: 사이클 결과 dict.
        duration_ms: 사이클 소요 시간(ms).
    """
    try:
        from sqlalchemy import select
        from app.models.autorun_log import AutorunLog
        from app.models.flow import Flow
        from app.services.autorun_message_builder import (
            build_collect_log_stats,
        )

        # 상태 결정: skipped > success/failed
        if result.get("skipped"):
            status = "skipped"
        elif result.get("success"):
            status = "success"
        else:
            status = "failed"

        # flow_id 가 있으면 Flow 조회하여 flow_name / user_id 연결
        flow_name = ""
        user_id = getattr(module, "user_id", None) or 1
        if flow_id:
            f_row = (
                await db.execute(select(Flow).where(Flow.id == flow_id))
            ).scalar_one_or_none()
            if f_row:
                flow_name = f_row.name
                user_id = f_row.user_id

        stats = build_collect_log_stats(result, "bulk_collect")
        message = stats.message if stats else result.get("message", "")

        log = AutorunLog.create_execution_log(
            user_id=user_id,
            flow_id=flow_id or None,
            action="bulk_collect",
            status=status,
            flow_name=flow_name,
            module_name=module.name,
            blog_name="-",
            post_title="",
            action_time=None,
            duration_ms=duration_ms,
            message=message,
        )
        if stats is not None:
            log.posts_processed = stats.posts_processed
            log.posts_success = stats.posts_success
            log.posts_failed = stats.posts_failed
        db.add(log)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[TASK:BULK_COLLECT] AutorunLog 저장 실패 err=%s", exc,
        )


async def _load_bulk_module(db, module_id: int):
    """대량 수집 모듈 ORM 인스턴스를 로딩.

    Args:
        db: AsyncSession.
        module_id: 모듈 ID.

    Returns:
        Module 인스턴스 또는 None.
    """
    from sqlalchemy import select
    from app.models.module import Module

    result = await db.execute(
        select(Module).where(Module.id == module_id)
    )
    return result.scalar_one_or_none()


async def _maybe_skip_for_backlog(
    module_id: int, params: dict,
) -> Optional[dict]:
    """4-2-C. 콜백 큐 적체 시 사이클 스킵 결과를 반환.

    Returns:
        스킵 결과 dict (스킵 시) 또는 None (정상 진행).
    """
    if not params["pause_on_callback_backlog"]:
        return None
    backlog = await check_callback_backlog()
    if backlog <= BACKLOG_THRESHOLD:
        return None
    msg = (
        f"콜백 큐 적체로 사이클 스킵 backlog={backlog} "
        f"threshold={BACKLOG_THRESHOLD}"
    )
    logger.warning("[BULK_COLLECT] %s module=%s", msg, module_id)
    return build_skipped_cycle_result("callback_backlog", msg)


async def _run_bulk_cycle_with_module(db, module) -> dict:
    """모듈 로딩 상태에서 1 사이클 실행 (재설계 2026-06-04).

    Phase 1: URL탭(블로그 소스)에서 사이트맵을 크롤해 신규 포스트를 적재.
    Phase 2: 적재된 pending 포스트의 제목을 추출해 TempTitle(임시제목탭) 저장.
    Timebox(cycle_max) 안에서만 동작하고, 미처리분은 다음 사이클로 이월(재개).
    """
    from app.services.bulk_collect import (
        ChunkProcessor, DomainLimiter, Timebox,
    )
    from app.services.bulk_collect.from_collect_ingest import (
        ingest_from_url_tab,
    )

    module_id = module.id
    settings = module.settings or {}
    params = _parse_bulk_cycle_params(settings)

    skipped = await _maybe_skip_for_backlog(module_id, params)
    if skipped is not None:
        return skipped

    started = time.monotonic()
    with Timebox(params["cycle_max"]) as timebox:
        # Phase 1 — 사이트맵에서 신규 포스트 URL 적재
        ingest_summary = await ingest_from_url_tab(
            db, module_id,
            blogs_per_cycle=params["blogs_per_cycle"],
            posts_per_blog=params["posts_per_blog"],
            timebox=timebox,
        )
        # Phase 2 — pending 포스트 제목 추출 (남은 시간 동안 drain)
        limiter = DomainLimiter(params["global_conc"], params["domain_conc"])
        processor = ChunkProcessor(db, limiter, timebox)
        title_stats = await _drain_titles(
            processor, module_id, params, timebox,
        )

    duration_sec = int(time.monotonic() - started)
    return _build_cycle_result(ingest_summary, title_stats, duration_sec)


async def _drain_titles(processor, module_id: int, params: dict, timebox):
    """Timebox 안에서 pending 포스트를 배치(100개)로 모두 제목 추출.

    Returns:
        누적 ChunkStats (processed/failed).
    """
    from app.services.bulk_collect import ChunkStats

    total = ChunkStats()
    while not timebox.expired:
        urls = await processor.load_pending_chunk(
            module_id=module_id, chunk_size=100,
            source_mode=params["source_mode"],
            order_mode=params["order_mode"],
        )
        if not urls:
            break
        stats = await processor.process_chunk(urls)
        total.processed += stats.processed
        total.failed += stats.failed
    return total


def _parse_bulk_cycle_params(settings: dict) -> dict:
    """대량 수집 사이클 파라미터 파싱 (재설계 옵션 4종 + 자동 전역 동시).

    옵션 우선순위(구버전 키 호환):
      - blogs_per_cycle: bulk_params.blogs_per_cycle → from_collect.max_urls → 3
      - posts_per_blog: bulk_params.posts_per_blog → chunk_size_initial → 100
      - domain_conc: bulk_params.domain_concurrency → 2
      - cycle_max: bulk_params.cycle_max_duration_sec → 300
      - global_conc: 자동 = blogs_per_cycle × domain_conc (옵션 노출 안 함)

    Args:
        settings: Module.settings JSONB dict.

    Returns:
        파라미터 dict.
    """
    bulk_params = settings.get("bulk_params", {}) or {}
    from_collect = settings.get("from_collect", {}) or {}

    blogs_per_cycle = max(1, int(
        bulk_params.get("blogs_per_cycle")
        or from_collect.get("max_urls")
        or 3
    ))
    posts_per_blog = max(1, int(
        bulk_params.get("posts_per_blog")
        or bulk_params.get("chunk_size_initial")
        or bulk_params.get("chunk_size")
        or 100
    ))
    domain_conc = max(1, int(bulk_params.get("domain_concurrency", 2)))
    return {
        "blogs_per_cycle": blogs_per_cycle,
        "posts_per_blog": posts_per_blog,
        "domain_conc": domain_conc,
        "global_conc": blogs_per_cycle * domain_conc,  # 자동(D-5)
        "cycle_max": int(bulk_params.get("cycle_max_duration_sec", 300)),
        "source_mode": str(
            settings.get("url_source_mode", "from_collect_module")
        ),
        "order_mode": str(
            from_collect.get("order_mode")
            or bulk_params.get("order_mode", "stored")
        ),
        "pause_on_callback_backlog": bool(
            bulk_params.get("pause_on_callback_backlog", False)
        ),
    }


def _build_cycle_result(
    ingest_summary: dict,
    title_stats,
    duration_sec: int,
) -> dict:
    """사이클 결과 dict 를 빌드 (블로그/적재/제목 3단 통계).

    Args:
        ingest_summary: Phase 1 적재 통계.
        title_stats: Phase 2 ChunkStats(제목 수집).
        duration_sec: 사이클 소요 시간(초).

    Returns:
        사이클 실행 결과 dict.
    """
    blogs = int(ingest_summary.get("blogs_processed", 0))
    posts = int(ingest_summary.get("posts_ingested", 0))
    titles = int(title_stats.processed)
    failed = int(title_stats.failed)
    msg = (
        f"블로그 {blogs}개 / 글주소 {posts}개 적재 / "
        f"제목 {titles}개 수집 (소요 {duration_sec}초)"
    )
    return {
        "success": True,
        "message": msg,
        "processed": titles,            # 제목 수집 수 (기존 키 호환)
        "failed": failed,
        "duration_sec": duration_sec,
        "blogs_processed": blogs,
        "posts_ingested": posts,
        "titles_collected": titles,
        "ingest_summary": ingest_summary,
    }
