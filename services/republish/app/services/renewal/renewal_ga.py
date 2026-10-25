"""리뉴얼 성과 판정 — 서치콘솔 이력이 없는 글은 GA(page_metrics_daily)로 읽는다.

블로그오토 전 옛 글(crawled)은 search_visibility_urls 이력이 없어 판정이 안 됐다.
GA 는 옛 글 주소까지 날마다 쌓인다(방문이 있는 날만 행이 생긴다).

- **없는 것을 0 으로 읽지 않는다.** 행이 없는 글을 '유입 0' 으로 보는 것은 그 블로그의
  GA 수집이 MIN_COVERAGE 일 이상 쌓였을 때만이다. 아니면 legacy(판정 안 함).
- 수집 기간 = 이 블로그 첫 행 ~ GA 수집 마지막 날. 창 = min(28일, 수집 기간/2)(9/13 부터라 28일×2 를 못 채움).
- 줄어듦은 네이버 유입으로, '유입 0' 은 전체 방문으로 본다(구글로 들어오는 글을 갈아엎지 않게).
- 수익 글 보호: 최근 창 네이버 유입 상위 TOP_N 편은 rewrite 금지(→ augment), 제목 그대로.

순서도: docs/flowcharts/renewal_performance_pick.md (1. 고르기 · 2. 성과 판정)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("renewal_ga", "app.log")

MIN_COVERAGE = 14   # 블로그 GA 수집이 이만큼 쌓여야 '행 없음 = 유입 0'
BASE_WINDOW = 28
TOP_N = 10
DECAY = 0.20        # analytics.performance.DEFAULTS 와 같은 출발점


@dataclass
class GaStat:
    """한 글의 GA 창 두 개 합."""

    naver_cur: int = 0
    naver_prev: int = 0
    sessions_cur: int = 0
    sessions_prev: int = 0


@dataclass
class GaView:
    """블로그 한 곳의 GA 읽기 결과(리뉴얼 고르기 한 번에 한 번만 읽는다)."""

    coverage_days: int
    window: int
    last: Optional[date]
    stats: Dict[int, GaStat]
    top_ids: Set[int]

    @property
    def usable(self) -> bool:
        """'행 없음 = 유입 0' 으로 읽어도 되나."""
        return self.coverage_days >= MIN_COVERAGE


def url_path(url: str) -> str:
    """글 주소 → GA 경로('/555/')."""
    p = urlparse(url or "").path or "/"
    return p if p.endswith("/") else p + "/"


def window_for(coverage_days: int) -> int:
    """창 길이(일). 수집일수 절반과 28일 중 작은 쪽, 최소 7일."""
    return max(7, min(BASE_WINDOW, coverage_days // 2))


def classify(stat: Optional[GaStat], usable: bool, protected: bool,
             decay: float = DECAY) -> Tuple[str, str]:
    """(action, reason). 순수 함수."""
    if not usable:
        return "legacy", "GA 수집 부족 — 판정 보류"
    s = stat or GaStat()
    if s.sessions_cur == 0 and s.sessions_prev == 0:
        if protected:
            return "augment", "유입 0 이지만 보호 글 — 보강만"
        return "rewrite", "GA 방문 0(두 창 모두) — 재작성"
    if s.naver_prev > 0 and s.naver_cur <= s.naver_prev * (1 - decay):
        return "augment", f"네이버 유입 {s.naver_prev}→{s.naver_cur} 줄어듦 — 보강"
    return "keep", f"유입 유지(네이버 {s.naver_prev}→{s.naver_cur}) — 건드리지 않음"


async def load_view(db: AsyncSession, blog_id: int) -> GaView:
    """블로그의 GA 를 글별 두 창 합으로 읽는다."""
    # 방문이 적은 블로그는 행이 드문드문이라 '행 있는 날 수'로 세면 수집 기간을 잘못 본다.
    # 수집 기간 = 이 블로그 첫 행 ~ GA 수집 마지막 날(모든 블로그 중 최신).
    cov = (await db.execute(sql(
        "select (select min(date) from page_metrics_daily where blog_id = :b), "
        "(select max(date) from page_metrics_daily)"), {"b": blog_id})).first()
    first, last = cov[0], cov[1]
    days = (last - first).days + 1 if first and last else 0
    win = window_for(days)
    if not last:
        return GaView(days, win, None, {}, set())
    paths = {url_path(u): pid for pid, u in (await db.execute(sql(
        "select id, url from crawled_posts where blog_id = :b and url is not null"),
        {"b": blog_id})).all()}
    rows = (await db.execute(sql(
        "select crawled_post_id, path, date, naver_sessions, sessions "
        "from page_metrics_daily where blog_id = :b and date > :since"),
        {"b": blog_id, "since": last - timedelta(days=win * 2)})).all()
    stats: Dict[int, GaStat] = {}
    cut = last - timedelta(days=win)
    for pid, path, d, naver, sess in rows:
        pid = pid or paths.get(path)
        if not pid:
            continue
        st = stats.setdefault(pid, GaStat())
        if d > cut:
            st.naver_cur += naver or 0
            st.sessions_cur += sess or 0
        else:
            st.naver_prev += naver or 0
            st.sessions_prev += sess or 0
    ranked = sorted(stats.items(), key=lambda kv: kv[1].naver_cur, reverse=True)
    top = {pid for pid, st in ranked[:TOP_N] if st.naver_cur > 0}
    return GaView(days, win, last, stats, top)


async def performance(db: AsyncSession, blog_id: int, post_id: int,
                      view: Optional[GaView] = None):
    """analytics.performance.Performance 모양으로 돌려준다(renewal_service 용)."""
    from ..analytics.performance import Performance

    view = view or await load_view(db, blog_id)
    stat = view.stats.get(post_id)
    action, reason = classify(stat, view.usable, post_id in view.top_ids)
    s = stat or GaStat()
    return Performance(url_id=0, action=action,
                       reason=f"[GA {view.window}일] {reason}",
                       sessions=s.sessions_cur, prev_sessions=s.sessions_prev,
                       days=view.coverage_days)
