"""Celery 유틸리티 태스크 정의 모듈.

- collect_keywords: 키워드/제목 수집 태스크
- transfer_titles: 제목 이동 태스크
- bulk_collect_cycle: 대량 수집 1 사이클 실행 태스크 (본체는
  `app.services.bulk_collect.cycle_runner.run_bulk_collect_cycle`)
"""
import logging
import time
from typing import Optional

from app.core.celery_async_bridge import run_async
from app.core.celery_config import celery_app

logger = logging.getLogger(__name__)


async def _async_collect(
    module_id: int,
    action_type: str,
    flow_id: int = None,
) -> dict:
    """수집/데이터 모듈 비동기 실행 로직.

    flows_execute.py 의 _execute_collect_module / _execute_data_module 을
    직접 재사용하여 동일 로직을 보장한다. 실행 완료 후 AutorunLog 에
    결과를 저장하여 사용자가 동작 로그에서 수집 건수·실패 사유 등을
    확인할 수 있게 한다.
    """
    # Celery prefork 워커에서 전역 db_manager 의 풀 커넥션은 첫 이벤트 루프에
    # 바인딩되어 두 번째 태스크부터 "Event loop is closed" 로 죽는다. NullPool
    # 기반 celery_db_session 을 사용한다(cycle_runner·publish 태스크와 동일).
    from app.core.celery_async_bridge import celery_db_session

    started_at = time.monotonic()
    async with celery_db_session() as db:
        module = await _load_module_with_type(db, module_id)
        if not module:
            return {
                "success": False,
                "message": f"모듈을 찾을 수 없습니다: id={module_id}",
            }

        result = await _dispatch_collect_action(db, module, action_type)
        if result is None:
            return {
                "success": False,
                "message": f"지원하지 않는 액션 타입: {action_type}",
            }

        duration_ms = int((time.monotonic() - started_at) * 1000)
        await _save_collect_autorun_log(
            db=db,
            module=module,
            flow_id=flow_id,
            action_type=action_type,
            result=result,
            duration_ms=duration_ms,
        )
        return result


async def _load_module_with_type(db, module_id: int):
    """Module 을 module_type eager load 와 함께 조회."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.module import Module

    q = await db.execute(
        select(Module)
        .where(Module.id == module_id)
        .options(selectinload(Module.module_type))
    )
    return q.scalar_one_or_none()


async def _dispatch_collect_action(
    db, module, action_type: str,
) -> Optional[dict]:
    """action_type 에 따라 collect/data 실행 함수로 디스패치."""
    from app.routers.flows_execute import (
        _execute_collect_module,
        _execute_data_module,
    )

    if action_type == "collect":
        return await _execute_collect_module(module, db)
    if action_type == "data":
        return await _execute_data_module(module, db)
    return None


async def _save_collect_autorun_log(
    db,
    module,
    flow_id,
    action_type: str,
    result: dict,
    duration_ms: int,
) -> None:
    """collect/data task 실행 결과를 AutorunLog 에 영구 기록.

    queue_register 만 남아있어 사용자가 실제 수집 결과를 못 보던 문제 해결.
    """
    try:
        from app.models.autorun_log import AutorunLog
        from app.services.autorun_message_builder import (
            build_collect_log_stats,
        )

        status = _resolve_autorun_status(result)
        flow_name, user_id = await _resolve_flow_meta(db, module, flow_id)

        # collect/bulk_collect 는 전용 빌더로 "제목 N개, 키워드/URL M개 수집"
        # 형태의 건수 메시지 + posts 통계 컬럼을 채운다.
        # data 등 그 외 액션은 None 이 반환되므로 기존 메시지로 폴백한다.
        stats = build_collect_log_stats(result, action_type)
        if stats is not None:
            message = stats.message
        else:
            message = _build_autorun_message(action_type, result)

        log = AutorunLog.create_execution_log(
            user_id=user_id,
            flow_id=flow_id or None,
            action=action_type,
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
    except Exception as log_err:  # noqa: BLE001
        logger.warning(
            f"[TASK:{action_type.upper()}] AutorunLog 저장 실패: {log_err}"
        )


def _resolve_autorun_status(result: dict) -> str:
    """task 결과 dict 로부터 AutorunLog status 결정."""
    if result.get("skipped"):
        return "skipped"
    if result.get("success"):
        return "success"
    return "failed"


async def _resolve_flow_meta(db, module, flow_id) -> tuple:
    """flow_id 가 있으면 Flow row 조회하여 (flow_name, user_id) 반환."""
    from sqlalchemy import select
    from app.models.flow import Flow

    flow_name = ""
    user_id = getattr(module, "user_id", None) or 1
    if flow_id:
        f = await db.execute(select(Flow).where(Flow.id == flow_id))
        f_row = f.scalar_one_or_none()
        if f_row:
            flow_name = f_row.name
            user_id = f_row.user_id
    return flow_name, user_id


def _build_autorun_message(action_type: str, result: dict) -> str:
    """AutorunLog message 빌드 (collect 의 경우 수집 건수 prefix 추가)."""
    message_parts = [result.get("message", "")[:200] or ""]
    if action_type == "collect":
        saved = result.get("total_saved")
        collected = result.get("total_collected")
        if saved is not None or collected is not None:
            message_parts.insert(
                0,
                f"saved={saved or 0} / collected={collected or 0}",
            )
    return " | ".join([m for m in message_parts if m]).strip()


@celery_app.task(
    bind=True,
    name="tasks.collect_keywords",
    queue="utility_queue",
    max_retries=0,
    acks_late=False,       # 시작 시 즉시 ack: 90분 작업이라 worker 재시작/메모리
                           # 초과 graceful restart 시 broker 가 redeliver 하는 것을
                           # 방지. 글로벌 task_acks_late=True 를 task 단위로 override.
                           # max_retries=0 이므로 명시적 재시도도 발생하지 않음.
    soft_time_limit=5400,  # 90분: bulk collect Phase 2 sitemap 크롤링은 30~80분 소요
    time_limit=5700,       # 95분 하드 제한
)
def collect_keywords(
    self,
    module_id: int,
    flow_id: int = None,
) -> dict:
    """키워드/제목 수집 태스크.

    모듈 설정에 따라 키워드와 제목을 수집합니다.
    대량 수집(bulk) 활성화 시 sitemap 크롤링에 수십 분이 소요될 수 있으므로
    time_limit을 충분히 크게 설정합니다.

    Args:
        module_id: 수집 모듈 ID
        flow_id: 플로우 ID (선택)

    Returns:
        dict: {"success": bool, "message": str, "collected_count": int}
    """
    logger.info(
        f"[TASK:COLLECT] 시작 | module={module_id} | flow={flow_id}"
    )

    try:
        result = run_async(_async_collect(module_id, "collect", flow_id=flow_id))
        logger.info(
            f"[TASK:COLLECT] 완료 | module={module_id} | "
            f"saved={result.get('total_saved', 0)} / "
            f"collected={result.get('total_collected', 0)}"
        )
        return result
    except Exception as exc:
        logger.error(f"[TASK:COLLECT] 예외 | module={module_id} | {exc}")
        raise


@celery_app.task(
    bind=True,
    name="tasks.transfer_titles",
    queue="utility_queue",
    max_retries=0,
    acks_late=False,       # 시작 시 즉시 ack (collect_keywords 와 동일 사유)
    soft_time_limit=1800,  # 30분
    time_limit=2100,        # 35분 하드 제한
)
def transfer_titles(
    self,
    module_id: int,
    flow_id: int = None,
) -> dict:
    """제목 이동 태스크.

    데이터 모듈 설정에 따라 제목을 이동/처리합니다.

    Args:
        module_id: 데이터 모듈 ID
        flow_id: 플로우 ID (선택)

    Returns:
        dict: {"success": bool, "message": str}
    """
    logger.info(
        f"[TASK:DATA] 시작 | module={module_id} | flow={flow_id}"
    )

    try:
        result = run_async(_async_collect(module_id, "data", flow_id=flow_id))
        logger.info(
            f"[TASK:DATA] 완료 | module={module_id} | "
            f"success={result.get('success')}"
        )
        return result
    except Exception as exc:
        logger.error(f"[TASK:DATA] 예외 | module={module_id} | {exc}")
        raise


# ==========================================================================
# Phase B: 대량 수집 모듈 (bulk_collect) 1 사이클 실행 태스크
# 본체 로직은 `app.services.bulk_collect.cycle_runner` 로 분리됨.
# ==========================================================================

@celery_app.task(
    bind=True,
    name="tasks.bulk_collect_cycle",
    queue="utility_queue",
    max_retries=0,
    acks_late=False,        # 장시간 작업: 즉시 ack 로 redeliver 방지
    soft_time_limit=1800,   # 30분 (cycle_max_duration_sec 보다 충분히 크게)
    time_limit=2100,         # 35분 하드 제한
)
def bulk_collect_cycle(self, module_id: int, flow_id: int = None) -> dict:
    """대량 수집 모듈 1 사이클 실행 (Celery entry).

    실제 비동기 사이클 본문은
    `app.services.bulk_collect.cycle_runner.run_bulk_collect_cycle`
    가 담당한다 (500줄 룰 분리). 사이클 완료 후 결과를 AutorunLog 에
    저장하여 동작 로그에서 "대량 수집 - 제목 N개 수집" 형태로 확인할 수
    있게 한다 (collect 모듈과 동일 패턴).

    Args:
        module_id: 대량 수집 모듈 ID.
        flow_id: 플로우 ID (선택). 결과 로그에 플로우명·user_id 연결용.

    Returns:
        실행 결과 dict.
    """
    from app.services.bulk_collect.cycle_runner import (
        run_bulk_collect_cycle,
    )

    logger.info(
        f"[TASK:BULK_COLLECT] 시작 | module={module_id} | flow={flow_id}"
    )
    try:
        result = run_async(
            run_bulk_collect_cycle(module_id, flow_id=flow_id)
        )
        logger.info(
            "[TASK:BULK_COLLECT] 완료 | module=%s | %s",
            module_id, result.get("message", ""),
        )
        return result
    except Exception as exc:
        logger.error(
            "[TASK:BULK_COLLECT] 예외 | module=%s | %s", module_id, exc,
        )
        raise
