"""발행글 정리 API — 미리보기 후 비공개/완전삭제.

순서도: docs/flowcharts/post_cleanup.md
"""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.publishing.post_cleanup_service import (
    CATEGORIES,
    DEFAULT_MIN_REMAINING,
    MODE_DELETE,
    MODE_PRIVATE,
    PostCleanupService,
    build_plan,
)

logger = get_logger("post_cleanup_api", "app.log")

router = APIRouter(prefix="/api/v1/blogs", tags=["발행글 정리"])


async def _get_blog(blog_id: int, user: User, db: AsyncSession):
    from sqlalchemy import select

    from ..models.blog import Blog

    blog = (await db.execute(
        select(Blog).where(
            Blog.id == blog_id, Blog.user_id == user.id,
            Blog.is_deleted == False,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not blog:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")
    return blog


def _min_remaining(blog, requested: Optional[int]) -> int:
    """잔존 하한. 승인 블로그는 낮춰도 기본값 아래로 내리지 않는다.

    승인 사이트에서 콘텐츠가 부족해지면 광고 게재가 중단될 수 있다.
    """
    approved = (getattr(blog, "adsense_status", None) == "approved")
    if requested is None:
        return DEFAULT_MIN_REMAINING if approved else 0
    if approved:
        return max(int(requested), DEFAULT_MIN_REMAINING)
    return max(0, int(requested))


@router.get("/{blog_id}/cleanup/preview")
async def preview_cleanup(
    blog_id: int,
    categories: Optional[str] = Query(
        default=None, description="쉼표 구분. 미지정이면 전체 유형"),
    min_body_len: int = Query(default=0, description="이 글자수 미만도 대상"),
    min_remaining: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """무엇이 왜 지워지는지 먼저 보여준다. 여기서는 아무것도 바꾸지 않는다."""
    blog = await _get_blog(blog_id, current_user, db)
    svc = PostCleanupService(blog)
    posts = await svc.fetch_posts()

    plan = build_plan(
        posts,
        categories=[c.strip() for c in categories.split(",")] if categories else None,
        min_body_len=min_body_len,
        min_remaining=_min_remaining(blog, min_remaining),
    )
    return {
        "blog": {"id": blog.id, "name": blog.name,
                 "adsense_status": blog.adsense_status},
        "categories": [{"code": c, "label": l} for c, l, _ in CATEGORIES],
        **plan.to_dict(),
    }


@router.post("/{blog_id}/cleanup/apply")
async def apply_cleanup(
    blog_id: int,
    mode: str = Query(default=MODE_PRIVATE),
    post_ids: List[str] = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """선택한 글을 비공개하거나 완전 삭제한다.

    완전삭제는 되돌릴 수 없다. 미리보기에서 확인한 목록만 넘기는 것을 전제한다.
    """
    if mode not in (MODE_PRIVATE, MODE_DELETE):
        raise HTTPException(422, "mode 는 private 또는 delete 여야 합니다")
    if not post_ids:
        raise HTTPException(422, "대상이 비어 있습니다")

    blog = await _get_blog(blog_id, current_user, db)
    svc = PostCleanupService(blog)

    # 하한 재검사 — 미리보기 이후 상황이 바뀌었을 수 있고,
    # API 를 직접 호출해 우회하는 것도 막는다.
    posts = await svc.fetch_posts()
    floor = _min_remaining(blog, None)
    remaining = len(posts) - len(set(post_ids))
    if remaining < floor:
        raise HTTPException(
            422,
            f"{len(post_ids)}개를 지우면 {remaining}개만 남습니다. "
            f"이 블로그는 최소 {floor}개를 유지해야 합니다",
        )

    wanted = set(post_ids)
    targets = [p for p in posts if p.post_id in wanted]
    result = await svc.apply(targets, mode=mode)

    from ..services.blog_service import add_action_log

    label = "완전삭제" if mode == MODE_DELETE else "비공개"
    await add_action_log(
        db, "SUCCESS" if not result.get("failed") else "WARNING",
        f"발행글 {label}: {blog.name} — {result['done']}건 처리"
        + (f" / 실패 {len(result['failed'])}건" if result.get("failed") else ""),
        category="cleanup", resource_type="blog", resource_id=blog.id,
    )
    return {"success": True, "mode": mode, **result}
