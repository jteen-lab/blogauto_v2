"""제목 길이 — 지시하고, 우리가 센다.

**AI 는 글자수를 세지 못한다.** 글자가 아니라 토큰 단위로 처리하고,
한국어는 한 글자가 1~3토큰으로 쪼개진다. "25자 이내" 를 프롬프트에
적어도 지킬 수단이 없다.

그래서 둘로 나눈다.

    지시  프롬프트 **맨 앞**에 강조해 넣는다. 뒤에 두면 스타일 지시에
          묻힌다(실제로 그랬다).
    검증  결과를 **코드로 세고**, 벗어나면 한 번 다시 청한다.

계획서: docs/plans/title_tab_workplan.md §4-5
"""
from __future__ import annotations

from typing import Optional, Tuple

# 설정하지 않으면 길이를 강제하지 않는다. 0 = 미설정.
UNSET = 0

# 상한. 이보다 길면 검색 결과에서 잘린다.
MAX_ALLOWED = 80


def parse_range(settings: Optional[dict]) -> Tuple[int, int]:
    """설정에서 (최소, 최대). 잘못된 값은 미설정으로 본다."""
    raw = settings or {}

    def _int(key: str) -> int:
        try:
            value = raw.get(key)
            return max(0, min(MAX_ALLOWED, int(value))) if value else UNSET
        except (TypeError, ValueError):
            return UNSET

    low, high = _int("min_length"), _int("max_length")
    # 뒤집혀 들어오면 바로잡는다 — 그대로 두면 아무 제목도 통과 못 한다
    if low and high and low > high:
        low, high = high, low
    return low, high


def instruction(low: int, high: int) -> Optional[str]:
    """프롬프트에 넣을 길이 지시. 미설정이면 None."""
    if not low and not high:
        return None
    if low and high:
        text = f"{low}자 이상 {high}자 이내"
    elif high:
        text = f"{high}자 이내"
    else:
        text = f"{low}자 이상"
    return (f"제목은 공백을 포함해 **{text}**로 쓰세요. "
            "이 길이를 지키는 것이 다른 무엇보다 먼저입니다.")


def fits(title: str, low: int, high: int) -> bool:
    """길이가 맞는가. 미설정 구간은 검사하지 않는다."""
    length = len(title or "")
    if low and length < low:
        return False
    if high and length > high:
        return False
    return True


def retry_hint(title: str, low: int, high: int) -> str:
    """다시 청할 때 붙일 문구. **실제 길이를 알려 준다.**

    AI 는 자기가 쓴 제목이 몇 자인지 모른다. 숫자를 주면 고칠 수 있다.
    """
    length = len(title or "")
    if high and length > high:
        gap = length - high
        return (f"방금 쓴 제목은 {length}자로 {gap}자 깁니다. "
                f"{low or 1}~{high}자로 줄여 다시 쓰세요.")
    gap = (low or 0) - length
    return (f"방금 쓴 제목은 {length}자로 {gap}자 짧습니다. "
            f"{low}~{high or low + 10}자로 늘려 다시 쓰세요.")
