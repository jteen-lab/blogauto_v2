"""문의 수신함 API (F10 대시보드).

Tally 폼 제출을 blogauto 대시보드에서 조회/동기화/읽음처리.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.contact_submission import ContactSubmission
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.publishing.contact_inbox_service import sync_all

router = APIRouter(prefix="/contact-submissions", tags=["문의 수신함"])
logger = get_logger("contact_submissions", "app.log")


@router.get("")
async def list_submissions(
    blog_id: Optional[int] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """문의 목록 조회(최신순). blog_id·미읽음 필터."""
    stmt = select(ContactSubmission, Blog.name).join(
        Blog, ContactSubmission.blog_id == Blog.id, isouter=True,
    )
    if blog_id is not None:
        stmt = stmt.where(ContactSubmission.blog_id == blog_id)
    if unread_only:
        stmt = stmt.where(ContactSubmission.is_read.is_(False))
    stmt = stmt.order_by(desc(ContactSubmission.submitted_at)).limit(min(limit, 200)).offset(offset)
    rows = (await db.execute(stmt)).all()

    items = [{
        "id": s.id,
        "blog_id": s.blog_id,
        "blog_name": blog_name or "-",
        "form_name": s.form_name,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        "fields": s.fields or [],
        "is_read": s.is_read,
    } for s, blog_name in rows]

    unread = (await db.execute(
        select(func.count(ContactSubmission.id)).where(ContactSubmission.is_read.is_(False))
    )).scalar() or 0
    return {"items": items, "unread_count": unread}


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """미읽음 문의 수(뱃지용)."""
    cnt = (await db.execute(
        select(func.count(ContactSubmission.id)).where(ContactSubmission.is_read.is_(False))
    )).scalar() or 0
    return {"unread_count": cnt}


@router.post("/sync")
async def sync_submissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Tally에서 새 문의를 가져와 저장(폴링)."""
    return await sync_all(db)


@router.post("/{submission_id}/read")
async def mark_read(
    submission_id: int,
    is_read: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """문의 읽음/안읽음 처리."""
    sub = await db.get(ContactSubmission, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")
    sub.is_read = is_read
    await db.commit()
    return {"success": True, "is_read": sub.is_read}
