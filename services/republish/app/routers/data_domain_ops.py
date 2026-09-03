"""도메인 정리 API — 대량삭제 팝업과 차단.

`data_domains.py` 가 목록·토글을 맡고, 여기는 **정리 흐름**을 맡는다.
파일을 나눈 이유는 500줄 규칙과, 두 관심사가 다르기 때문이다.

계획서: docs/plans/title_tab_workplan.md §2-3
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.title_collect import domain_ops

router = APIRouter(prefix="/data/domains", tags=["data-domains"])
logger = get_logger("data_domain_ops", "app.log")


class PurgeRequest(BaseModel):
    """도메인 통째 정리."""

    domain: str
    # 제목만 지울지, 재수집까지 막을지. 제목만 정리하고 도메인은 살려
    # 두고 싶은 경우가 있다.
    block: bool = True


class DeleteTitlesRequest(BaseModel):
    ids: List[int]


@router.get("/{domain_id}/titles")
async def domain_titles(
    domain_id: int,
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """팝업에 뿌릴 남은 제목 전체.

    페이지를 넘기지 않고 한 화면에서 고를 수 있어야 이 기능을 만든 의미가
    있다. 그래서 기본 500건까지 한 번에 준다.
    """
    from sqlalchemy import select

    from ..models.niche_domain import NicheDomain

    row = (await db.execute(
        select(NicheDomain).where(NicheDomain.id == domain_id,
                                  NicheDomain.user_id == current_user.id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="도메인을 찾을 수 없습니다")

    titles = await domain_ops.list_titles(db, row.domain, limit)
    return {"domain": row.domain, "deleted_count": row.deleted_title_count,
            "is_blocked": row.is_blocked, "total": len(titles),
            "items": titles}


@router.post("/titles/delete")
async def delete_domain_titles(
    payload: DeleteTitlesRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """팝업에서 고른 제목만 삭제."""
    removed = await domain_ops.delete_titles(db, payload.ids)
    return {"success": True, "deleted": removed}


@router.post("/purge")
async def purge(
    payload: PurgeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """도메인의 제목을 모두 지우고, 원하면 재수집을 차단한다."""
    result = await domain_ops.purge_domain(
        db, current_user.id, payload.domain, payload.block)
    logger.info("[DOMAIN_OPS] purge %s | user=%s | %s",
                payload.domain, current_user.id, result)
    return {"success": True, **result}


@router.post("/{domain_id}/unblock")
async def unblock_domain(
    domain_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """차단 해제. 다시 수집·추출 대상이 된다."""
    row = await domain_ops.unblock(db, current_user.id, domain_id)
    if row is None:
        raise HTTPException(status_code=404, detail="도메인을 찾을 수 없습니다")
    return {"success": True, "domain": row.domain, "is_blocked": False}
