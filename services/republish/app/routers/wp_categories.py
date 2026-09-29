"""WordPress 카테고리·메뉴 동기화 API.

순서도: docs/flowcharts/wp_category_sync.md
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/blogs", tags=["WP 카테고리 동기화"])


@router.post("/{blog_id}/wp/categories/sync")
async def sync_wp_categories(
    blog_id: int,
    dry_run: bool = Query(default=False, description="true 면 조회만(생성·저장 안 함)"),
    with_menu: bool = Query(default=True, description="메뉴 보장까지 실행"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """활성 블로그 카테고리 → WP 카테고리 생성/매핑 → (선택) 메뉴 보장."""
    from sqlalchemy import select

    from ..models.blog import Blog
    from ..services.publishing.wp_category_sync import sync_categories
    from ..services.publishing.wp_menu_sync import ensure_menu, names_from_sync

    blog = (await db.execute(
        select(Blog).where(
            Blog.id == blog_id, Blog.user_id == current_user.id,
            Blog.is_deleted == False,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not blog:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")
    if "wordpress" not in str(getattr(blog.platform, "value", blog.platform)).lower():
        raise HTTPException(400, "WordPress 블로그만 지원합니다")

    categories = await sync_categories(blog, db, apply=not dry_run)
    menu = None
    if with_menu and not dry_run:
        menu = await ensure_menu(blog, names_from_sync(categories))
    return {"blog_id": blog_id, "dry_run": dry_run, "categories": categories, "menu": menu}
