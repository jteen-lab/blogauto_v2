"""대시보드 v2 트렌드/통계 API (trends, blog_stats, hourly)."""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.autorun_log import AutorunLog
from ..models.blog import Blog
from ..models.crawled_post import CrawledPost
from ..models.generation_history import GenerationHistory

logger = get_logger("dashboard_trends", "dashboard.log")
router = APIRouter(prefix="/dashboard", tags=["대시보드 트렌드"])
_EMPTY = {"dates": [], "generated": [], "published": [], "republished": []}


@router.get("/trends")
async def get_trends(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """시계열 트렌드 데이터 (차트용). dates/generated/published/republished 배열 반환."""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # 일별 생성 건수
        gen_q = (
            select(func.date(GenerationHistory.created_at).label("d"), func.count().label("cnt"))
            .where(GenerationHistory.created_at >= since)
            .group_by(func.date(GenerationHistory.created_at))
        )
        gen_map = {str(r.d): r.cnt for r in (await db.execute(gen_q)).all()}

        # 일별 발행 건수 (generated + published_at 존재)
        pub_q = (
            select(func.date(CrawledPost.published_at).label("d"), func.count().label("cnt"))
            .where(CrawledPost.source == "generated",
                   CrawledPost.published_at.isnot(None),
                   CrawledPost.published_at >= since)
            .group_by(func.date(CrawledPost.published_at))
        )
        pub_map = {str(r.d): r.cnt for r in (await db.execute(pub_q)).all()}

        # 일별 재발행 건수
        rep_q = (
            select(func.date(AutorunLog.created_at).label("d"), func.count().label("cnt"))
            .where(AutorunLog.action == "republish",
                   AutorunLog.status == "success",
                   AutorunLog.created_at >= since)
            .group_by(func.date(AutorunLog.created_at))
        )
        rep_map = {str(r.d): r.cnt for r in (await db.execute(rep_q)).all()}

        # 날짜 배열 조립
        dates, generated, published, republished = [], [], [], []
        for i in range(days):
            d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            dates.append(d)
            generated.append(gen_map.get(d, 0))
            published.append(pub_map.get(d, 0))
            republished.append(rep_map.get(d, 0))

        return {"dates": dates, "generated": generated,
                "published": published, "republished": republished}
    except Exception as e:
        logger.error(f"트렌드 데이터 조회 실패: {e}")
        return _EMPTY


@router.get("/blog_stats")
async def get_blog_stats(
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """블로그별 생성 통계 (7일간, 상위 6개). success_rate는 content_html 존재 비율."""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        q = (
            select(
                GenerationHistory.blog_id,
                Blog.name.label("blog_name"),
                Blog.platform.label("platform"),
                func.count().label("total"),
                func.count(GenerationHistory.content_html).label("success"),
            )
            .join(Blog, Blog.id == GenerationHistory.blog_id)
            .where(GenerationHistory.created_at >= since)
            .group_by(GenerationHistory.blog_id, Blog.name, Blog.platform)
            .order_by(func.count().desc())
            .limit(6)
        )
        rows = (await db.execute(q)).all()
        return [
            {
                "blog_name": r.blog_name, "blog_id": r.blog_id,
                "platform": (
                    r.platform.value if hasattr(r.platform, 'value')
                    else str(r.platform)
                ),
                "count": r.total,
                "success_rate": round(r.success / r.total * 100, 1) if r.total else 0.0,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"블로그 통계 조회 실패: {e}")
        return []


@router.get("/hourly")
async def get_hourly_distribution(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, list[int]]:
    """시간대별 생성 분포 (7일간). hours(0~23)와 counts 배열 반환."""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        q = (
            select(
                extract("hour", GenerationHistory.created_at).label("h"),
                func.count().label("cnt"),
            )
            .where(GenerationHistory.created_at >= since)
            .group_by(extract("hour", GenerationHistory.created_at))
        )
        hour_map = {int(r.h): r.cnt for r in (await db.execute(q)).all()}
        return {"hours": list(range(24)),
                "counts": [hour_map.get(h, 0) for h in range(24)]}
    except Exception as e:
        logger.error(f"시간대별 분포 조회 실패: {e}")
        return {"hours": list(range(24)), "counts": [0] * 24}
