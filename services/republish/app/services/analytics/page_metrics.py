"""페이지별 유입 — 유입 경로(네이버/구글/직접/기타) + 옛 글까지.

GA4 가 준 (날짜·경로·source·medium) 행을 (경로·날짜) 칸으로 합쳐
`page_metrics_daily` 에 적는다. 블로그오토 발행 글인지, 옛 글(crawled_posts)
인지 표시해 두면 대시보드가 "어느 글이 네이버에서 사람을 데려오나" 를 보여 준다.

순서도: docs/flowcharts/analytics_sources.md
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.page_metric import PageMetricDaily
from .url_match import path_of

logger = get_logger("analytics_pages", "app.log")

CHANNELS = ("naver", "google", "direct", "other")


def classify_channel(source: Optional[str], medium: Optional[str] = None) -> str:
    """GA4 sessionSource/sessionMedium 을 네 갈래로 나눈다.

    네이버는 검색(search.naver.com)·블로그·카페 등 출처 이름이 여러 개라
    'naver' 가 들어 있으면 모두 네이버로 본다. 구글도 같다.
    """
    src = (source or "").strip().lower()
    if src in ("(direct)", "direct") or (
            not src and (medium or "").strip().lower() in ("(none)", "")):
        return "direct"
    if "naver" in src:
        return "naver"
    if "google" in src:
        return "google"
    return "other"


def aggregate_pages(rows: Iterable[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    """GA4 행을 (경로, 날짜) 칸으로 합친다.

    평균 시간은 세션 가중평균이다. 경로별로 쪼개진 평균을 그냥 더하거나
    큰 값만 남기면 방문이 적은 경로의 값이 전체를 흔든다.

    Returns:
        {(path, date): {"sessions", "engaged_sessions", "avg_duration",
                        "naver_sessions", ...}}
    """
    out: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        key_path = path_of(row.get("path") or "")
        day = _to_date(row.get("date"))
        if not key_path or day is None:
            continue
        slot = out.setdefault((key_path, day), {
            "sessions": 0, "engaged_sessions": 0, "_dur": 0.0,
            **{f"{c}_sessions": 0 for c in CHANNELS}})
        sessions = int(row.get("sessions") or 0)
        slot["sessions"] += sessions
        slot["engaged_sessions"] += int(row.get("engaged_sessions") or 0)
        slot["_dur"] += float(row.get("avg_duration") or 0.0) * sessions
        channel = classify_channel(row.get("source"), row.get("medium"))
        slot[f"{channel}_sessions"] += sessions
    for slot in out.values():
        dur = slot.pop("_dur")
        slot["avg_duration"] = (round(dur / slot["sessions"], 2)
                                if slot["sessions"] else 0.0)
    return out


def _to_date(raw: Any) -> Optional[date]:
    """'YYYY-MM-DD' 를 date 로. 깨졌으면 None."""
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


async def crawled_index(db: AsyncSession, blog_id: int) -> Dict[str, int]:
    """이 블로그 글(옛 글 포함)의 {경로: crawled_post_id}. 최신 글 우선."""
    rows = (await db.execute(text(
        "SELECT id, url FROM crawled_posts WHERE blog_id = :b "
        "AND url IS NOT NULL ORDER BY id DESC"), {"b": blog_id})).all()
    out: Dict[str, int] = {}
    for post_id, url in rows:
        key = path_of(url or "")
        if key and key != "/" and key not in out:
            out[key] = post_id
    return out


async def save_pages(db: AsyncSession, blog_id: int,
                     buckets: Dict[tuple, Dict[str, Any]],
                     autopost_paths: Set[str]) -> int:
    """그 블로그·그 기간을 지우고 다시 넣는다(GA4 는 최근치를 나중에 보정한다).

    Returns:
        적재한 행 수
    """
    if not buckets:
        return 0
    days = [key[1] for key in buckets]
    by_path = await crawled_index(db, blog_id)
    await db.execute(delete(PageMetricDaily).where(
        PageMetricDaily.blog_id == blog_id,
        PageMetricDaily.date >= min(days), PageMetricDaily.date <= max(days)))
    for (path, day), values in buckets.items():
        db.add(PageMetricDaily(
            blog_id=blog_id, date=day, path=path[:1000],
            crawled_post_id=by_path.get(path),
            is_autopost=path in autopost_paths, **values))
    return len(buckets)


async def summarize_sources(db: AsyncSession, days: int = 28,
                            blog_id: Optional[int] = None,
                            limit: int = 30) -> Dict[str, Any]:
    """대시보드용 — 블로그별 유입 경로 합계와 방문 많은 페이지."""
    since = date.today() - timedelta(days=days)
    where = [PageMetricDaily.date >= since]
    if blog_id:
        where.append(PageMetricDaily.blog_id == blog_id)
    sums = [func.coalesce(func.sum(getattr(PageMetricDaily, f"{c}_sessions")), 0)
            for c in CHANNELS]
    blogs = {b.id: b for b in (await db.execute(select(Blog))).scalars().all()}

    per_blog = []
    for row in (await db.execute(
            select(PageMetricDaily.blog_id,
                   func.coalesce(func.sum(PageMetricDaily.sessions), 0), *sums)
            .where(*where).group_by(PageMetricDaily.blog_id)
            .order_by(func.sum(PageMetricDaily.sessions).desc()))).all():
        blog = blogs.get(row[0])
        per_blog.append({"blog_id": row[0], "blog": blog.name if blog else "",
                         "sessions": int(row[1]),
                         **{c: int(v) for c, v in zip(CHANNELS, row[2:])}})
    totals = {"sessions": sum(b["sessions"] for b in per_blog),
              **{c: sum(b[c] for b in per_blog) for c in CHANNELS}}
    pages = await _top_pages(db, where, blogs, limit)
    return {"days": days, "totals": totals, "blogs": per_blog, "pages": pages}


async def _top_pages(db: AsyncSession, where: list, blogs: Dict[int, Blog],
                     limit: int) -> List[Dict[str, Any]]:
    """방문 많은 페이지. 옛 글은 crawled_posts 제목으로 보여 준다."""
    pm = PageMetricDaily
    rows = (await db.execute(
        select(pm.blog_id, pm.path, func.max(pm.crawled_post_id),
               func.bool_or(pm.is_autopost), func.sum(pm.sessions),
               func.sum(pm.naver_sessions), func.sum(pm.google_sessions),
               func.sum(pm.avg_duration * pm.sessions))
        .where(*where).group_by(pm.blog_id, pm.path)
        .order_by(func.sum(pm.sessions).desc()).limit(limit))).all()
    ids = [r[2] for r in rows if r[2]]
    titles = dict((await db.execute(text(
        "SELECT id, title FROM crawled_posts WHERE id = ANY(:ids)"),
        {"ids": ids})).all()) if ids else {}
    out = []
    for blog_id, path, post_id, auto, sessions, naver, google, dur in rows:
        blog = blogs.get(blog_id)
        base = (blog.url or "").rstrip("/") if blog else ""
        sessions = int(sessions or 0)
        out.append({
            "blog": blog.name if blog else "", "path": path,
            "url": f"{base}{path}" if base else path,
            "title": titles.get(post_id) or ("첫 화면" if path == "/" else ""),
            "kind": "auto" if auto else ("legacy" if post_id else "page"),
            "sessions": sessions, "naver": int(naver or 0),
            "google": int(google or 0),
            "avg_duration": round(float(dur or 0) / sessions, 1)
            if sessions else 0.0,
        })
    return out
