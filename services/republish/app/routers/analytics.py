"""유입 분석 API — 연결·수집·조회.

발행한 글이 실제로 읽히는지 회수한다. 서치콘솔(보였나)과 GA4(들어왔나)를
같은 행에 합쳐, 재발행이 글마다 다른 판단을 할 수 있게 한다.

계획서: docs/plans/analytics_integration_plan.md
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.post_metric import PostMetricDaily
from ..models.search_visibility import SearchVisibilityUrl
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.analytics import ga4_client

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = get_logger("analytics_api", "app.log")


class TokenRequest(BaseModel):
    """GA4 refresh token 저장."""

    refresh_token: str = ""


class PropertyRequest(BaseModel):
    """블로그 ↔ GA4 속성 연결. 속성은 블로그마다 따로다."""

    blog_id: int
    property_id: str = ""
    display_name: str = ""


@router.post("/account")
async def save_account(
    request: TokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """GA4 refresh token 저장. 서치콘솔과 **같은 방식**이다.

    필요 범위: https://www.googleapis.com/auth/analytics.readonly
    """
    from ..core.encryption import encrypt_api_key
    from ..services.system_settings_service import SystemSettingsService

    token = (request.refresh_token or "").strip()
    existing = await SystemSettingsService.get(
        ga4_client.SETTING_GA4_REFRESH_TOKEN, db)

    # 화면이 마스킹된 값을 되돌려 보내면 덮어쓰지 않는다
    if token and "****" not in token:
        await SystemSettingsService.set(
            ga4_client.SETTING_GA4_REFRESH_TOKEN, encrypt_api_key(token), db)
    elif not existing:
        raise HTTPException(status_code=422, detail="refresh token을 입력하세요")
    await db.commit()

    logger.info("[ANALYTICS] GA4 refresh token 저장")
    stored = await SystemSettingsService.get(
        ga4_client.SETTING_GA4_REFRESH_TOKEN, db)
    return {"success": True, "configured": bool(stored)}


@router.get("/properties")
async def list_properties(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """볼 수 있는 GA4 속성과 블로그 연결 현황."""
    token = await ga4_client.resolve_token(db)
    if not token:
        return {"connected": False,
                "error": "refresh token이 저장되지 않았거나 만료되었습니다"}
    try:
        properties = await ga4_client.list_properties(token)
    except ga4_client.Ga4Error as e:
        result = {"connected": False, "error": e.message}
        if e.status_code == 403:
            # 권한 부족은 대개 다른 용도의 토큰을 넣은 경우다
            result["granted_scopes"] = await ga4_client.granted_scopes(token)
            result["required_scope"] = ga4_client.REQUIRED_SCOPE
        return result

    blogs = list((await db.execute(
        select(Blog).where(Blog.is_deleted.is_(False)).order_by(Blog.id)
    )).scalars().all())
    return {
        "connected": True,
        "properties": properties,
        "blogs": [{
            "id": b.id, "name": b.name,
            "property_id": (b.analytics_config or {}).get("property_id") or "",
        } for b in blogs],
    }


@router.put("/properties")
async def link_property(
    request: PropertyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그에 GA4 속성을 연결한다. 빈 값이면 연결 해제."""
    blog = await db.get(Blog, request.blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    pid = (request.property_id or "").strip()
    blog.analytics_config = ({"property_id": pid,
                              "display_name": request.display_name or ""}
                             if pid else None)
    await db.commit()
    logger.info("[ANALYTICS] 속성 연결 | blog=%s | property=%s",
                blog.name, pid or "(해제)")
    return {"success": True, "blog_id": blog.id, "property_id": pid}


@router.post("/collect")
async def collect(
    days: int = Query(default=28, ge=1, le=90),
    blog_id: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """유입을 지금 수집한다. 자동 수집과 **같은 코드**를 탄다."""
    from ..services.analytics.collector import AnalyticsCollector, collect_all

    if blog_id is None:
        return await collect_all(db, days=days)

    blog = await db.get(Blog, blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    from ..services.search_visibility import index_check_service as ics
    from ..services.search_visibility.runner import resolve_gsc_token

    ga_token = await ga4_client.resolve_token(db)
    gsc_token = await resolve_gsc_token(db)
    site = None
    if gsc_token:
        try:
            site = ics.resolve_property(await ics.list_sites(gsc_token), blog)
        except ics.IndexCheckError:
            site = None
    return await AnalyticsCollector(db).collect_blog(
        blog, days=days, ga_token=ga_token, gsc_token=gsc_token,
        gsc_site=site)


@router.get("/summary")
async def summary(
    blog_id: Optional[int] = Query(default=None),
    days: int = Query(default=28, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """대시보드용 요약 — 기간 합계와 일별 추이.

    수집 이력이 없는 구간은 0 이 아니라 **빠진 날**로 둔다. 0 으로 그리면
    도입 전 기간이 전부 폭락처럼 보인다.
    """
    since = date.today() - timedelta(days=days)
    where = [PostMetricDaily.date >= since]
    if blog_id:
        where.append(PostMetricDaily.blog_id == blog_id)

    totals = (await db.execute(
        select(func.coalesce(func.sum(PostMetricDaily.sessions), 0),
               func.coalesce(func.sum(PostMetricDaily.clicks), 0),
               func.coalesce(func.sum(PostMetricDaily.impressions), 0),
               func.count(func.distinct(PostMetricDaily.url_id)))
        .where(*where)
    )).first() or (0, 0, 0, 0)

    trend = [{
        "date": row[0].isoformat() if hasattr(row[0], "isoformat")
                else str(row[0]),
        "sessions": int(row[1] or 0), "clicks": int(row[2] or 0),
        "impressions": int(row[3] or 0),
    } for row in (await db.execute(
        select(PostMetricDaily.date,
               func.sum(PostMetricDaily.sessions),
               func.sum(PostMetricDaily.clicks),
               func.sum(PostMetricDaily.impressions))
        .where(*where).group_by(PostMetricDaily.date)
        .order_by(PostMetricDaily.date)
    )).all()]

    return {
        "days": days,
        "sessions": int(totals[0] or 0), "clicks": int(totals[1] or 0),
        "impressions": int(totals[2] or 0), "posts": int(totals[3] or 0),
        "trend": trend,
    }


@router.get("/posts")
async def posts(
    blog_id: Optional[int] = Query(default=None),
    days: int = Query(default=28, ge=1, le=180),
    limit: int = Query(default=30, ge=1, le=200),
    order: str = Query(default="sessions", pattern="^(sessions|impressions)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """글별 성적. 재발행 판정과 **같은 기준**으로 동작까지 함께 준다."""
    from ..services.analytics.performance import (
        Performance, decide_action, summarize,
    )

    since = date.today() - timedelta(days=days)
    prev_since = since - timedelta(days=days)
    where = [PostMetricDaily.date >= since]
    if blog_id:
        where.append(PostMetricDaily.blog_id == blog_id)

    rows = (await db.execute(
        select(PostMetricDaily.url_id,
               func.sum(PostMetricDaily.sessions),
               func.sum(PostMetricDaily.clicks),
               func.sum(PostMetricDaily.impressions),
               func.avg(PostMetricDaily.position),
               func.count(PostMetricDaily.id))
        .where(*where).group_by(PostMetricDaily.url_id)
        .order_by(func.sum(
            PostMetricDaily.sessions if order == "sessions"
            else PostMetricDaily.impressions).desc())
        .limit(limit)
    )).all()
    if not rows:
        return {"items": [], "summary": {}}

    url_ids = [r[0] for r in rows]
    prev = {
        r[0]: int(r[1] or 0) for r in (await db.execute(
            select(PostMetricDaily.url_id, func.sum(PostMetricDaily.sessions))
            .where(PostMetricDaily.url_id.in_(url_ids),
                   PostMetricDaily.date >= prev_since,
                   PostMetricDaily.date < since)
            .group_by(PostMetricDaily.url_id)
        )).all()
    }
    urls = {
        u.id: u for u in (await db.execute(
            select(SearchVisibilityUrl)
            .where(SearchVisibilityUrl.id.in_(url_ids))
        )).scalars().all()
    }

    items, perfs = [], []
    for url_id, sessions, clicks, impressions, position, day_count in rows:
        perf = decide_action(Performance(
            url_id=url_id, sessions=int(sessions or 0),
            prev_sessions=prev.get(url_id, 0),
            clicks=int(clicks or 0), impressions=int(impressions or 0),
            position=round(float(position or 0.0), 1),
            days=int(day_count or 0)))
        perfs.append(perf)
        row = urls.get(url_id)
        items.append({
            **perf.to_dict(),
            "title": getattr(row, "title", "") or "",
            "url": getattr(row, "url", "") or "",
        })
    return {"items": items, "summary": summarize(perfs)}
