"""0-1 모자란 블로그부터 차례로 채우기 — 제목 수집 회차의 시드를 정한다.

- 제목이 30일 치 아래인 블로그 중 며칠 치가 가장 적은 곳부터, 한 회차에 한 블로그.
- 그 블로그가 45일 치가 되면 다음 블로그.
- 검색어부터 30일 치 아래면 검색어 창고 채우기를 먼저.
- 시드 70% = 그 블로그 칸, 30% = 무작위. 부족한 블로그가 없으면 100% 무작위.
- 3회차 연속 며칠 치가 안 늘면 멈추고 logs/title_fill_stall.jsonl 에 한 줄
  (호스트 작업이 마케팅 상태.md 에 옮긴다). 14일 뒤 다시 대상이 된다.

순서도: docs/flowcharts/title_screen_d.md (0-1 채우기 차례)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import VERDICT_ADOPT, KeywordCandidate
from . import inventory
from .inventory import BlogStock

logger = get_logger("title_screen", "app.log")

STATE_KEY = "title_fill_state"
SHORT_SHARE = 0.7
STALL_ROUNDS = 3
STALL_RETRY_DAYS = 14
STALL_LOG = Path("logs/title_fill_stall.jsonl")


@dataclass
class FillPlan:
    """이번 회차 계획."""

    blog: Optional[BlogStock] = None
    note: str = ""
    refilled: Dict[str, int] = field(default_factory=dict)


async def _load(db: AsyncSession) -> Dict[str, Any]:
    """채우기 상태. 워커마다 설정 캐시가 따로라 DB 를 바로 읽는다."""
    from ...models.system_settings import SystemSettings

    raw = (await db.execute(select(SystemSettings.value).where(
        SystemSettings.key == STATE_KEY))).scalar_one_or_none()
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}


async def _save(db: AsyncSession, state: Dict[str, Any]) -> None:
    """상태 저장."""
    from ..system_settings_service import SystemSettingsService

    await SystemSettingsService.set(STATE_KEY, json.dumps(state, ensure_ascii=False), db)
    await db.commit()   # set() 은 커밋하지 않는다


def _stalled(state: Dict[str, Any]) -> Dict[str, str]:
    """멈춘 블로그 {id: 멈춘 날}. 14일 지난 것은 뺀다."""
    keep = {}
    for bid, day in (state.get("stalled") or {}).items():
        try:
            if date.fromisoformat(day) + timedelta(days=STALL_RETRY_DAYS) > date.today():
                keep[bid] = day
        except ValueError:
            continue
    return keep


def _stall_note(b: BlogStock) -> None:
    """마케팅에 알릴 한 줄(호스트 작업이 상태.md 로 옮긴다)."""
    line = {"at": datetime.now().isoformat(timespec="minutes"), "blog_id": b.blog_id,
            "blog": b.name, "title_days": b.title_days, "keyword_days": b.keyword_days,
            "msg": f"{b.name} 제목 채우기 3회차 연속 안 늘어 멈춤 — 씨앗 말 새로 필요"}
    try:
        STALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with STALL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("[TITLE_FILL] 멈춤 기록 실패 | %s", e)
    logger.warning("[TITLE_FILL] %s", line["msg"])


def _advance(state: Dict[str, Any], stocks: List[BlogStock]) -> Optional[BlogStock]:
    """지금 채울 블로그를 정하고 정체 셈을 갱신한다."""
    stalled = _stalled(state)
    by_id = {str(b.blog_id): b for b in stocks}
    cur = by_id.get(str(state.get("blog_id")))
    if cur and (cur.title_days >= inventory.FULL_DAYS or str(cur.blog_id) in stalled):
        cur = None
    if cur:
        gained = cur.title_days > float(state.get("last_days") or 0)
        state["no_gain"] = 0 if gained else int(state.get("no_gain") or 0) + 1
        if state["no_gain"] >= STALL_ROUNDS:
            stalled[str(cur.blog_id)] = date.today().isoformat()
            _stall_note(cur)
            cur = None
    if cur is None:
        short = [b for b in stocks if b.title_days < inventory.SHORT_DAYS
                 and str(b.blog_id) not in stalled]
        cur = short[0] if short else None
        state["no_gain"] = 0
    state.update(blog_id=cur.blog_id if cur else None,
                 last_days=cur.title_days if cur else None, stalled=stalled)
    return cur


async def plan(db: AsyncSession, user_id: int) -> FillPlan:
    """이번 회차에 채울 블로그(없으면 무작위만). 검색어부터 모자라면 창고를 먼저 채운다."""
    stocks = await inventory.stock(db)
    state = await _load(db)
    cur = _advance(state, stocks)
    if cur is None:
        await _save(db, state)
        return FillPlan(note="부족한 블로그 없음 — 100% 무작위")
    out = FillPlan(blog=cur, note=f"{cur.name} {cur.title_days}일 치 채우는 중")
    if cur.keyword_days < inventory.SHORT_DAYS:
        from . import extract, warehouse

        cat = await extract.catalog(db, user_id)
        out.refilled = await warehouse.refill(
            db, user_id, cur.blog_id, cur.subtopics, {s: v[0] for s, v in cat.items()})
    # 회차가 여기까지 왔을 때만 셈을 남긴다(중간 실패를 '안 늘었다'로 세지 않게)
    await _save(db, state)
    return out


async def seeds(db: AsyncSession, user_id: int, fill: FillPlan, limit: int) -> List[Any]:
    """시드 limit 개 — 70% 부족 블로그 칸, 나머지 무작위(칸 이름표 있는 채택 검색어)."""
    base = select(KeywordCandidate).where(
        KeywordCandidate.user_id == user_id, KeywordCandidate.verdict == VERDICT_ADOPT,
        KeywordCandidate.is_active.is_(True))
    picked: List[Any] = []
    if fill.blog:
        n = math.ceil(limit * SHORT_SHARE)
        picked = list((await db.execute(
            base.where(KeywordCandidate.subtopic_id.in_(fill.blog.subtopics))
            .order_by(KeywordCandidate.titled.asc(),
                      KeywordCandidate.search_volume.desc().nullslast()).limit(n)
        )).scalars().all())
    seen = {r.id for r in picked}
    rest = (await db.execute(
        base.where(KeywordCandidate.subtopic_id.is_not(None))
        .order_by(func.random()).limit(limit * 2))).scalars().all()
    for row in rest:
        if len(picked) >= limit:
            break
        if row.id not in seen:
            picked.append(row)
            seen.add(row.id)
    return picked[:limit]
