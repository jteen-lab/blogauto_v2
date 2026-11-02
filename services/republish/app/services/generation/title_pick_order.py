"""재고 제목 고르는 순서·거름 — 모듈 스위치 ``title_pick`` (2026-11-02, 마케팅 A1).

승인 4곳은 하루 3편으로 늘리면서 늘어난 칸을 **검색량에서 출발한 제목**
(keyword_module)으로 채운다. 예전 순서(오래된 순)는 옛 수집 제목이 먼저 나가
6~8월(하루 3~5편, 노출 거의 0)을 되풀이한다.

또 공식 출처가 없어 몇 번이고 보류된 제목(꿀팁대백과 1937 산초 효능 13회)을
관문 다음 제목이 매번 다시 집어 회차를 날렸다 — 보류 횟수가 넘은 제목은 뺀다.

모듈 settings 예::

    "title_pick": {"prefer_source": ["keyword_module"], "skip_held_count": 3}

스위치가 없으면 예전과 같다(나머지 10곳).
순서도: docs/flowcharts/approved4_a1_volume.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from sqlalchemy import case

from ...models.title import MainTitle


@dataclass(frozen=True)
class PickOpts:
    """제목 고르기 옵션."""

    prefer_sources: Tuple[str, ...] = ()
    skip_held_count: Optional[int] = None

    @property
    def active(self) -> bool:
        """하나라도 켜졌나."""
        return bool(self.prefer_sources or self.skip_held_count)


NONE = PickOpts()


def pick_opts(settings: Optional[dict]) -> PickOpts:
    """모듈 settings → 옵션. 모양이 틀리면 꺼진 것으로 본다."""
    cfg = (settings or {}).get("title_pick")
    if not isinstance(cfg, dict):
        return NONE
    src = cfg.get("prefer_source") or ()
    if isinstance(src, str):
        src = (src,)
    held = cfg.get("skip_held_count")
    try:
        held = int(held) if held else None
    except (TypeError, ValueError):
        held = None
    return PickOpts(tuple(str(s) for s in src if s), held if held and held > 0 else None)


def conditions(opts: PickOpts) -> List[Any]:
    """후보 거름 조건(WHERE 에 더한다)."""
    if not opts.skip_held_count:
        return []
    return [MainTitle.hold_count < opts.skip_held_count]


def order(opts: PickOpts) -> List[Any]:
    """정렬. 고른 출처 먼저, 그다음 새 제목 먼저(검색량 제목은 매일 10시에 새로 생긴다).

    스위치가 없으면 예전 그대로 오래된 순.
    """
    if not opts.prefer_sources:
        return [MainTitle.created_at.asc()]
    first = case((MainTitle.source.in_(list(opts.prefer_sources)), 0), else_=1)
    return [first, MainTitle.created_at.desc()]
