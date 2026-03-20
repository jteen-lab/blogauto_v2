"""
생성 이력 페이지 라우터

생성된 콘텐츠 목록/상세 조회 페이지를 제공합니다.
설계 문서: generation_content_storage_plan.md - Phase 3
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.user import User
from ..models.blog import Blog
from ..models.crawled_post import CrawledPost
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("generation_pages", "app.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["생성 이력 페이지"])


@router.get("/generation/history", response_class=HTMLResponse)
async def generation_history_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """생성 이력 페이지"""
    # 블로그 목록 (필터용)
    blog_result = await db.execute(
        select(Blog.id, Blog.name)
        .where(Blog.user_id == current_user.id)
        .order_by(Blog.name)
    )
    blogs = [{"id": row.id, "name": row.name} for row in blog_result.fetchall()]

    # 통계
    stats_result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(
                CrawledPost.content_html.isnot(None)
            ).label("with_content"),
            func.count().filter(
                CrawledPost.image_url.isnot(None)
            ).label("with_image"),
            func.count().filter(
                CrawledPost.published_at.isnot(None)
            ).label("published"),
        )
        .where(CrawledPost.source == "generated")
    )
    stats_row = stats_result.one()

    stats = {
        "total": stats_row.total,
        "with_content": stats_row.with_content,
        "with_image": stats_row.with_image,
        "published": stats_row.published,
    }

    return templates.TemplateResponse(
        "generation/history.html",
        {
            "request": request,
            "user": current_user,
            "blogs": blogs,
            "stats": stats,
        }
    )
