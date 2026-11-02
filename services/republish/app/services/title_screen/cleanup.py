"""이미 쌓인 창고 한 번 정리(2026-11-02 형 승인) — 단계별로 이어서 돌릴 수 있다.

    backup   temp_titles·main_titles·keyword_candidates 를 bak_1102_* 표로 통째 복사
    temp     임시 제목 2~5단계(통과 → 이름표, 떨어짐 → 삭제+지문, 실패 → 그대로)
    main     정식 available 같은 검사(떨어짐 → screened_out 표시만)
    safety   쓸 제목이 7일 치 아래로 떨어진 블로그의 칸은 거름 표시를 미룸(screen_deferred)
    keywords 칸 없는 채택 검색어에 칸 붙이기, 안 맞으면 is_active=false (지우지 않음)

진행 위치는 logs/title_screen_cleanup_state.json 에 남겨 끊겨도 이어서 한다.
순서도: docs/flowcharts/title_screen_d.md (정리)
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import VERDICT_ADOPT, KeywordCandidate
from ...models.title import MainTitle, TempTitle
from . import extract, inventory, rules
from .screen import Screener

logger = get_logger("title_screen", "app.log")

STATE = Path("logs/title_screen_cleanup_state.json")
BACKUPS = ("temp_titles", "main_titles", "keyword_candidates")
DEFERRED = "screen_deferred"
NOTE_OFF = "[D정리1102 끔]"
NOTE_TAG = "[D정리1102 칸]"
CHUNK = 500


def load_state() -> Dict[str, Any]:
    """진행 위치."""
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def track(state: Dict[str, Any], ai: Any) -> None:
    """AI 글자 수(비용 어림용)를 회차 시작값 위에 더해 둔다."""
    if ai is not None:
        state["chars_in"] = state.get("_base_in", 0) + ai.chars_in
        state["chars_out"] = state.get("_base_out", 0) + ai.chars_out


def save_state(state: Dict[str, Any]) -> None:
    """진행 위치 저장."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


async def backup(db: AsyncSession) -> Dict[str, int]:
    """bak_1102_* 표가 없을 때만 만든다(두 번 돌려도 첫 백업을 덮지 않는다)."""
    out = {}
    for table in BACKUPS:
        await db.execute(text(f"CREATE TABLE IF NOT EXISTS bak_1102_{table} AS "
                              f"SELECT * FROM {table}"))
        out[table] = (await db.execute(text(f"SELECT count(*) FROM bak_1102_{table}"))).scalar()
    await db.commit()
    return out


async def run_temp(db: AsyncSession, state: Dict[str, Any], s: Screener,
                   max_rows: int) -> Counter:
    """임시 제목을 id 순으로 CHUNK 개씩."""
    total: Counter = Counter(state.get("temp_counts") or {})
    done = 0
    while done < max_rows:
        rows = list((await db.execute(
            select(TempTitle).where(TempTitle.id > int(state.get("temp_cursor") or 0),
                                    TempTitle.screen_result.is_(None),
                                    TempTitle.status.in_(["new", "categorized"]))
            .order_by(TempTitle.id).limit(CHUNK))).scalars().all())
        if not rows:
            # 판정을 미룬 것(AI·검색량 실패)은 한 바퀴 더 본다
            if int(state.get("temp_pass") or 1) < 2:
                state.update(temp_pass=2, temp_cursor=0)
                continue
            state["temp_done"] = True
            break
        last = rows[-1].id
        total.update(await s.temp(rows))
        state.update(temp_cursor=last, temp_counts=dict(total), stats=dict(s.stats),
                     ai_calls=s.ai.calls if s.ai else 0, volume_calls=s.meter.calls)
        track(state, s.ai)
        save_state(state)
        done += len(rows)
        logger.info("[TITLE_SCREEN_CLEANUP] 임시 ~%d | %s", last, dict(total))
    return total


async def run_main(db: AsyncSession, state: Dict[str, Any], s: Screener,
                   max_rows: int) -> Counter:
    """정식 available 을 id 순으로 — 지우지 않고 표시만."""
    total: Counter = Counter(state.get("main_counts") or {})
    done = 0
    while done < max_rows:
        rows = list((await db.execute(
            select(MainTitle).where(MainTitle.id > int(state.get("main_cursor") or 0),
                                    MainTitle.status == "available",
                                    MainTitle.cpa_offer_id.is_(None),
                                    MainTitle.screen_result.is_(None))
            .order_by(MainTitle.id).limit(CHUNK))).scalars().all())
        if not rows:
            # 판정을 미룬 것(AI·검색량 실패)은 한 바퀴 더 본다
            if int(state.get("main_pass") or 1) < 2:
                state.update(main_pass=2, main_cursor=0)
                continue
            state["main_done"] = True
            break
        last = rows[-1].id
        out = await s.main(rows)
        total.update(v.result for v in out["verdicts"])
        state.update(main_cursor=last, main_counts=dict(total), stats=dict(s.stats),
                     ai_calls=s.ai.calls if s.ai else 0, volume_calls=s.meter.calls)
        track(state, s.ai)
        save_state(state)
        done += len(rows)
        logger.info("[TITLE_SCREEN_CLEANUP] 정식 ~%d | %s", last, dict(total))
    return total


async def safety(db: AsyncSession) -> List[dict]:
    """7일 치 아래로 떨어진 블로그 칸의 거름 표시를 미룬다(발행이 끊기지 않게)."""
    deferred = []
    for b in await inventory.stock(db):
        if b.title_days >= inventory.SAFE_DAYS:
            continue
        res = await db.execute(
            update(MainTitle).where(MainTitle.subtopic_id.in_(b.subtopics),
                                    MainTitle.status == "available",
                                    MainTitle.screen_result == "screened_out")
            .values(screen_result=DEFERRED))
        deferred.append({"blog": b.name, "days_before": b.title_days,
                         "deferred": res.rowcount})
    await db.commit()
    return deferred


async def run_keywords(db: AsyncSession, state: Dict[str, Any], max_rows: int) -> Counter:
    """칸 없는 채택 검색어 — 버릴 말은 끄고, 나머지는 AI 로 칸을 붙인다(0이면 끔)."""
    cat = await extract.catalog(db, 1)
    ai = extract.Extractor(db, cat)
    state["_base_in"], state["_base_out"] = state.get("chars_in", 0), state.get("chars_out", 0)
    total: Counter = Counter(state.get("kw_counts") or {})
    done = 0
    while done < max_rows:
        rows = list((await db.execute(
            select(KeywordCandidate).where(
                KeywordCandidate.id > int(state.get("kw_cursor") or 0),
                KeywordCandidate.verdict == VERDICT_ADOPT, KeywordCandidate.is_active.is_(True),
                KeywordCandidate.subtopic_id.is_(None))
            .order_by(KeywordCandidate.id).limit(extract.KW_BATCH))).scalars().all())
        if not rows:
            state["kw_done"] = True
            break
        total.update(await _tag(rows, ai, cat))
        await db.commit()
        state.update(kw_cursor=rows[-1].id, kw_counts=dict(total), kw_ai_calls=ai.calls)
        track(state, ai)
        save_state(state)
        done += len(rows)
    return total


async def _tag(rows: List[KeywordCandidate], ai: extract.Extractor, cat: dict) -> Counter:
    """검색어 한 묶음 처리."""
    out: Counter = Counter()
    todo = []
    for r in rows:
        if rules.keyword_junk(r.keyword):
            _off(r, "버릴 말")
            out["off_junk"] += 1
        else:
            todo.append(r)
    if not todo:
        return out
    ans = await ai.keywords([r.keyword for r in todo])
    if not ans:
        out["skip"] += len(todo)
        return out
    for i, r in enumerate(todo):
        if i not in ans:
            out["skip"] += 1
        elif ans[i] is None:
            _off(r, "칸 없음")
            out["off_niche"] += 1
        else:
            r.subtopic_id, r.topic_id = ans[i], cat[ans[i]][0]
            r.note = ((r.note or "") + f" {NOTE_TAG}").strip()
            out["tagged"] += 1
    return out


def _off(row: KeywordCandidate, why: str) -> None:
    """끈다(지우지 않음). 되돌리기 표시를 note 에 남긴다."""
    row.is_active = False
    row.note = ((row.note or "") + f" {NOTE_OFF} {why}").strip()
