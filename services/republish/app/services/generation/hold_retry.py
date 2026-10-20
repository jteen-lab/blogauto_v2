"""O3. 보류가 나면 그날은 다음 대기 제목으로 바로 넘어간다.

슈마즈(하루 1편)는 공식 출처·말투·사실 관문 보류가 나면 그날 글이 빈다.
관문은 그대로 두고(보류 횟수 기록도 그대로) 다음 제목으로 다시 시도한다.
한 번 실행에 최대 max_attempts(기본 3)개 제목까지.

모듈 설정 ``fact_gate.next_title_on_hold.enabled`` 가 true 일 때만 —
다른 블로그는 지금과 같다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (O3)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence, Tuple

from ...core.logger import get_logger

logger = get_logger("hold_retry", "app.log")

DEFAULT_MAX = 3


def switch(settings: Optional[dict]) -> Tuple[bool, int]:
    """(켜짐, 최대 시도 수)."""
    cfg = ((settings or {}).get("fact_gate") or {})
    sub = cfg.get("next_title_on_hold") if isinstance(cfg, dict) else None
    if not isinstance(sub, dict) or sub.get("enabled") is not True:
        return False, 0
    return True, max(1, int(sub.get("max_attempts") or DEFAULT_MAX))


def _held_today(title: Any) -> bool:
    """오늘 이미 보류된 제목인가(오늘 다시 뽑지 않는다)."""
    at = getattr(title, "last_held_at", None)
    return bool(at) and at.date() == datetime.now(at.tzinfo).date()


async def next_title_id(trigger: Any, blog_id: int, settings: dict,
                        tried: Sequence[int]) -> int:
    """아직 안 해 본, 오늘 보류되지 않은 다음 제목. 없으면 0."""
    titles = await trigger.find_available_titles(
        blog_id, limit=20, module_settings=settings)
    for t in titles:
        if t.id not in tried and not _held_today(t):
            return t.id
    return 0


async def retry(executor: Any, module: Any, blog: Any, stage_params: Any,
                scope_gate: bool, settings: dict, error: Optional[str],
                tried: Tuple[int, ...]) -> Optional[dict]:
    """보류였으면 다음 제목으로 다시 실행한 결과. 안 하면 None."""
    on, limit = switch(settings)
    if not on or "보류" not in (error or ""):
        return None
    while len(tried) < limit:
        nxt = await next_title_id(executor.inventory_trigger, blog.id,
                                  settings, tried)
        if not nxt:
            logger.info("[HOLD_RETRY] 다음 제목 없음 | blog=%s | 시도 %s",
                        blog.id, list(tried))
            return None
        logger.info("[HOLD_RETRY] 보류 → 다음 제목 | blog=%s | %d/%d번째 | "
                    "title_id=%s | 앞 사유: %s", blog.id, len(tried) + 1,
                    limit, nxt, (error or "")[:80])
        res = await executor.execute_for_blog(
            module, blog, stage_params=stage_params, force_title_id=nxt,
            scope_gate=scope_gate, _tried=tried)
        if not res.get("skipped"):
            res["held_titles"] = list(tried)
            return res
        tried = (*tried, nxt)
    return None
