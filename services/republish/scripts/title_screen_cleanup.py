"""이미 쌓인 제목 한 번 정리 실행기(D 방식, 2026-11-02).

    python scripts/title_screen_cleanup.py all            # 백업→임시→정식→안전장치→검색어→결과표
    python scripts/title_screen_cleanup.py temp --max 1000  # 한 단계만, 개수 제한(시험)
    python scripts/title_screen_cleanup.py report         # 결과표만

앱 컨테이너 안에서 PYTHONPATH=/app 로 돌린다. 끊기면 같은 명령으로 이어서 한다.
결과표: logs/title_screen_cleanup_report.json
순서도: docs/flowcharts/title_screen_d.md (정리)
"""
import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import func, select, text

REPORT = Path("logs/title_screen_cleanup_report.json")
WON_PER_USD = 1400


def cost_won(state: Dict[str, Any]) -> int:
    """AI 비용 어림(gpt-4o-mini, 입력 0.15·출력 0.6 달러/100만 토큰, 한글 1자≈1토큰)."""
    cin, cout = state.get("chars_in", 0), state.get("chars_out", 0)
    return round((cin * 0.15 + cout * 0.6) / 1e6 * WON_PER_USD)


async def report(db) -> Dict[str, Any]:
    """블로그별 남은 쓸 제목·며칠 치·거름 수 + 전체 숫자."""
    from app.models.keyword_candidate import KeywordCandidate
    from app.models.title import MainTitle
    from app.models.title_screen import TitleFingerprint, TitleSiteScore
    from app.services.title_screen import cleanup, inventory

    state = cleanup.load_state()
    blogs = []
    for b in await inventory.stock(db):
        out = dict(b.to_dict())
        for label, val in (("screened_out", "screened_out"), ("deferred", cleanup.DEFERRED),
                           ("passed", "pass"), ("hold", "hold")):
            out[label] = (await db.execute(select(func.count()).where(
                MainTitle.subtopic_id.in_(b.subtopics), MainTitle.status == "available",
                MainTitle.screen_result == val))).scalar()
        blogs.append(out)
    sites = dict((await db.execute(select(TitleSiteScore.status, func.count())
                                   .group_by(TitleSiteScore.status))).all())
    tagged = (await db.execute(select(func.count()).where(
        KeywordCandidate.note.like(f"%{cleanup.NOTE_TAG}%")))).scalar()
    off = (await db.execute(select(func.count()).where(
        KeywordCandidate.note.like(f"%{cleanup.NOTE_OFF}%")))).scalar()
    fps = (await db.execute(select(func.count(TitleFingerprint.id)))).scalar()
    rep = {"blogs": blogs, "sites": sites, "keywords_tagged": tagged, "keywords_off": off,
           "fingerprints": fps, "temp": state.get("temp_counts"), "main": state.get("main_counts"),
           "keywords": state.get("kw_counts"), "safety": state.get("safety"),
           "ai_calls": state.get("ai_calls", 0) + state.get("kw_ai_calls", 0),
           "volume_calls": state.get("volume_calls"), "stats": state.get("stats"),
           "ai_cost_won_est": cost_won(state)}
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


async def main(phase: str, max_rows: int) -> None:
    """단계 실행."""
    from app.core.database import db_manager
    from app.services.title_screen import cleanup
    from app.services.title_screen.screen import Screener

    state = cleanup.load_state()
    state["_base_in"], state["_base_out"] = state.get("chars_in", 0), state.get("chars_out", 0)
    async with db_manager.get_session() as db:
        if phase in ("all", "backup") and not state.get("backup"):
            state["backup"] = await cleanup.backup(db)
            cleanup.save_state(state)
        s = Screener(db, 1)
        if phase in ("all", "temp") and not state.get("temp_done"):
            await cleanup.run_temp(db, state, s, max_rows)
        if phase in ("all", "main") and not state.get("main_done"):
            await cleanup.run_main(db, state, s, max_rows)
        if phase in ("all", "safety") and state.get("main_done") and not state.get("safety_done"):
            state["safety"] = await cleanup.safety(db)
            state["safety_done"] = True
        if phase in ("all", "keywords") and not state.get("kw_done"):
            await cleanup.run_keywords(db, state, max_rows)
        cleanup.save_state(state)
        rep = await report(db)
    print(json.dumps({k: rep[k] for k in rep if k != "blogs"}, ensure_ascii=False))
    for b in rep["blogs"]:
        print(b["name"], b["title_days"], b["keyword_days"], b["screened_out"], b["deferred"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["all", "backup", "temp", "main", "safety", "keywords",
                                      "report"])
    ap.add_argument("--max", type=int, default=10 ** 9)
    args = ap.parse_args()
    asyncio.run(main(args.phase, args.max))
