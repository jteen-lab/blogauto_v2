"""홍보 링크 API.

글에 붙일 버튼 주소를 목록으로 관리한다. CPA 오퍼의 확인 절차를 밟지
않고도 바로 쓸 수 있는 가벼운 길이다.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models import PromoLink, User
from ..models.promo_link import DEFAULT_NOTICE
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/promo-links", tags=["홍보 링크"])


class LinkIn(BaseModel):
    """새 링크 입력."""

    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=4, max_length=500)
    button_text: str = Field(..., min_length=1, max_length=200)
    notice: Optional[str] = Field(DEFAULT_NOTICE, max_length=300)
    keywords: Optional[str] = Field(
        None, max_length=500,
        description="이 링크를 쓸 키워드 조합. 예: 이사+견적, 이사+비용")
    blog_id: Optional[int] = None
    cpa_offer_id: Optional[int] = None


class LinkPatch(BaseModel):
    """고칠 값만 보낸다."""

    name: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=500)
    button_text: Optional[str] = Field(None, max_length=200)
    notice: Optional[str] = Field(None, max_length=300)
    keywords: Optional[str] = Field(None, max_length=500)
    blog_id: Optional[int] = None
    cpa_offer_id: Optional[int] = None
    is_active: Optional[bool] = None


#: 비우면 "없음"으로 치는 칸 — 빈 문자열은 None 으로 바꿔 넣는다
_EMPTY_IS_NONE = ("notice", "keywords")

#: 비울 수 없는 칸 — 공백만 보내면 거절한다
_REQUIRED = ("name", "url", "button_text")


async def _get(db: AsyncSession, link_id: int) -> PromoLink:
    """없으면 404."""
    link = await db.get(PromoLink, link_id)
    if link is None:
        raise HTTPException(404, "링크를 찾을 수 없습니다")
    return link


def _clean(field: str, value: object) -> object:
    """넣기 전에 다듬는다.

    화면에서 칸을 지우면 빈 문자열이 온다. 키워드를 지운 링크는
    자동 선택에서 빠져야 하는데, 빈 문자열이 그대로 들어가면 "없음"
    으로 읽히지 않는다.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if field in _REQUIRED and not text:
        raise HTTPException(400, "이름·주소·버튼 문구는 비울 수 없습니다")
    if field in _EMPTY_IS_NONE and not text:
        return None
    return text


@router.get("", summary="링크 목록")
async def list_links(
    blog_id: Optional[int] = Query(None, description="이 블로그가 쓸 수 있는 것만"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """등록된 링크. blog_id 를 주면 공용 + 그 블로그 전용만 나온다."""
    stmt = select(PromoLink).where(PromoLink.is_active.is_(True))
    if blog_id is not None:
        stmt = stmt.where(
            (PromoLink.blog_id.is_(None)) | (PromoLink.blog_id == blog_id))
    rows = (await db.execute(stmt.order_by(PromoLink.id.desc()))).scalars().all()
    return {"success": True, "items": [r.to_dict() for r in rows]}


@router.post("", summary="링크 등록")
async def create_link(
    payload: LinkIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """새 링크 하나. 등록하면 바로 글에 붙일 수 있다."""
    link = PromoLink(
        name=payload.name.strip(), url=payload.url.strip(),
        button_text=payload.button_text.strip(),
        notice=(payload.notice or "").strip() or None,
        keywords=(payload.keywords or "").strip() or None,
        blog_id=payload.blog_id, cpa_offer_id=payload.cpa_offer_id)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    logger.info("[PROMO_LINK] 등록 | id=%s | %s", link.id, link.name)
    return {"success": True, "link": link.to_dict()}


@router.patch("/{link_id}", summary="링크 수정")
async def update_link(
    link_id: int,
    payload: LinkPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """보낸 값만 바꾼다. 안 보낸 칸은 그대로 둔다."""
    link = await _get(db, link_id)
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(link, field, _clean(field, value))
    await db.commit()
    await db.refresh(link)
    logger.info("[PROMO_LINK] 수정 | id=%s | %s", link_id,
                ", ".join(changed.keys()) or "없음")
    return {"success": True, "link": link.to_dict()}


@router.delete("/{link_id}", summary="링크 삭제")
async def delete_link(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """목록에서 뺀다. 이미 쓴 글은 그대로 남는다."""
    link = await _get(db, link_id)
    link.is_active = False
    await db.commit()
    return {"success": True, "message": "목록에서 뺐습니다"}
