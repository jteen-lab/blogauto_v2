"""관문에 걸리면 같은 회차 안에서 다음 제목으로 다시 한다(2026-10-25, 마케팅 지시).

10/23 N3(블로그끼리 90일)를 켠 뒤 제목 관문·같은 블로그 중복의 '이번만 건너뜀'이
회차를 통째로 날려 14곳 생성이 하루 9편 → 2편으로 줄었다. 관문 기준·보관 규칙은
그대로 두고, 걸린 뒤 같은 회차에서 다음 후보로 넘어간다(N2 검색량 바닥선과 같은 길).

- 이번 회차에 본 제목은 바닥선·관문이 한 묶음으로 센다 — 최대 ``MAX_TRIES`` 개.
- 30일 안에 검색량 '낮음'으로 잰 제목은 다음 후보에서 뺀다(바닥선 스위치가 켜졌을 때만).

순서도: docs/flowcharts/title_topic_gate.md (관문에 걸려도 같은 회차에서 다음 제목)
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from ...core.logger import get_logger
from . import lead_keyword
from .volume_floor import remembered

logger = get_logger("gate_retry", "app.log")

MAX_TRIES = 3


def _skip(reason: str) -> dict:
    """회차를 건너뛸 때의 결과(예전과 같은 모양)."""
    return {"success": True, "skipped": True, "message": f"{reason} - 생성 건너뜀"}


async def pick_next(trigger: Any, blog_id: int, settings: dict,
                    tried: Tuple[int, ...]) -> Optional[int]:
    """이번 회차에 아직 안 본 다음 제목 id. 없으면 None."""
    floor = lead_keyword.floor(settings) if lead_keyword.enabled(settings) else None
    titles = await trigger.find_available_titles(
        blog_id, limit=40, module_settings=settings)
    for t in titles:
        if t.id in tried or (floor is not None and remembered(t, floor) is False):
            continue
        return t.id
    return None


async def next_title(executor: Any, module: Any, blog: Any, stage_params: Any,
                     scope_gate: bool, settings: dict, tried: Tuple[int, ...],
                     reason: str) -> dict:
    """같은 회차에서 다음 제목으로 다시 실행한 결과. 더 볼 제목이 없으면 건너뜀."""
    if len(tried) >= MAX_TRIES:
        logger.info("[GATE_RETRY] 이번 회차 %d개 모두 걸림 — 다음 회차로 | blog=%s | 끝 사유: %s",
                    len(tried), blog.name, reason[:80])
        return _skip(reason)
    try:
        nxt = await pick_next(executor.inventory_trigger, blog.id, settings, tried)
    except Exception as e:  # noqa: BLE001
        logger.warning("[GATE_RETRY] 다음 제목 조회 실패 | blog=%s | %s", blog.name, e)
        return _skip(reason)
    if nxt is None:
        logger.info("[GATE_RETRY] 남은 제목 없음 | blog=%s | 본 제목 %s", blog.name, list(tried))
        return _skip(reason)
    logger.info("[GATE_RETRY] 다음 제목 | blog=%s | %d번째 | title_id=%s | 앞 사유: %s",
                blog.name, len(tried) + 1, nxt, reason[:80])
    return await executor.execute_for_blog(
        module, blog, stage_params=stage_params, force_title_id=nxt,
        scope_gate=scope_gate, _tried=tried)
