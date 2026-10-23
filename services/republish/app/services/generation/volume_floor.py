"""N2 검색량 바닥선 — 아무도 안 찾는 제목은 이번 회차에 건너뛰고 다음 제목을 쓴다.

마케팅 실측(2026-10-23, 형 승인): 118편 중 핵심어 검색량 10 미만 글이 많았다.
맨 앞 검색어 후보(lead_keyword_pick)가 모두 한 달 바닥선(기본 50) 아래면 그 제목은
이번 회차에 쓰지 않고 같은 회차 안에서 다음 제목으로 넘어간다(발행 수 유지).

- 제목은 보관하지 않는다. 가장 큰 검색량과 잰 날만 main_titles 에 남긴다 —
  나중에 바닥선을 바꾸면 남긴 값으로 다시 판정한다. 30일 안이면 다시 재지 않는다.
- 조회 실패면 건너뛰지 않는다(조회 실패로 발행이 멈추면 안 된다).
- CPA 오퍼 제목은 보지 않는다. 바닥선은 모듈 `title_lead_floor`(인포노트 10 — 구글 유입).
- 스위치는 맨 앞 검색어와 같은 `title_lead_keyword`.

순서도: docs/flowcharts/title_lead_keyword.md (1. 생성 회차)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from ...core.logger import get_logger
from . import lead_keyword
from .title_lifecycle import title_keywords

logger = get_logger("volume_floor", "app.log")

REMEMBER_DAYS = 30
MAX_TRIES = 3


def remembered(title: Any, low: int) -> Optional[bool]:
    """30일 안에 잰 값으로 판정: True=통과, False=낮음, None=다시 재야 함."""
    at = getattr(title, "search_volume_at", None)
    vol = getattr(title, "search_volume", None)
    if at is None or vol is None:
        return None
    if datetime.now(timezone.utc) - at > timedelta(days=REMEMBER_DAYS):
        return None
    return vol >= low


async def check(db: Any, user_id: int, blog: Any, title: Any,
                settings: Optional[dict]) -> Optional[str]:
    """바닥선 아래면 건너뛸 사유, 아니면 None. 판정 오류는 통과."""
    if not lead_keyword.enabled(settings) or getattr(title, "cpa_offer_id", None):
        return None
    low = lead_keyword.floor(settings)
    text = getattr(title, "title", "") or ""
    try:
        known = remembered(title, low)
        if known is None:
            lead = await lead_keyword.measure(db, user_id, text, title_keywords(title), low)
            if lead.status == "fail":
                return None
            title.search_volume = lead.best
            title.search_volume_at = datetime.now(timezone.utc)
            await db.commit()
            known = lead.status != "low"
    except Exception as e:  # noqa: BLE001
        logger.warning("[VOLUME_FLOOR] 판정 실패(통과) | blog=%s | %s", blog.id, e)
        return None
    if known:
        return None
    msg = (f"검색량 낮음 — 맨 앞 검색어 후보 최대 한 달 "
           f"{title.search_volume}회(바닥선 {low})")
    logger.info("[VOLUME_FLOOR] 건너뜀 | blog=%s | title_id=%s | '%s' | %s",
                blog.name, title.id, text[:40], msg)
    return msg


async def next_title(executor: Any, module: Any, blog: Any, stage_params: Any,
                     scope_gate: bool, settings: dict,
                     tried: Tuple[int, ...]) -> Optional[dict]:
    """같은 회차에서 다음 제목으로 다시 실행한 결과. 더 볼 제목이 없으면 None."""
    if len(tried) >= MAX_TRIES:
        logger.info("[VOLUME_FLOOR] 이번 회차 %d개 모두 낮음 — 다음 회차로 | blog=%s",
                    len(tried), blog.name)
        return None
    low = lead_keyword.floor(settings)
    titles = await executor.inventory_trigger.find_available_titles(
        blog.id, limit=40, module_settings=settings)
    for t in titles:
        if t.id in tried or remembered(t, low) is False:
            continue
        logger.info("[VOLUME_FLOOR] 다음 제목 | blog=%s | %d번째 | title_id=%s",
                    blog.name, len(tried) + 1, t.id)
        return await executor.execute_for_blog(
            module, blog, stage_params=stage_params, force_title_id=t.id,
            scope_gate=scope_gate, _tried=tried)
    logger.info("[VOLUME_FLOOR] 남은 제목이 모두 낮음 | blog=%s", blog.name)
    return None
