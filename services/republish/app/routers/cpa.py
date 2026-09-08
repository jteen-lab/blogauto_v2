"""CPA 오퍼 API.

오퍼는 프로모션 하나의 규칙 묶음이다. 확인되지 않은 오퍼로 글을 만들면
규정 위반이 되므로, **확인 전에는 쓰지 못하게** 상태로 막는다.

순서도: docs/flowcharts/cpa_offer.md
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.cpa_offer import (
    CpaOffer, DEFAULT_RECHECK_DAYS, ST_ACTIVE, ST_DRAFT, ST_RECHECK,
    ST_STOPPED, default_recheck,
)
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.cpa.offer_parser import parse

router = APIRouter(prefix="/cpa", tags=["cpa"])
logger = get_logger("cpa_api", "app.log")


class OfferIn(BaseModel):
    """오퍼 등록 — 원문을 가공 없이 그대로 받는다."""

    raw_text: str = Field(..., min_length=20)
    network: str = "adlix"
    offer_code: Optional[str] = None
    landing_url: Optional[str] = None
    vertical: Optional[str] = None
    recheck_days: int = Field(default=DEFAULT_RECHECK_DAYS, ge=1, le=365)


class OfferPatch(BaseModel):
    """확인 화면에서 고치는 값."""

    name: Optional[str] = None
    advertiser: Optional[str] = None
    vertical: Optional[str] = None
    landing_url: Optional[str] = None
    subid_param: Optional[str] = None
    ftc_notice: Optional[str] = None
    conversion: Optional[dict] = None
    note: Optional[str] = None


@router.get("/offers")
async def list_offers(
    status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """오퍼 목록. 기한이 지난 것은 조회 시점에 recheck 로 바꾼다."""
    where = [CpaOffer.is_deleted.is_(False)]
    if status:
        where.append(CpaOffer.status == status)

    rows = (await db.execute(
        select(CpaOffer).where(*where).order_by(CpaOffer.id.desc())
    )).scalars().all()

    changed = 0
    for row in rows:
        if row.status == ST_ACTIVE and row.overdue:
            row.status = ST_RECHECK
            changed += 1
    if changed:
        await db.commit()
        logger.info("[CPA] 재확인 기한 경과 %d건 — 글 생성 중단", changed)

    return {
        "items": [r.to_dict() for r in rows],
        "counts": {
            "draft": sum(1 for r in rows if r.status == ST_DRAFT),
            "active": sum(1 for r in rows if r.status == ST_ACTIVE),
            "recheck": sum(1 for r in rows if r.status == ST_RECHECK),
            "stopped": sum(1 for r in rows if r.status == ST_STOPPED),
        },
    }


@router.post("/offers")
async def create_offer(
    payload: OfferIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """원문을 저장하고 고정 서식을 뽑는다.

    자유 서술의 규칙 추출은 아직 하지 않는다(P2). 그때까지는 규칙 0건이므로
    **확인해도 검사가 거의 없다**는 뜻이다. 화면이 그 사실을 밝힌다.
    """
    found = parse(payload.raw_text)

    offer = CpaOffer(
        network=payload.network,
        offer_code=payload.offer_code,
        name=found["name"],
        vertical=payload.vertical,
        raw_text=payload.raw_text,
        conversion=found["conversion"],
        ftc_notice=found["ftc_notice"],
        rules=[], unmatched=[], conflicts=[],
        landing_url=payload.landing_url,
        status=ST_DRAFT,
        recheck_due=default_recheck(payload.recheck_days),
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    logger.info("[CPA] 오퍼 등록 | %s | 추출 %s", offer.name, found["found"])
    return {"success": True, "offer": offer.to_dict(),
            "found": found["found"],
            "notice_position": found["notice_position"]}


@router.post("/offers/{offer_id}/reparse")
async def reparse_offer(
    offer_id: int,
    payload: Optional[OfferIn] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """원문을 다시 붙여넣어 갱신한다. 조건이 바뀌었을 때 쓴다.

    갱신하면 **확인 전 상태로 되돌린다.** 바뀐 내용을 사람이 다시 봐야 한다.
    """
    offer = await _get(db, offer_id)
    if payload and payload.raw_text:
        offer.raw_text = payload.raw_text
        offer.recheck_due = default_recheck(payload.recheck_days)

    found = parse(offer.raw_text)
    offer.name = found["name"]
    offer.conversion = found["conversion"]
    offer.ftc_notice = found["ftc_notice"]
    offer.status = ST_DRAFT
    offer.confirmed_at = None
    await db.commit()
    await db.refresh(offer)

    logger.info("[CPA] 오퍼 재해석 | %s | 확인 전으로 되돌림", offer.name)
    return {"success": True, "offer": offer.to_dict(),
            "found": found["found"]}


@router.patch("/offers/{offer_id}")
async def update_offer(
    offer_id: int,
    payload: OfferPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """확인 화면에서 고친 값을 저장한다."""
    offer = await _get(db, offer_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(offer, field, value)
    await db.commit()
    await db.refresh(offer)
    return {"success": True, "offer": offer.to_dict()}


@router.post("/offers/{offer_id}/confirm")
async def confirm_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """사람이 확인했다. 이제 이 오퍼로 글을 만들 수 있다.

    오퍼당 한 번이면 된다. 대신 이 한 번을 건너뛰면 그 오퍼로 만든 글
    **전부가** 위반이 될 수 있다.
    """
    offer = await _get(db, offer_id)
    if not offer.ftc_notice:
        raise HTTPException(
            status_code=400,
            detail="공정거래위원회 대가성 문구가 비어 있습니다. "
                   "표시하지 않으면 위법입니다.")
    if offer.overdue:
        raise HTTPException(status_code=400,
                            detail="재확인 기한이 지났습니다. 원문을 다시 붙여넣으세요.")

    offer.status = ST_ACTIVE
    offer.confirmed_at = datetime.now()
    await db.commit()
    await db.refresh(offer)
    logger.info("[CPA] 오퍼 확인 완료 | %s", offer.name)
    return {"success": True, "offer": offer.to_dict()}


@router.post("/offers/{offer_id}/stop")
async def stop_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """중단. 지우지 않는다 — 이미 발행한 글의 근거가 남아야 한다."""
    offer = await _get(db, offer_id)
    offer.status = ST_STOPPED
    await db.commit()
    return {"success": True, "offer": offer.to_dict()}


@router.get("/offers/{offer_id}")
async def get_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """오퍼 하나. 원문까지 함께 준다 — 확인 화면이 대조해야 한다."""
    offer = await _get(db, offer_id)
    return {"offer": offer.to_dict(), "raw_text": offer.raw_text}


async def _get(db: AsyncSession, offer_id: int) -> CpaOffer:
    offer = await db.get(CpaOffer, offer_id)
    if not offer or offer.is_deleted:
        raise HTTPException(status_code=404, detail="오퍼를 찾을 수 없습니다")
    return offer
