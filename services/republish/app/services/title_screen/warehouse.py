"""0단계 검색어 창고 — 칸별 씨앗 말로 연관 검색어를 모은다(B7).

- 씨앗: 블로그 칸의 카테고리 키워드(사람이 등록) + 마케팅이 정한 블로그 씨앗(아래 표).
- 버릴 말: 주가·시세·맛집·게임·대출 상품·성인·띄어쓰기 깨진 말(rules.keyword_junk).
- 모든 검색어에 칸(subtopic) 이름표를 붙여 넣는다. 월 500 아래는 넣지 않는다.
- 블로그의 안 쓴 검색어가 30일 치 아래면 채우기(filler)가 이걸 먼저 부른다.

순서도: docs/flowcharts/title_screen_d.md (0)
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import VERDICT_ADOPT, KeywordCandidate
from . import rules
from .measure import key, norm_col

logger = get_logger("title_screen", "app.log")

MIN_VOLUME = 500
PER_SEED = 40
SEEDS_PER_ROUND = 5

# 마케팅 D 방식 0단계 블로그 씨앗(2026-11-02) — (씨앗, 칸 id)
BLOG_SEEDS: Dict[int, Tuple[Tuple[str, int], ...]] = {
    14: (("건강보험료", 107), ("대상포진", 66), ("갱년기", 66), ("지원금", 71)),
    9: (("연말정산", 87), ("종합소득세", 88), ("청약", 82), ("퇴직연금", 145)),
    7: (("등산코스", 25), ("여행코스", 27), ("자격증 시험일정", 169), ("실업급여", 104)),
    8: (("레시피", 54), ("끓이는법", 54), ("전시회 일정", 60)),
}


async def seeds_for(db: AsyncSession, blog_id: int, subtopics: List[int],
                    kw_count: Dict[int, int]) -> List[Tuple[str, int]]:
    """이번 회차 씨앗(말, 칸). 안 쓴 검색어가 적은 칸의 씨앗을 앞에."""
    from ...models.category import Keyword

    rows = (await db.execute(select(Keyword.name, Keyword.subtopic_id).where(
        Keyword.subtopic_id.in_(subtopics), Keyword.is_deleted.is_(False)))).all()
    pool = [(n, s) for n, s in rows if n] + list(BLOG_SEEDS.get(blog_id, ()))
    random.shuffle(pool)
    pool.sort(key=lambda p: kw_count.get(p[1], 0))
    return pool[:SEEDS_PER_ROUND]


async def refill(db: AsyncSession, user_id: int, blog_id: int,
                 subtopics: List[int], topic_of: Dict[int, int]) -> Dict[str, int]:
    """한 블로그 칸의 검색어를 채운다. 넣은 수·버린 수를 돌려준다."""
    from ..naver_ads_service import NaverAdsService
    from ...models.user_settings import UserSettings

    settings = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    service = NaverAdsService(settings)
    if not settings or not service.is_configured():
        return {"added": 0, "error": 1}
    kw_count = dict((await db.execute(
        select(KeywordCandidate.subtopic_id, func.count()).where(
            KeywordCandidate.subtopic_id.in_(subtopics), KeywordCandidate.titled.is_(False),
            KeywordCandidate.is_active.is_(True), KeywordCandidate.verdict == VERDICT_ADOPT)
        .group_by(KeywordCandidate.subtopic_id))).all())
    out = {"added": 0, "junk": 0, "low": 0, "seeds": 0}
    seen: set = set()   # 씨앗끼리 같은 연관어가 겹친다(세션 자동 flush 가 꺼져 있다)
    for seed, sid in await seeds_for(db, blog_id, subtopics, kw_count):
        res = await service.get_keyword_stats([seed], include_related=True)
        if not res.get("success"):
            continue
        out["seeds"] += 1
        rows = (res.get("keywords") or []) + (res.get("related_keywords") or [])
        await _store(db, user_id, seed, sid, topic_of.get(sid), rows[:200], out, seen)
    await db.commit()
    logger.info("[TITLE_SCREEN] 검색어 창고 채우기 blog=%s → %s", blog_id, out)
    return out


async def _store(db: AsyncSession, user_id: int, seed: str, sid: int, tid, rows: list,
                 out: Dict[str, int], seen: set) -> None:
    """한 씨앗의 응답을 거르고 넣는다(이미 있는 말·이번 회차에 넣은 말은 건너뜀)."""
    norm = norm_col(KeywordCandidate.keyword)
    keys = [key(r.get("keyword") or "") for r in rows]
    have = seen
    have.update((await db.execute(select(norm).where(
        KeywordCandidate.user_id == user_id, norm.in_(keys)))).scalars().all())
    now, added = datetime.now(timezone.utc), 0
    for r in rows:
        word, vol = (r.get("keyword") or "").strip(), int(r.get("total_search_volume") or 0)
        if not word or key(word) in have:
            continue
        if rules.keyword_junk(word):
            out["junk"] += 1
            continue
        if vol < MIN_VOLUME:
            out["low"] += 1
            continue
        db.add(KeywordCandidate(
            user_id=user_id, keyword=word[:200], seed=seed[:200], topic_id=tid, subtopic_id=sid,
            search_volume=vol, search_volume_pc=r.get("pc_search_volume"),
            search_volume_mobile=r.get("mobile_search_volume"),
            competition=r.get("competition"), verdict=VERDICT_ADOPT,
            verdict_reason="D 0단계 칸 씨앗", source="seed_warehouse", measured_at=now,
            is_active=True, titled=False))
        have.add(key(word))
        added += 1
        if added >= PER_SEED:
            break
    out["added"] += added
    await db.flush()
