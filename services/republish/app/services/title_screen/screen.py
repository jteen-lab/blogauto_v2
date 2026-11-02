"""2~6단계를 묶어 돌린다 — 임시 제목(떨어지면 삭제+지문)·정식 제목(떨어지면 '거름' 표시만).

    0원 규칙·지문 → AI 검색어 후보(50개 묶음) → 검색량 실측 → 판정
      → 통과: 검색어·검색량·칸 이름표, 채택 검색어 창고에, 임시 제목은 categorized
      → 보류: 표시만
      → 떨어짐: 임시 제목 삭제 + 지문 / 정식 제목 screened_out 표시
    → 사이트 점수(본 수·통과 수)

순서도: docs/flowcharts/title_screen_d.md
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.title import MainTitle, TempTitle
from ...models.title_screen import TitleFingerprint
from . import extract, judge, rules, sites
from .measure import VolumeMeter

logger = get_logger("title_screen", "app.log")

SCREENED_OUT = "screened_out"


class Screener:
    """한 회차 동안 칸 목록·검색량 기억·AI 호출 수를 들고 있다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.cat: Dict[int, Tuple[int, str]] = {}
        self.ai: Optional[extract.Extractor] = None
        self.meter = VolumeMeter(db, user_id)
        self.stats: Counter = Counter()

    async def _ready(self) -> None:
        if self.ai is None:
            self.cat = await extract.catalog(self.db, self.user_id)
            self.ai = extract.Extractor(self.db, self.cat)

    async def _known_fps(self, fps: List[str]) -> Set[str]:
        rows = (await self.db.execute(select(TitleFingerprint.fingerprint).where(
            TitleFingerprint.fingerprint.in_(fps)))).scalars().all()
        return set(rows)

    async def verdicts(self, titles: List[str]) -> List[judge.Verdict]:
        """제목 목록 → 판정(규칙에 걸린 것은 reason=규칙 이름)."""
        await self._ready()
        known = await self._known_fps([rules.fingerprint(t) for t in titles])
        out: List[Optional[judge.Verdict]] = [None] * len(titles)
        todo: List[int] = []
        for i, t in enumerate(titles):
            reason = "fingerprint" if rules.fingerprint(t) in known else rules.junk_reason(t)
            if reason:
                out[i] = judge.Verdict(judge.FAIL, reason)
            else:
                todo.append(i)
        picked: Dict[int, extract.Picked] = {}
        for s in range(0, len(todo), extract.BATCH):
            chunk = todo[s:s + extract.BATCH]
            ans = await self.ai.titles([titles[i] for i in chunk])
            picked.update({chunk[j]: p for j, p in ans.items()})
        vols = await self.meter.measure(c for p in picked.values() for c in p.candidates)
        for i in todo:
            out[i] = judge.judge(picked.get(i), vols)
        for v in out:
            self.stats[f"{v.result}:{v.reason}"] += 1
        return out  # type: ignore[return-value]

    async def _adopt(self, verdicts: List[judge.Verdict]) -> Dict[str, int]:
        words = [(v.keyword, v.volume, v.subtopic_id, self.cat[v.subtopic_id][0])
                 for v in verdicts if v.result == judge.PASS and v.subtopic_id in self.cat]
        return await judge.adopt(self.db, self.user_id, words)

    async def temp(self, rows: List[TempTitle]) -> Dict[str, int]:
        """임시 제목 묶음 판정·반영. 떨어진 것은 지우고 지문을 남긴다."""
        if not rows:
            return {}
        verdicts = await self.verdicts([r.title for r in rows])
        ids = await self._adopt(verdicts)
        now = datetime.now(timezone.utc)
        drop: List[int] = []
        fps: Dict[str, Tuple[str, str]] = {}
        site_counts: Dict[str, List[int]] = {}
        for row, v in zip(rows, verdicts):
            if v.result == judge.SKIP:
                continue
            site = rules.site_key(row.source_post_url or row.source_blog_url)
            if site and v.reason not in ("fingerprint",):
                c = site_counts.setdefault(site, [0, 0])
                c[0] += 1
                c[1] += v.result == judge.PASS
            if v.result == judge.FAIL:
                drop.append(row.id)
                fps.setdefault(rules.fingerprint(row.title), (v.reason, site))
                continue
            row.screen_result, row.screened_at = v.result, now
            row.lead_keyword, row.search_volume = (v.keyword or "")[:200] or None, v.volume
            if v.result == judge.PASS:
                self._label(row, v, ids)
        await self._forget(drop, fps)
        await sites.record(self.db, self.user_id,
                           {s: (c[0], c[1]) for s, c in site_counts.items()})
        await self.db.commit()
        return {"passed": sum(v.result == judge.PASS for v in verdicts),
                "held": sum(v.result == judge.HOLD for v in verdicts), "dropped": len(drop)}

    def _label(self, row: Any, v: judge.Verdict, ids: Dict[str, int]) -> None:
        """통과 제목에 칸·검색어 id. 임시 제목은 정식 이동 대상(categorized)."""
        from .measure import key

        row.candidate_id = ids.get(key(v.keyword or "")) or row.candidate_id
        if isinstance(row, TempTitle) or row.subtopic_id is None:
            row.subtopic_id = v.subtopic_id
            row.topic_id = self.cat[v.subtopic_id][0]
        if isinstance(row, TempTitle):
            row.status = "categorized"

    async def _forget(self, ids: List[int], fps: Dict[str, Tuple[str, str]]) -> None:
        """임시 제목 삭제 + 지문 보관(이미 있는 지문은 건너뜀)."""
        if fps:
            known = await self._known_fps(list(fps))
            for fp, (reason, site) in fps.items():
                if fp and fp not in known:
                    self.db.add(TitleFingerprint(fingerprint=fp, reason=reason[:60],
                                                 site=(site or None) and site[:255]))
        if ids:
            await self.db.execute(delete(TempTitle).where(TempTitle.id.in_(ids)))

    async def main(self, rows: List[MainTitle], mark: bool = True) -> Dict[str, Any]:
        """정식 제목 묶음 — 지우지 않고 통과분은 채우고 떨어진 것은 거름 표시.

        mark=False 면 판정만 돌려준다(안전장치: 7일 치 아래로 떨어지는 블로그 확인용).
        """
        if not rows:
            return {"verdicts": []}
        verdicts = await self.verdicts([r.title for r in rows])
        if not mark:
            return {"verdicts": verdicts}
        ids = await self._adopt(verdicts)
        now = datetime.now(timezone.utc)
        site_counts: Dict[str, Tuple[int, int]] = {}
        for row, v in zip(rows, verdicts):
            if v.result == judge.SKIP:
                continue
            apply_main(row, v, now)
            if v.result == judge.PASS:
                self._label(row, v, ids)
            site = rules.site_key(row.source_url)
            if site and row.source == "transfer":
                seen, passed = site_counts.get(site, (0, 0))
                site_counts[site] = (seen + 1, passed + (v.result == judge.PASS))
        await sites.record(self.db, self.user_id, site_counts)
        await self.db.commit()
        return {"verdicts": verdicts}


def apply_main(row: MainTitle, v: judge.Verdict, now: datetime) -> None:
    """정식 제목 하나에 판정을 적는다(떨어짐 = screened_out)."""
    row.screen_result = SCREENED_OUT if v.result == judge.FAIL else v.result
    row.screened_at = now
    if v.keyword:
        row.lead_keyword = v.keyword[:200]
        row.search_volume, row.search_volume_at = v.volume, now


async def screen_new_temp(db: AsyncSession, user_id: int, limit: int) -> Dict[str, Any]:
    """새로 들어온(아직 판정 안 한) 임시 제목을 최근 것부터 limit 개 거른다."""
    rows = list((await db.execute(
        select(TempTitle).where(TempTitle.screen_result.is_(None),
                                TempTitle.status.in_(["new", "categorized"]),
                                TempTitle.collection_stage != "keyword_module")
        .order_by(TempTitle.id.desc()).limit(max(1, limit)))).scalars().all())
    if not rows:
        return {"screened": 0}
    s = Screener(db, user_id)
    out = await s.temp(rows)
    out.update({"screened": len(rows), "ai_calls": s.ai.calls if s.ai else 0,
                "volume_calls": s.meter.calls})
    logger.info("[TITLE_SCREEN] 새 임시 제목 %d개 → %s", len(rows), out)
    return out
