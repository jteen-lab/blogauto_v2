"""
불규칙 간격(Jitter) 계산 모듈

Features:
- 기본 간격에 랜덤 변동률 적용
- 활성 시간대 고려한 다음 실행 시간 계산
- 제외 요일 스킵 처리
"""

import random
from datetime import datetime, timedelta, time
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.publish_profile import PublishProfile


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