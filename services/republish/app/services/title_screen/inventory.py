"""0-1 블로그별 재고 계기판 — 블로그마다 '쓸 제목·안 쓴 검색어가 며칠 치 남았나'.

    쓸 제목   = 정식 제목 available 중 거름(screened_out)·보류(hold)·CPA 전용이 아닌 것
              + 거르기를 통과하고 정식 이동을 기다리는 임시 제목(이동은 6시간마다라 빼면
                채우기가 '안 늘었다'고 잘못 본다)
    안 쓴 검색어 = 채택·켜짐·아직 제목 안 만든(titled=false) 검색어
    여러 블로그가 같은 칸을 쓰면 그 칸 수를 블로그 수로 나눈다.
    며칠 치 = 수 ÷ 하루 목표(성장 프로파일의 지금 구간 발행 수, 없으면 1)

순서도: docs/flowcharts/title_screen_d.md (0-1)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Set

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("title_screen", "app.log")

SHORT_DAYS = 30     # 이보다 적으면 '부족'
FULL_DAYS = 45      # 채움 기준
SAFE_DAYS = 7       # 정리 안전장치


@dataclass
class BlogStock:
    """블로그 하나의 재고."""

    blog_id: int
    name: str
    daily: int
    titles: float
    keywords: float
    subtopics: List[int]

    @property
    def title_days(self) -> float:
        """쓸 제목 며칠 치."""
        return round(self.titles / max(1, self.daily), 1)

    @property
    def keyword_days(self) -> float:
        """안 쓴 검색어 며칠 치."""
        return round(self.keywords / max(1, self.daily), 1)

    def to_dict(self) -> dict:
        """화면·보고용."""
        d = asdict(self)
        d.update(title_days=self.title_days, keyword_days=self.keyword_days,
                 titles=round(self.titles, 1), keywords=round(self.keywords, 1))
        return d


def usable_title():
    """쓸 제목 조건(고르기 거름과 같은 기준)."""
    from ...models.title import MainTitle

    return and_(MainTitle.status == "available", MainTitle.cpa_offer_id.is_(None),
                or_(MainTitle.screen_result.is_(None),
                    MainTitle.screen_result.notin_(["screened_out", "hold"])))


async def blog_subtopics(db: AsyncSession) -> Dict[int, Set[int]]:
    """활성 블로그 → 쓰는 칸 집합."""
    from ...models.blog import Blog
    from ...models.category import BlogCategory

    rows = (await db.execute(
        select(BlogCategory.blog_id, BlogCategory.subtopic_id)
        .join(Blog, Blog.id == BlogCategory.blog_id)
        .where(BlogCategory.is_active.is_(True), BlogCategory.subtopic_id.is_not(None),
               Blog.is_active.is_(True)))).all()
    out: Dict[int, Set[int]] = {}
    for bid, sid in rows:
        out.setdefault(bid, set()).add(sid)
    return out


async def daily_targets(db: AsyncSession) -> Dict[int, int]:
    """블로그 → 하루 발행 목표(성장 프로파일의 지금 구간 publish.daily_count)."""
    from ...models.blog import Blog
    from ..generation.growth_profile_resolver import GrowthProfileResolver
    from sqlalchemy import text

    rows = (await db.execute(text(
        "select fb.blog_id, m.settings from flow_modules fm "
        "join modules m on m.id = fm.module_id "
        "join module_types mt on mt.id = m.module_type_id "
        "join flow_blogs fb on fb.flow_id = fm.flow_id "
        "where mt.code = 'growth_profile' and fm.is_active"))).all()
    posts = dict((await db.execute(select(Blog.id, Blog.total_post_count))).all())
    out: Dict[int, int] = {}
    for bid, settings in rows:
        stage = GrowthProfileResolver.resolve_stage_for_blog(
            posts.get(bid) or 0, (settings or {}).get("stages") or [])
        try:
            n = int(((stage or {}).get("publish") or {}).get("daily_count") or 1)
        except (TypeError, ValueError):
            n = 1
        out[bid] = max(out.get(bid, 1), n)
    return out


async def _per_subtopic(db: AsyncSession) -> tuple:
    """칸별 쓸 제목 수, 칸별 안 쓴 검색어 수."""
    from ...models.keyword_candidate import VERDICT_ADOPT, KeywordCandidate
    from ...models.title import MainTitle

    from ...models.title import TempTitle

    titles = dict((await db.execute(
        select(MainTitle.subtopic_id, func.count()).where(usable_title())
        .group_by(MainTitle.subtopic_id))).all())
    pending = (await db.execute(
        select(TempTitle.subtopic_id, func.count()).where(
            TempTitle.screen_result == "pass", TempTitle.status.in_(["new", "categorized"]))
        .group_by(TempTitle.subtopic_id))).all()
    for sid, n in pending:
        titles[sid] = (titles.get(sid) or 0) + n
    kws = dict((await db.execute(
        select(KeywordCandidate.subtopic_id, func.count()).where(
            KeywordCandidate.verdict == VERDICT_ADOPT, KeywordCandidate.is_active.is_(True),
            KeywordCandidate.titled.is_(False), KeywordCandidate.subtopic_id.is_not(None))
        .group_by(KeywordCandidate.subtopic_id))).all())
    return titles, kws


async def stock(db: AsyncSession) -> List[BlogStock]:
    """블로그별 재고(며칠 치가 적은 순)."""
    from ...models.blog import Blog

    subs = await blog_subtopics(db)
    share: Dict[int, int] = {}
    for sids in subs.values():
        for s in sids:
            share[s] = share.get(s, 0) + 1
    titles, kws = await _per_subtopic(db)
    daily = await daily_targets(db)
    names = dict((await db.execute(select(Blog.id, Blog.name))).all())
    out = []
    for bid, sids in subs.items():
        t = sum((titles.get(s) or 0) / share[s] for s in sids)
        k = sum((kws.get(s) or 0) / share[s] for s in sids)
        out.append(BlogStock(bid, names.get(bid) or str(bid), daily.get(bid, 1), t, k,
                             sorted(sids)))
    out.sort(key=lambda b: b.title_days)
    return out
