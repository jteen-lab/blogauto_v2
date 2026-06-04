"""대량 수집 사이클 튜닝 유틸리티 (4-2-A/C/D 핫픽스).

`app/core/celery_utility_tasks.py` 의 분량 한도(500줄) 준수를 위해
사이클 운영 옵션 관련 헬퍼들을 본 모듈로 분리.

포함 기능:
    - _compute_adaptive_chunk_size: 적응형 청크 크기 (4-2-A)
    - _is_quiet_hours_kst / _apply_quiet_hours_boost: 야간 부스트 (4-2-D)
    - _get_last_cycle_duration: BulkCollectProgress 직전 사이클 시간 조회
    - _check_callback_backlog: Redis callback_queue LLEN 조회 (4-2-C)
    - _build_skipped_cycle_result: 사이클 스킵 표준 결과 dict

운영 상수 (튜닝 포인트):
    BACKLOG_THRESHOLD                # callback_queue 적체 임계치
    ADAPTIVE_CHUNK_RATIO_MIN/MAX    # 적응형 청크 ±50% 강제 범위
    ADAPTIVE_UP_FACTOR/DOWN_FACTOR  # 단계 조정 계수
    ADAPTIVE_LOW/HIGH_THRESHOLD     # 조정 트리거 임계 비율
    QUIET_HOURS_BOOST_FACTOR        # 야간 청크 부스트 배수
    QUIET_HOURS_START_KST           # 야간 시작 시각 (KST)
    QUIET_HOURS_END_KST             # 야간 종료 시각 (KST)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ===========================================================================
# 모듈 레벨 상수 (운영 튜닝 포인트)
# ===========================================================================
# 콜백 큐 적체 임계치: Redis LIST `callback_queue` 길이가 이 값을 초과하면
# 대량 수집 사이클을 건너뛴다 (pause_on_callback_backlog=True 일 때만).
BACKLOG_THRESHOLD: int = 50

# 적응형 청크 사이즈 ±50% 강제 범위 (chunk_size_initial 기준)
ADAPTIVE_CHUNK_RATIO_MIN: float = 0.5
ADAPTIVE_CHUNK_RATIO_MAX: float = 1.5

# 적응형 단계 조정 계수
# 직전 사이클이 한도의 50% 미만 → 1.5배, 80% 초과 → 0.7배
ADAPTIVE_UP_FACTOR: float = 1.5
ADAPTIVE_DOWN_FACTOR: float = 0.7
ADAPTIVE_LOW_THRESHOLD: float = 0.5
ADAPTIVE_HIGH_THRESHOLD: float = 0.8

# 야간 시간대(KST 02:00 ~ 06:00) 청크 부스트 배수
QUIET_HOURS_BOOST_FACTOR: float = 1.5
QUIET_HOURS_START_KST: int = 2
QUIET_HOURS_END_KST: int = 6


# ===========================================================================
# 4-2-A. 적응형 청크 사이즈
# ===========================================================================
def compute_adaptive_chunk_size(
    initial: int,
    last_duration: Optional[int],
    max_duration: int,
) -> int:
    """직전 사이클 소요 시간을 기반으로 다음 청크 크기를 계산.

    Args:
        initial: chunk_size_initial 기준선.
        last_duration: 직전 사이클 소요 시간(초). None 이면 초기값 반환.
        max_duration: cycle_max_duration_sec.

    Returns:
        조정된 청크 크기. `initial` 기준 ±50% 범위로 강제 클램프.

    Behaviour:
        - 직전 사이클이 max_duration 의 50% 미만 → 1.5배 (여유 → 청크 ↑)
        - 직전 사이클이 max_duration 의 80% 초과 → 0.7배 (빠듯 → 청크 ↓)
        - 그 외 → initial 유지
    """
    if initial <= 0:
        return 1
    if last_duration is None or max_duration <= 0:
        return initial

    ratio = last_duration / max_duration
    if ratio < ADAPTIVE_LOW_THRESHOLD:
        adjusted = int(initial * ADAPTIVE_UP_FACTOR)
    elif ratio > ADAPTIVE_HIGH_THRESHOLD:
        adjusted = int(initial * ADAPTIVE_DOWN_FACTOR)
    else:
        adjusted = initial

    # initial 기준 ±50% 범위 클램프
    floor = max(1, int(initial * ADAPTIVE_CHUNK_RATIO_MIN))
    ceiling = max(floor, int(initial * ADAPTIVE_CHUNK_RATIO_MAX))
    return max(floor, min(ceiling, adjusted))


# ===========================================================================
# 4-2-D. 야간 시간대 부스트
# ===========================================================================
def is_quiet_hours_kst(now: Optional[datetime] = None) -> bool:
    """현재 시각이 야간 시간대(KST 02:00 ~ 06:00)인지 판정.

    Args:
        now: (테스트용) 평가할 datetime. None 이면 현재 시각.

    Returns:
        True: 야간 시간대. False: 주간.
    """
    try:
        import pytz
        kst = pytz.timezone("Asia/Seoul")
        current = now.astimezone(kst) if now else datetime.now(kst)
    except Exception as exc:  # noqa: BLE001
        logger.debug("quiet_hours 시각 판정 실패 err=%s", exc)
        return False
    return QUIET_HOURS_START_KST <= current.hour < QUIET_HOURS_END_KST


def apply_quiet_hours_boost(chunk_size: int, enabled: bool) -> int:
    """야간 시간대일 때 청크 크기를 1.5배로 부스트.

    Args:
        chunk_size: 현재 청크 크기.
        enabled: quiet_hours_chunk_boost 설정.

    Returns:
        부스트 적용 후 청크 크기.
    """
    if not enabled:
        return chunk_size
    if not is_quiet_hours_kst():
        return chunk_size
    boosted = int(chunk_size * QUIET_HOURS_BOOST_FACTOR)
    logger.info(
        "[BULK_COLLECT] quiet_hours 청크 부스트 적용 | %d → %d",
        chunk_size, boosted,
    )
    return max(1, boosted)


# ===========================================================================
# BulkCollectProgress 조회 (적응형 청크용)
# ===========================================================================
async def get_last_cycle_duration(
    db, module_id: int,
) -> Optional[int]:
    """BulkCollectProgress 의 가장 최근 사이클 소요 시간을 조회.

    Args:
        db: AsyncSession.
        module_id: 모듈 ID.

    Returns:
        last_cycle_duration_sec (없으면 None).
    """
    try:
        from sqlalchemy import select
        from app.models.bulk_collect_progress import BulkCollectProgress
        stmt = (
            select(BulkCollectProgress.last_cycle_duration_sec)
            .where(BulkCollectProgress.module_id == module_id)
            .where(BulkCollectProgress.blog_domain == "_cycle_")
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[BULK_COLLECT] last_cycle_duration 조회 실패 module=%s err=%s",
            module_id, exc,
        )
        return None


# ===========================================================================
# 4-2-C. Redis callback_queue 적체 체크
# ===========================================================================
async def check_callback_backlog() -> int:
    """Redis `callback_queue` 적체 길이를 조회 (실패 시 0).

    Returns:
        callback_queue LIST 길이 (조회 실패 시 0).
    """
    try:
        from redis.asyncio import Redis  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[BULK_COLLECT] redis.asyncio import 실패 err=%s "
            "→ backlog 0 으로 간주",
            exc,
        )
        return 0

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        client = Redis.from_url(redis_url)
        try:
            length = await client.llen("callback_queue")
            return int(length or 0)
        finally:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[BULK_COLLECT] callback_queue LLEN 조회 실패 err=%s", exc,
        )
        return 0


def build_skipped_cycle_result(reason: str, detail: str) -> dict:
    """사이클을 건너뛸 때 반환할 표준 dict.

    Args:
        reason: 스킵 사유 코드 (예: "callback_backlog").
        detail: 사람이 읽을 메시지.

    Returns:
        사이클 결과 dict (success=False, skipped=True).
    """
    return {
        "success": False,
        "skipped": True,
        "reason": reason,
        "message": detail,
        "processed": 0,
        "failed": 0,
        "duration_sec": 0,
        "chunk_size": 0,
        "ingest_summary": None,
    }


__all__ = [
    "BACKLOG_THRESHOLD",
    "ADAPTIVE_CHUNK_RATIO_MIN",
    "ADAPTIVE_CHUNK_RATIO_MAX",
    "ADAPTIVE_UP_FACTOR",
    "ADAPTIVE_DOWN_FACTOR",
    "ADAPTIVE_LOW_THRESHOLD",
    "ADAPTIVE_HIGH_THRESHOLD",
    "QUIET_HOURS_BOOST_FACTOR",
    "QUIET_HOURS_START_KST",
    "QUIET_HOURS_END_KST",
    "compute_adaptive_chunk_size",
    "is_quiet_hours_kst",
    "apply_quiet_hours_boost",
    "get_last_cycle_duration",
    "check_callback_backlog",
    "build_skipped_cycle_result",
]
