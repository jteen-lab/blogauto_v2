"""Celery 유틸리티 태스크 정의 모듈.

- collect_keywords: 키워드/제목 수집 태스크
- transfer_titles: 제목 이동 태스크
"""
import logging
import time

from app.core.celery_async_bridge import run_async
from app.core.celery_config import celery_app

logger = logging.getLogger(__name__)


async def _async_collect(
    module_id: int,
    action_type: str,
    flow_id: int = None,
) -> dict:
    """수집/데이터 모듈 비동기 실행 로직.

    flows_execute.py의 _execute_collect_module / _execute_data_module을
    직접 재사용하여 동일 로직을 보장합니다.

    실행 완료 후 AutorunLog 에 결과를 저장하여 사용자가 동작 로그에서
    수집 건수·실패 사유 등을 확인할 수 있게 한다.
    """
    from app.core.database import db_manager
    from app.models.module import Module
    from sqlalchemy.orm import selectinload

    started_at = time.monotonic()

    async with db_manager.get_session() as db:
        from sqlalchemy import select
        q = await db.execute(
            select(Module)
            .where(Module.id == module_id)
            .options(selectinload(Module.module_type))
        )
        module = q.scalar_one_or_none()

        if not module:
            return {
                "success": False,
                "message": f"모듈을 찾을 수 없습니다: id={module_id}",
            }

        from app.routers.flows_execute import (
            _execute_collect_module,
            _execute_data_module,
        )

        if action_type == "collect":
            result = await _execute_collect_module(module, db)
        elif action_type == "data":
            result = await _execute_data_module(module, db)
        else:
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
        from app.models.flow import Flow
        from sqlalchemy import select

        if result.get("skipped"):
            status = "skipped"
        elif result.get("success"):
            status = "success"
        else:
            status = "failed"

        flow_name = ""
        user_id = getattr(module, "user_id", None) or 1
        if flow_id:
            f = await db.execute(select(Flow).where(Flow.id == flow_id))
            f_row = f.scalar_one_or_none()
            if f_row:
                flow_name = f_row.name
                user_id = f_row.user_id

        # collect 의 핵심 지표(수집 건수)를 메시지에 포함
        message_parts = [result.get("message", "")[:200] or ""]
        if action_type == "collect":
            saved = result.get("total_saved")
            collected = result.get("total_collected")
            if saved is not None or collected is not None:
                message_parts.insert(
                    0,
                    f"saved={saved or 0} / collected={collected or 0}"
                )
        message = " | ".join([m for m in message_parts if m]).strip()

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
        db.add(log)
        await db.commit()
    except Exception as log_err:
        logger.warning(
            f"[TASK:{action_type.upper()}] AutorunLog 저장 실패: {log_err}"
        )


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
