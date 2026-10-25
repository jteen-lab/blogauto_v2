"""리뉴얼 대상 고르기 — 성과 순서 · 블로그오토 전 옛 글 포함 (2026-10-25).

예전 규칙(6개월 지난 블로그오토 글만)은 인생꿀팁에서 한 번도 대상을 찾지 못했다
(가장 오래된 블로그오토 글 5/13 → 11/13 전 0편, 실제 유입은 옛 글 663편에).
블로그 ``renewal_config.pick == "performance"`` 일 때만 이 규칙을 쓴다.

    1. 유입이 있었는데 줄어드는 글        → augment (직전 창 네이버 유입 큰 순)
    2. 노출은 있는데 유입 적은 글          → title   (서치콘솔 이력 있는 글만)
    3. 유입·노출 다 없는 옛 글(crawled)    → rewrite (오래된 순, GA 수집 14일↑일 때만)
    4. 6개월 지난 블로그오토 글            → legacy  (예전 규칙)

빼는 글: 정리된 글(status=unpublished), exclude_paths, min_gap_days 안에 리뉴얼한 글,
제목이 관문 위험주제·대출 상품인 글(지어낸 시간·번호, 금지 상품). 하루 상한 max_per_day.

순서도: docs/flowcharts/renewal_performance_pick.md (1. 고르기)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from . import renewal_ga

logger = get_logger("renewal_pick", "app.log")

KST = timezone(timedelta(hours=9))
DEFAULT_GAP_DAYS = 90
DEFAULT_PER_DAY = 1


@dataclass
class Row:
    """후보 글 한 줄(가벼운 값만)."""

    id: int
    source: str
    title: str
    url: str
    published_at: Optional[datetime]
    last_renewed_at: Optional[datetime]


def enabled(cfg: Optional[dict]) -> bool:
    """새 고르기 규칙을 쓰는 블로그인가."""
    return bool(cfg) and cfg.get("pick") == "performance"


def blocked_title(title: str) -> bool:
    """제목 관문 1·3·4(위험주제·대출)에 걸리는 글은 리뉴얼하지 않는다."""
    from ..generation.topic_gate import check_title

    v = check_title(title or "")
    return bool(v and v.code in ("위험주제", "대부업체", "대출상품"))


async def renewed_today(db: AsyncSession, blog_id: int) -> int:
    """오늘(한국 날짜) 리뉴얼한 글 수."""
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((await db.execute(sql(
        "select count(*) from crawled_posts where blog_id = :b "
        "and last_renewed_at >= :s"), {"b": blog_id, "s": start})).scalar() or 0)


async def load_rows(db: AsyncSession, blog_id: int, gap_days: int,
                    exclude_paths: List[str]) -> List[Row]:
    """리뉴얼해도 되는 글(라이브 주소가 있고 정리되지 않은 글)."""
    since = datetime.now(timezone.utc) - timedelta(days=gap_days)
    rows = (await db.execute(sql(
        "select id, source, coalesce(title,''), coalesce(url,''), published_at, "
        "last_renewed_at from crawled_posts where blog_id = :b "
        "and source in ('crawled','generated') and platform_post_id is not null "
        "and published_at is not null and coalesce(status,'') <> 'unpublished' "
        "and (last_renewed_at is null or last_renewed_at < :since)"),
        {"b": blog_id, "since": since})).all()
    skip = {renewal_ga.url_path(p) for p in exclude_paths}
    return [Row(*r) for r in rows
            if renewal_ga.url_path(r[3]) not in skip and not blocked_title(r[2])]


def pick_order(rows: List[Row], view: renewal_ga.GaView,
               months: int) -> Optional[tuple]:
    """(Row, 단계 이름, 이유). 1→3→4 순서(2 는 load 쪽에서 따로 본다). 순수 함수."""
    def stat(r: Row) -> renewal_ga.GaStat:
        return view.stats.get(r.id) or renewal_ga.GaStat()

    decl = []
    for r in rows:
        act, why = renewal_ga.classify(view.stats.get(r.id), view.usable,
                                       r.id in view.top_ids)
        if act == "augment" and stat(r).naver_prev > 0:
            decl.append((stat(r).naver_prev, r, why))
    if decl:
        _, r, why = max(decl, key=lambda x: x[0])
        return r, "1-augment", why
    if view.usable:
        zero = [r for r in rows if r.source == "crawled" and r.id not in view.stats]
        if zero:
            r = min(zero, key=lambda x: x.published_at or datetime.max.replace(tzinfo=timezone.utc))
            return r, "3-rewrite", "GA 방문 0 옛 글 — 재작성"
    cut = datetime.now(timezone.utc) - timedelta(days=months * 30)
    old = [r for r in rows if r.source == "generated"
           and _aware(r.last_renewed_at or r.published_at) <= cut]
    if old:
        r = min(old, key=lambda x: _aware(x.last_renewed_at or x.published_at))
        return r, "4-legacy", f"블로그오토 글 {months}개월 지남"
    return None


def _aware(d: Optional[datetime]) -> datetime:
    """시간대 없는 값은 UTC 로."""
    if d is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


async def title_candidate(db: AsyncSession, blog_id: int,
                          rows: List[Row]) -> Optional[tuple]:
    """2단계: 서치콘솔 노출이 있고 판정이 title 인 글."""
    from ..analytics.performance import evaluate

    ids = {r.id: r for r in rows}
    urls = (await db.execute(sql(
        "select s.id, s.crawled_post_id from search_visibility_urls s "
        "join post_metrics_daily m on m.url_id = s.id where s.blog_id = :b "
        "and m.date > current_date - 28 group by 1,2 having sum(m.impressions) > 0"),
        {"b": blog_id})).all()
    for url_id, pid in urls:
        if pid in ids:
            perf = await evaluate(db, url_id)
            if perf.action == "title":
                return ids[pid], "2-title", perf.reason
    return None


async def find_due(db: AsyncSession, blog: Any, cfg: Dict[str, Any]):
    """오늘 리뉴얼할 글(CrawledPost)과 고른 이유. 없으면 None."""
    from ...models.crawled_post import CrawledPost

    cap = int(cfg.get("max_per_day", DEFAULT_PER_DAY) or 0)
    if cap <= 0 or await renewed_today(db, blog.id) >= cap:
        return None
    rows = await load_rows(db, blog.id, int(cfg.get("min_gap_days", DEFAULT_GAP_DAYS)),
                           list(cfg.get("exclude_paths") or []))
    view = await renewal_ga.load_view(db, blog.id)
    picked = pick_order(rows, view, int(cfg.get("default_period_months", 6) or 6))
    if picked is None or picked[1] != "1-augment":
        picked = await title_candidate(db, blog.id, rows) or picked
    if picked is None:
        logger.info("[RENEWAL_PICK] 대상 없음 | blog=%s | 후보 %d", blog.name, len(rows))
        return None
    row, stage, why = picked
    logger.info("[RENEWAL_PICK] %s | blog=%s | post=%s | %s | %s",
                stage, blog.name, row.id, row.url, why)
    return await db.get(CrawledPost, row.id), stage
