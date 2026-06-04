"""
불규칙 간격(Jitter) 계산 모듈

Features:
- 기본 간격에 랜덤 변동률 적용
- 활성 시간대 고려한 다음 실행 시간 계산
- 제외 요일 스킵 처리
- bulk_collect 등 별도 모듈 settings 에서 GP 와 동일한 jitter 객체
  구조를 읽어오는 정규화 헬퍼 제공
"""

import logging
import random
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.publish_profile import PublishProfile

logger = logging.getLogger(__name__)


def calculate_jittered_interval(
    base_interval_minutes: int,
    jitter_enabled: bool,
    jitter_min_percent: int,
    jitter_max_percent: int
) -> int:
    """
    불규칙 간격 계산

    Args:
        base_interval_minutes: 기본 간격(분)
        jitter_enabled: 불규칙 간격 활성화 여부
        jitter_min_percent: 최소 변동률(%)
        jitter_max_percent: 최대 변동률(%)

    Returns:
        계산된 간격(분)

    Examples:
        >>> calculate_jittered_interval(60, True, -20, 30)
        73  # 48분 ~ 78분 사이의 랜덤 값
    """
    if not jitter_enabled:
        return base_interval_minutes

    # 변동률 계산
    min_multiplier = 1 + (jitter_min_percent / 100)  # 0.8 (-20%)
    max_multiplier = 1 + (jitter_max_percent / 100)  # 1.3 (+30%)

    # 랜덤 배율 적용
    random_multiplier = random.uniform(min_multiplier, max_multiplier)
    jittered = int(base_interval_minutes * random_multiplier)

    # 최소 5분 보장
    return max(5, jittered)


def calculate_next_run_time(
    last_run: datetime,
    base_interval_minutes: int,
    profile: "PublishProfile"
) -> datetime:
    """
    다음 실행 시간 계산 (활성 시간대 및 제외 요일 고려)

    Args:
        last_run: 마지막 실행 시간
        base_interval_minutes: 기본 간격(분)
        profile: 재발행 프로파일

    Returns:
        다음 실행 시간
    """
    # 1. Jitter 적용
    jittered_interval = calculate_jittered_interval(
        base_interval_minutes,
        profile.jitter_enabled,
        profile.jitter_min_percent,
        profile.jitter_max_percent
    )

    # 2. 기본 다음 시간 계산
    next_time = last_run + timedelta(minutes=jittered_interval)

    # 3. 활성 시간대 조정
    next_time = _adjust_to_active_hours(next_time, profile)

    # 4. 제외 요일 스킵
    next_time = _skip_blackout_days(next_time, profile)

    return next_time


def _adjust_to_active_hours(next_time: datetime, profile: "PublishProfile") -> datetime:
    """활성 시간대에 맞춰 시간 조정"""
    # 활성 시간 파싱
    active_start = _parse_time_str(profile.active_hours_start)
    active_end = _parse_time_str(profile.active_hours_end)

    current_time = next_time.time()

    # 활성 시간대 내에 있는지 확인
    if active_start <= current_time <= active_end:
        return next_time

    # 활성 시간 전이면 당일 활성 시간 시작으로
    if current_time < active_start:
        return next_time.replace(
            hour=active_start.hour,
            minute=active_start.minute,
            second=0,
            microsecond=0
        )

    # 활성 시간 후면 다음 날 활성 시간 시작으로
    next_day = next_time + timedelta(days=1)
    return next_day.replace(
        hour=active_start.hour,
        minute=active_start.minute,
        second=0,
        microsecond=0
    )


def _skip_blackout_days(next_time: datetime, profile: "PublishProfile") -> datetime:
    """제외 요일 스킵 처리"""
    blackout_days = profile.blackout_days or []

    if not blackout_days:
        return next_time

    # 최대 7일 확인 (무한 루프 방지)
    for _ in range(7):
        weekday = next_time.weekday()  # 0=월요일, 6=일요일

        if weekday not in blackout_days:
            return next_time

        # 다음 날로 이동
        next_time = next_time + timedelta(days=1)
        # 활성 시간 시작으로 조정
        next_time = _adjust_to_active_hours(next_time, profile)

    # 모든 요일이 제외된 경우 원본 반환 (설정 오류)
    return next_time


def _parse_time_str(time_str: str) -> time:
    """시간 문자열 파싱 (HH:MM 형식)"""
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except (ValueError, AttributeError):
        # 기본값: 오전 9시
        return time(9, 0)


def get_jitter_percentage(original_interval: int, jittered_interval: int) -> float:
    """Jitter 적용률 계산 (로그용)"""
    if original_interval == 0:
        return 0.0

    percentage = ((jittered_interval - original_interval) / original_interval) * 100
    return round(percentage, 1)


# 기본 지터 범위 (GP/bulk_collect 모두 동일)
DEFAULT_JITTER_MIN_PERCENT = -20
DEFAULT_JITTER_MAX_PERCENT = 30


def normalize_jitter_config(raw: Any) -> Dict[str, Any]:
    """다양한 지터 설정 구조를 GP 표준 (enabled/min_percent/max_percent) 으로 정규화.

    지원 입력:
        1. 신 객체 형식 (권장)::

            {"enabled": True, "min_percent": -20, "max_percent": 30}

        2. 구 평탄 형식 (bulk_collect 레거시)::

            {
                "jitter_enabled": True,
                "jitter_min_percent": 80,    # 양수만 사용, 100 기준
                "jitter_max_percent": 120,
            }

           이 경우 ``min_percent = jitter_min_percent - 100`` 식으로 변환.
           (80 → -20, 120 → +20). 변환 결과가 비현실적(±200% 이상)이면 기본값.

        3. None 또는 빈 dict → 기본값 반환 (disabled).

    Args:
        raw: 지터 설정 값. 객체/평탄/None 모두 허용.

    Returns:
        정규화된 dict ``{enabled, min_percent, max_percent}``.

    Examples:
        >>> normalize_jitter_config(
        ...     {"enabled": True, "min_percent": -20, "max_percent": 30}
        ... )
        {'enabled': True, 'min_percent': -20, 'max_percent': 30}

        >>> normalize_jitter_config({
        ...     "jitter_enabled": True,
        ...     "jitter_min_percent": 80,
        ...     "jitter_max_percent": 120,
        ... })
        {'enabled': True, 'min_percent': -20, 'max_percent': 20}

        >>> normalize_jitter_config(None)
        {'enabled': False, 'min_percent': -20, 'max_percent': 30}
    """
    default = {
        "enabled": False,
        "min_percent": DEFAULT_JITTER_MIN_PERCENT,
        "max_percent": DEFAULT_JITTER_MAX_PERCENT,
    }
    if not raw or not isinstance(raw, dict):
        return default

    # Case 1: 신 객체 형식 - "enabled" 키 존재
    if "enabled" in raw or "min_percent" in raw or "max_percent" in raw:
        try:
            return {
                "enabled": bool(raw.get("enabled", False)),
                "min_percent": int(
                    raw.get("min_percent", DEFAULT_JITTER_MIN_PERCENT)
                ),
                "max_percent": int(
                    raw.get("max_percent", DEFAULT_JITTER_MAX_PERCENT)
                ),
            }
        except (TypeError, ValueError) as exc:
            logger.warning(
                "[JITTER] 신 객체 형식 파싱 실패, 기본값 사용 | error=%s | raw=%s",
                exc, raw,
            )
            return default

    # Case 2: 구 평탄 형식 - "jitter_enabled" 키 존재
    if "jitter_enabled" in raw or "jitter_min_percent" in raw:
        try:
            enabled = bool(raw.get("jitter_enabled", False))
            legacy_min = int(raw.get("jitter_min_percent", 100))
            legacy_max = int(raw.get("jitter_max_percent", 100))
            # 100 기준 양수 → ±% 변환 (80 → -20, 120 → +20)
            min_pct = legacy_min - 100
            max_pct = legacy_max - 100
            # 비현실적 값 가드
            if abs(min_pct) > 200 or abs(max_pct) > 200:
                logger.warning(
                    "[JITTER] 레거시 값 범위 이상, 기본값 사용 | "
                    "legacy_min=%s legacy_max=%s", legacy_min, legacy_max,
                )
                return {**default, "enabled": enabled}
            return {
                "enabled": enabled,
                "min_percent": min_pct,
                "max_percent": max_pct,
            }
        except (TypeError, ValueError) as exc:
            logger.warning(
                "[JITTER] 레거시 평탄 형식 파싱 실패, 기본값 사용 | error=%s | raw=%s",
                exc, raw,
            )
            return default

    return default


def resolve_module_jitter(settings: Dict[str, Any]) -> Dict[str, Any]:
    """모듈 ``settings`` JSONB 에서 지터 설정을 추출/정규화.

    bulk_collect 모듈의 settings 구조::

        # 신 형식 (권장 - GP 와 통일)
        {
            "schedule": {
                "jitter": {
                    "enabled": True,
                    "min_percent": -20,
                    "max_percent": 30,
                },
            },
        }

        # 구 형식 (레거시 - 호환 지원)
        {
            "schedule": {
                "jitter_enabled": True,
                "jitter_min_percent": 80,
                "jitter_max_percent": 120,
            },
        }

    Args:
        settings: ``Module.settings`` dict.

    Returns:
        ``{enabled, min_percent, max_percent}`` 표준 dict.
    """
    if not settings or not isinstance(settings, dict):
        return normalize_jitter_config(None)
    schedule = settings.get("schedule") or {}
    if not isinstance(schedule, dict):
        return normalize_jitter_config(None)

    # 신 객체 형식 우선
    obj = schedule.get("jitter")
    if obj:
        return normalize_jitter_config(obj)
    # 레거시 평탄 형식 폴백
    return normalize_jitter_config(schedule)