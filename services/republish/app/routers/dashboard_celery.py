"""
Celery 큐/워커 모니터링 API 라우터

큐/워커 Phase 4:
- 큐별 대기 작업 수 조회
- task_executions 실행 이력 조회
- Flower 모니터링 URL 제공
"""
import asyncio
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.task_execution import TaskExecution

logger = get_logger("dashboard_celery", "dashboard.log")

router = APIRouter(prefix="/dashboard/celery", tags=["Celery 모니터링"])

# 모니터링 대상 큐 목록
MONITORED_QUEUES = [
    "generation_queue",
    "publish_queue",
    "image_queue",
    "utility_queue",
    "callback_queue",
]

# 워커 이름 → 키 매핑
WORKER_KEY_MAP = {
    "generation": "generation",
    "publish": "publish",
    "utility": "utility",
}

# 워커 상태 캐시 (inspect 호출 비용 절감)
_worker_cache: dict = {}
_worker_cache_time: float = 0.0
_CACHE_TTL: float = 5.0


@router.get("/status", summary="Celery 큐/워커 상태")
async def get_celery_status(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Celery 큐별 대기 작업 수와 task_executions 상태 집계를 조회합니다.

    Returns:
        dict: queues(큐별 대기 수), task_status(상태별 카운트), total_pending
    """
    queue_lengths = _get_queue_lengths()
    status_counts = await _get_status_counts(db)

    return {
        "queues": queue_lengths,
        "task_status": status_counts,
        "total_pending": (
            max(queue_lengths.get("generation_queue", 0), 0)
            + max(queue_lengths.get("publish_queue", 0), 0)
        ),
    }


@router.get("/history", summary="태스크 실행 이력")
async def get_task_history(
    limit: int = 20,
    status: Optional[str] = None,
    task_name: Optional[str] = None,
    blog_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db_session),
) -> list:
    """
    task_executions 테이블에서 최근 실행 이력을 조회합니다.

    Args:
        limit: 조회 건수 (최대 100, 기본 20)
        status: 상태 필터 (pending/running/success/failed/retrying/dead_letter)
        task_name: 태스크 이름 필터
        blog_id: 블로그 ID 필터

    Returns:
        list[dict]: 태스크 실행 이력 목록
    """
    limit = min(limit, 100)

    query = (
        select(TaskExecution)
        .order_by(TaskExecution.created_at.desc())
        .limit(limit)
    )

    if status:
        query = query.where(TaskExecution.status == status)
    if task_name:
        query = query.where(TaskExecution.task_name == task_name)
    if blog_id:
        query = query.where(TaskExecution.blog_id == blog_id)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [_serialize_task(t) for t in tasks]


@router.get("/flower-url", summary="Flower 모니터링 URL")
async def get_flower_url() -> dict:
    """
    Flower 모니터링 대시보드 URL을 반환합니다.

    Flower는 docker-compose.yml에서 5555 포트로 노출되어 있습니다.

    Returns:
        dict: {"url": str, "description": str}
    """
    flower_host = os.getenv("FLOWER_HOST", "localhost")
    flower_port = os.getenv("FLOWER_PORT", "5555")

    return {
        "url": f"http://{flower_host}:{flower_port}",
        "description": "Celery Flower 모니터링 대시보드",
    }


def _get_queue_lengths() -> dict:
    """Redis에서 각 큐의 대기 작업 수를 조회합니다.

    Returns:
        dict: 큐 이름 -> 대기 작업 수 (-1이면 조회 실패)
    """
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = redis_lib.from_url(redis_url)

        queue_lengths = {}
        for q in MONITORED_QUEUES:
            try:
                queue_lengths[q] = redis_client.llen(q)
            except Exception:
                queue_lengths[q] = -1

        redis_client.close()
        return queue_lengths
    except Exception as e:
        logger.warning(f"[CELERY_MONITOR] Redis 연결 실패: {e}")
        return {q: -1 for q in MONITORED_QUEUES}


async def _get_status_counts(db: AsyncSession) -> dict:
    """task_executions 테이블에서 상태별 카운트를 집계합니다.

    Args:
        db: DB 세션

    Returns:
        dict: 상태 -> 카운트
    """
    try:
        result = await db.execute(
            select(TaskExecution.status, func.count(TaskExecution.id))
            .group_by(TaskExecution.status)
        )
        return {row[0]: row[1] for row in result.fetchall()}
    except Exception as e:
        logger.warning(f"[CELERY_MONITOR] task_executions 조회 실패: {e}")
        return {}


def _serialize_task(t: TaskExecution) -> dict:
    """TaskExecution 인스턴스를 API 응답용 딕셔너리로 변환합니다.

    Args:
        t: TaskExecution 인스턴스

    Returns:
        dict: 직렬화된 태스크 데이터
    """
    return {
        "id": t.id,
        "task_id": t.task_id,
        "task_name": t.task_name,
        "queue": t.queue,
        "status": t.status,
        "blog_id": t.blog_id,
        "module_id": t.module_id,
        "flow_id": t.flow_id,
        "priority": t.priority,
        "retry_count": t.retry_count,
        "error_message": t.error_message,
        "created_at": (
            t.created_at.isoformat() if t.created_at else None
        ),
        "started_at": (
            t.started_at.isoformat() if t.started_at else None
        ),
        "completed_at": (
            t.completed_at.isoformat() if t.completed_at else None
        ),
    }


@router.get("/workers", summary="Celery 워커 실시간 상태")
async def get_worker_status() -> dict:
    """
    Celery inspect()와 Redis LLEN을 조합하여 워커 실시간 상태를 조회합니다.

    Returns:
        dict: workers(워커별 상태), queues(큐별 대기 수), total_queued, timestamp
    """
    from datetime import datetime, timezone

    loop = asyncio.get_event_loop()
    worker_info = await loop.run_in_executor(None, _inspect_workers_cached)
    queue_lengths = await loop.run_in_executor(None, _get_queue_lengths)

    total_queued = sum(
        max(v, 0) for k, v in queue_lengths.items()
        if v >= 0 and k not in ("callback_queue",)
    )

    return {
        "workers": worker_info,
        "queues": queue_lengths,
        "total_queued": total_queued,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _inspect_workers_cached() -> dict:
    """5초 TTL 캐시가 적용된 워커 상태 조회."""
    global _worker_cache, _worker_cache_time

    now = time.monotonic()
    if now - _worker_cache_time < _CACHE_TTL and _worker_cache:
        return _worker_cache

    result = _inspect_workers()
    _worker_cache = result
    _worker_cache_time = now
    return result


def _inspect_workers() -> dict:
    """
    Celery inspect()로 워커 상태를 조회합니다.

    동기 함수이므로 run_in_executor로 호출해야 합니다.
    timeout=3초로 설정하여 워커가 응답하지 않는 경우 빠르게 반환합니다.
    """
    result = {
        key: {
            "name": None, "status": "offline", "active_tasks": 0,
            "processed": 0, "concurrency": 0, "uptime": None,
        }
        for key in WORKER_KEY_MAP.values()
    }

    try:
        from ..core.celery_config import celery_app

        inspector = celery_app.control.inspect(timeout=3.0)
        ping_response = inspector.ping() or {}
        active_response = inspector.active() or {}
        stats_response = inspector.stats() or {}

        for worker_name in ping_response:
            worker_key = _resolve_worker_key(worker_name)
            if worker_key is None:
                continue
            result[worker_key]["name"] = worker_name
            result[worker_key]["status"] = "online"
            result[worker_key]["active_tasks"] = len(
                active_response.get(worker_name, [])
            )
            _fill_worker_stats(result[worker_key], stats_response.get(worker_name, {}))

    except Exception as e:
        logger.warning(f"[WORKER_STATUS] inspect 실패: {e}")

    return result


def _fill_worker_stats(info: dict, stats: dict) -> None:
    """워커 stats 응답에서 processed/concurrency/uptime을 추출합니다."""
    total_tasks = stats.get("total", {})
    if isinstance(total_tasks, dict):
        info["processed"] = int(sum(
            v for v in total_tasks.values() if isinstance(v, (int, float))
        ))

    info["concurrency"] = stats.get("pool", {}).get("max-concurrency", 0)

    clock = stats.get("clock")
    if clock:
        hours = int(clock) // 3600
        days, rem = divmod(hours, 24)
        info["uptime"] = f"{days}d {rem}h" if days > 0 else f"{rem}h"


def _resolve_worker_key(worker_name: str) -> str | None:
    """
    워커 이름에서 키를 추출합니다.

    Args:
        worker_name: Celery 워커 이름 (예: "generation@hostname")
    """
    for prefix, key in WORKER_KEY_MAP.items():
        if worker_name.startswith(prefix):
            return key
    return None
