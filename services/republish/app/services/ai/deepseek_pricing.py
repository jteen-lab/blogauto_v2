"""딥시크 요금제 — 엔드포인트·기본 모델·피크 시간 정의 (2026-08-30).

피크 시간 정의를 여기 한 곳에만 둔다. 화면 표시와 요약 계산이 각자 시간을
적어두면 요금제가 바뀔 때 한쪽만 고쳐져 서로 다른 답을 낸다.

요금(100만 토큰당 USD, 2026-08-16 개편 기준)
    v4-flash  비피크 입력 $0.22 / 출력 $0.66   — 피크는 정확히 2배
    v4-pro    비피크 입력 $0.66 / 출력 $1.98   — 피크는 정확히 2배

피크는 UTC 01:00~04:00, 06:00~10:00 (월~금). 서버와 schedule_matrix 는
Asia/Seoul 기준이라 KST 로 환산해 쓴다. UTC 01~10시는 KST 로 같은 날
10~19시여서 요일이 밀리지 않는다.
"""
from __future__ import annotations

from typing import Dict, List

BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

# 사고 모드를 끈다.
# 딥시크 v4 는 기본으로 사고(reasoning)를 하는데, 그 토큰이 max_tokens 예산을
# 같이 쓴다. 제목 재조합처럼 max_tokens=200 인 짧은 작업에서는 사고에 다 쓰고
# 본문이 빈 채로 돌아와 "호출 실패" 가 됐다(실측: 200 → content 0자/사고 484자).
# 앱의 max_tokens 는 '본문 길이' 를 의도한 값이므로 사고가 먹으면 안 된다.
# 사고 토큰도 출력으로 과금되므로 요금 면에서도 끄는 편이 낫다.
EXTRA_PARAMS = {"reasoning_effort": "none"}

MODELS: List[Dict[str, str]] = [
    {
        "id": "deepseek-v4-flash",
        "label": "DeepSeek V4 Flash (저가·범용)",
        "note": "비피크 출력 $0.66/1M",
    },
    {
        "id": "deepseek-v4-pro",
        "label": "DeepSeek V4 Pro (고성능)",
        "note": "비피크 출력 $1.98/1M",
    },
    {
        "id": "deepseek-v4-flash-vision-exp",
        "label": "DeepSeek V4 Flash Vision (실험·이미지 입력)",
        "note": "Flash 와 동일 요금",
    },
]

# UTC 기준 피크 구간 [시작, 끝) — 끝 시각은 포함하지 않는다
PEAK_UTC_RANGES = ((1, 4), (6, 10))
# 피크가 적용되는 요일(월=0 … 일=6)
PEAK_WEEKDAYS = (0, 1, 2, 3, 4)
KST_OFFSET = 9
PEAK_MULTIPLIER = 2.0


def peak_hours_kst() -> List[int]:
    """피크에 해당하는 KST 시각 목록."""
    hours = []
    for start, end in PEAK_UTC_RANGES:
        for h in range(start, end):
            hours.append((h + KST_OFFSET) % 24)
    return sorted(hours)


def is_peak(weekday: int, hour_kst: int) -> bool:
    """해당 요일·KST 시각이 피크인지.

    Args:
        weekday: 월=0 … 일=6 (schedule_matrix 의 행 순서와 같다)
        hour_kst: 0~23
    """
    if weekday not in PEAK_WEEKDAYS:
        return False
    return hour_kst in peak_hours_kst()


def peak_summary(schedule_matrix) -> Dict[str, int]:
    """스케줄에서 활성 시간 중 몇 시간이 피크인지 센다.

    Args:
        schedule_matrix: bool[7][24] (월~일 × 0~23시, KST)

    Returns:
        {"active": 활성 시간 수, "peak": 그중 피크 시간 수}
    """
    active = peak = 0
    for day, row in enumerate(schedule_matrix or []):
        for hour, on in enumerate(row or []):
            if not on:
                continue
            active += 1
            if is_peak(day, hour):
                peak += 1
    return {"active": active, "peak": peak}
