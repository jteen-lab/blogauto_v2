"""최신성 판정 — 낡은 제목을 규칙으로 골라낸다.

확장 재조합 ①(계획서 §4-6). AI 없이 후보를 고를 수 있다는 것이 요점이다.
문장 다듬기만 AI 가 하고, **무엇을 다듬을지는 규칙이 정한다.**

    "2024년 전기기사 실기 접수 일정"  ← 2026년에 쓰면 죽은 제목
            ↓
    "2026년 전기기사 실기 접수 일정"

연도가 박혔거나 '올해·최신·최근' 같은 시점 표현이 있는데 만들어진 지
오래된 제목이 대상이다.

계획서: docs/plans/title_tab_workplan.md §4-6 ①
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 연도(4자리). 1900~2099 만 본다 — 전화번호·가격이 걸리지 않게.
YEAR_RE = re.compile(r"(19|20)\d{2}")

# 시점 표현. 연도가 없어도 시간이 지나면 낡는다.
TIME_WORDS = ("올해", "최신", "최근", "이번 달", "이번달", "현재", "요즘",
              "신규", "개정")

# 이만큼 지나면 다시 본다. 분기마다 한 번꼴.
STALE_DAYS = 90


def years_in(title: str) -> List[int]:
    """제목에 박힌 연도들."""
    return [int(m.group()) for m in YEAR_RE.finditer(title or "")]


def has_time_marker(title: str) -> bool:
    """시점 표현이 있는가."""
    text = title or ""
    return bool(years_in(text)) or any(w in text for w in TIME_WORDS)


def is_stale(title: str, created_at: Optional[datetime],
             now: Optional[datetime] = None,
             stale_days: int = STALE_DAYS) -> bool:
    """낡았는가.

    판단 두 가지:
      1. 지난 연도가 박혀 있다 → 무조건 낡았다
      2. 시점 표현이 있는데 만들어진 지 오래됐다
    """
    now = now or datetime.now(timezone.utc)
    text = title or ""

    for year in years_in(text):
        if year < now.year:
            return True

    if not has_time_marker(text):
        return False
    if created_at is None:
        return False
    # timezone 이 없는 값이 섞여 들어온다(옛 행)
    made = created_at if created_at.tzinfo else \
        created_at.replace(tzinfo=timezone.utc)
    return (now - made).days >= stale_days


def refresh_years(title: str, now: Optional[datetime] = None) -> str:
    """지난 연도를 올해로 바꾼다. AI 없이 되는 부분은 여기서 끝낸다.

    올해·미래 연도는 건드리지 않는다 — "2027년 시행" 같은 제목을 과거로
    당기면 안 된다.
    """
    now = now or datetime.now(timezone.utc)

    def swap(match: re.Match) -> str:
        year = int(match.group())
        return str(now.year) if year < now.year else match.group()

    return YEAR_RE.sub(swap, title or "")


def plan(title: str, created_at: Optional[datetime],
         now: Optional[datetime] = None) -> Dict[str, Any]:
    """이 제목을 어떻게 손볼지.

    Returns:
        {"stale": bool, "rule_only": str|None, "needs_ai": bool}
        `rule_only` 가 있으면 AI 를 부르지 않아도 된다.
    """
    now = now or datetime.now(timezone.utc)
    stale = is_stale(title, created_at, now)
    if not stale:
        return {"stale": False, "rule_only": None, "needs_ai": False}

    swapped = refresh_years(title, now)
    if swapped != title:
        # 연도만 바꾸면 되는 경우가 가장 흔하다. AI 비용 0.
        return {"stale": True, "rule_only": swapped, "needs_ai": False}
    return {"stale": True, "rule_only": None, "needs_ai": True}
