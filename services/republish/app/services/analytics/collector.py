"""유입 수집 — 하루 한 번, 글마다 어제까지의 성적을 적재한다.

두 소스를 **같은 행**에 합친다. 따로 두면 "노출은 유지되는데 세션이 빠지는"
상태를 볼 수 없고, 그 구분이 재발행 판정의 핵심이다.

GA4 가 연결 안 된 블로그도 GSC 만으로 진행한다. 둘 다 없으면 건너뛴다 —
없는 데이터를 0 으로 적으면 "유입 없는 글" 이 되어 멀쩡한 글이 갈아엎힌다.

계획서: docs/plans/analytics_integration_plan.md §4
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.post_metric import PostMetricDaily
from ...models.search_visibility import SearchVisibilityUrl
from . import ga4_client, gsc_pages
from .url_match import MatchReport, index_by_path, path_of

logger = get_logger("analytics_collector", "app.log")

DEFAULT_DAYS = 28

# 매칭률이 이보다 낮으면 정규화가 틀렸다고 본다. 조용히 넘어가면
# "유입 없는 글" 이 잔뜩 생겨 재발행이 멀쩡한 글을 갈아엎는다.
MATCH_WARN_RATE = 0.5


class AnalyticsCollector:
    """블로그 하나의 유입을 모아 적재한다."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def collect_blog(self, blog: Blog, days: int = DEFAULT_DAYS,
                           ga_token: Optional[str] = None,
                           gsc_token: Optional[str] = None,
                           gsc_site: Optional[str] = None) -> Dict[str, Any]:
        """한 블로그의 최근 지표를 적재한다.

        Args:
            blog: 대상 블로그
            days: 조회 기간(일)
            ga_token/gsc_token: 미리 받아 둔 access token(회차당 1회 발급)
            gsc_site: 이 블로그를 담는 Search Console 속성

        Returns:
            {"rows": 적재 행 수, "ga4": bool, "gsc": bool, "match": {...}}
        """
        urls = await self._urls(blog.id)
        if not urls:
            return {"skipped": "발행 URL 없음", "rows": 0}

        by_path = index_by_path(urls)
        report = MatchReport()
        # (url_id, date) → 지표. 두 소스를 같은 칸에 합친다.
        bucket: Dict[tuple, Dict[str, Any]] = {}

        ga_used = await self._pull_ga4(blog, days, ga_token, by_path, bucket,
                                       report)
        gsc_used = await self._pull_gsc(blog, days, gsc_token, gsc_site,
                                        by_path, bucket, report)

        if not ga_used and not gsc_used:
            return {"skipped": "연결된 소스 없음", "rows": 0}

        rows = await self._upsert(blog.id, bucket)
        await self.db.commit()

        if report.missed and report.rate < MATCH_WARN_RATE:
            logger.warning(
                "[ANALYTICS] URL 매칭률 낮음 | blog=%s | %s%% | 예: %s",
                blog.name, int(report.rate * 100), report.samples)

        logger.info("[ANALYTICS] %s | 행 %d | GA4=%s GSC=%s | 매칭 %s%%",
                    blog.name, rows, ga_used, gsc_used,
                    int(report.rate * 100))
        return {"rows": rows, "ga4": ga_used, "gsc": gsc_used,
                "match": report.to_dict()}

    async def _pull_ga4(self, blog: Blog, days: int, token: Optional[str],
                        by_path: dict, bucket: dict,
                        report: MatchReport) -> bool:
        """GA4 세션. 속성이 없으면 조용히 건너뛴다."""
        cfg = blog.analytics_config or {}
        property_id = str(cfg.get("property_id") or "").strip()
        if not property_id or not token:
            return False
        try:
            rows = await ga4_client.fetch_landing_pages(token, property_id,
                                                        days)
        except ga4_client.Ga4Error as e:
            logger.warning("[ANALYTICS] GA4 실패 | %s | %s", blog.name,
                           e.message)
            return False

        for row in rows:
            target = self._resolve(row.get("path"), by_path, report)
            if target is None:
                continue
            slot = self._slot(bucket, target.id, row.get("date"))
            if slot is None:
                continue
            slot["sessions"] += row.get("sessions") or 0
            slot["engaged_sessions"] += row.get("engaged_sessions") or 0
            # 평균 시간은 합산하면 안 된다 — 큰 쪽을 남긴다
            slot["avg_duration"] = max(slot["avg_duration"],
                                       row.get("avg_duration") or 0.0)
        return True

    async def _pull_gsc(self, blog: Blog, days: int, token: Optional[str],
                        site: Optional[str], by_path: dict, bucket: dict,
                        report: MatchReport) -> bool:
        """서치콘솔 노출·클릭·순위."""
        if not token or not site:
            return False
        rows = await gsc_pages.fetch_pages(token, site, days)
        if not rows:
            return False

        for row in rows:
            target = self._resolve(row.get("url"), by_path, report)
            if target is None:
                continue
            slot = self._slot(bucket, target.id, row.get("date"))
            if slot is None:
                continue
            slot["clicks"] += row.get("clicks") or 0
            slot["impressions"] += row.get("impressions") or 0
            slot["position"] = row.get("position") or 0.0
        return True

    @staticmethod
    def _resolve(raw: Optional[str], by_path: dict, report: MatchReport):
        """URL/경로를 우리 발행 행에 맞춘다."""
        key = path_of(raw or "")
        if not key:
            return None
        found = by_path.get(key)
        if found is None:
            report.miss(key)
            return None
        report.hit()
        return found

    @staticmethod
    def _slot(bucket: dict, url_id: int, raw_date: Optional[str]):
        """(url, 날짜) 칸을 꺼낸다. 날짜가 깨졌으면 버린다."""
        try:
            day = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
        key = (url_id, day)
        if key not in bucket:
            bucket[key] = {"sessions": 0, "engaged_sessions": 0,
                           "avg_duration": 0.0, "clicks": 0,
                           "impressions": 0, "position": 0.0}
        return bucket[key]

    async def _urls(self, blog_id: int) -> List[SearchVisibilityUrl]:
        """이 블로그의 발행 URL. 최신 발행순."""
        result = await self.db.execute(
            select(SearchVisibilityUrl)
            .where(SearchVisibilityUrl.blog_id == blog_id)
            .order_by(SearchVisibilityUrl.published_at.desc().nullslast())
        )
        return list(result.scalars().all())

    async def _upsert(self, blog_id: int, bucket: dict) -> int:
        """(url, 날짜) 단위로 덮어쓴다.

        같은 날을 다시 수집하면 값이 갱신돼야 한다. GA4·GSC 모두 최근
        며칠치를 나중에 보정하므로, 처음 받은 값을 고집하면 틀린 채로 남는다.
        """
        if not bucket:
            return 0
        url_ids = {key[0] for key in bucket}
        days = {key[1] for key in bucket}
        existing = {
            (row.url_id, row.date): row
            for row in (await self.db.execute(
                select(PostMetricDaily).where(
                    PostMetricDaily.url_id.in_(url_ids),
                    PostMetricDaily.date.in_(days))
            )).scalars().all()
        }

        for (url_id, day), values in bucket.items():
            row = existing.get((url_id, day))
            if row is None:
                row = PostMetricDaily(url_id=url_id, blog_id=blog_id, date=day)
                self.db.add(row)
            for field, value in values.items():
                setattr(row, field, value)
        return len(bucket)


async def collect_all(db: AsyncSession, days: int = DEFAULT_DAYS
                      ) -> Dict[str, Any]:
    """활성 블로그 전부. 하루 한 번 도는 진입점.

    토큰은 회차당 한 번만 발급한다. 블로그마다 발급하면 13번 갱신 호출이
    붙는다.
    """
    from ..search_visibility import index_check_service as ics
    from ..search_visibility.runner import resolve_gsc_token

    blogs = list((await db.execute(
        select(Blog).where(Blog.is_active.is_(True),
                           Blog.is_deleted.is_(False))
        .order_by(Blog.id)
    )).scalars().all())
    if not blogs:
        return {"blogs": 0, "rows": 0}

    ga_token = await ga4_client.resolve_token(db)
    gsc_token = await resolve_gsc_token(db)
    sites: List[str] = []
    if gsc_token:
        try:
            sites = await ics.list_sites(gsc_token)
        except ics.IndexCheckError as e:
            logger.warning("[ANALYTICS] 서치콘솔 속성 목록 실패 | %s", e.message)

    collector = AnalyticsCollector(db)
    total, details = 0, []
    for blog in blogs:
        site = ics.resolve_property(sites, blog) if sites else None
        try:
            out = await collector.collect_blog(
                blog, days=days, ga_token=ga_token, gsc_token=gsc_token,
                gsc_site=site)
        except Exception as e:  # noqa: BLE001 — 한 블로그가 회차를 멈추면 안 된다
            logger.error("[ANALYTICS] 수집 오류 | %s | %s", blog.name, e)
            out = {"error": str(e)[:200], "rows": 0}
        total += out.get("rows") or 0
        details.append({"blog": blog.name, **out})

    logger.info("[ANALYTICS] 회차 완료 | 블로그 %d | 행 %d", len(blogs), total)
    return {"blogs": len(blogs), "rows": total, "details": details,
            "collected_at": date.today().isoformat()}
