"""CPA 오퍼 API.

오퍼는 프로모션 하나의 규칙 묶음이다. 확인되지 않은 오퍼로 글을 만들면
규정 위반이 되므로, **확인 전에는 쓰지 못하게** 상태로 막는다.

순서도: docs/flowcharts/cpa_offer.md
"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     Query, UploadFile)
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
    blog_ids: Optional[List[int]] = None
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
        conversion={**found["conversion"],
                    "notice_position": found["notice_position"]},
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
    offer.conversion = {**found["conversion"],
                        "notice_position": found["notice_position"]}
    offer.ftc_notice = found["ftc_notice"]
    offer.status = ST_DRAFT
    offer.confirmed_at = None
    await db.commit()
    await db.refresh(offer)

    logger.info("[CPA] 오퍼 재해석 | %s | 확인 전으로 되돌림", offer.name)
    return {"success": True, "offer": offer.to_dict(),
            "found": found["found"]}


@router.post("/offers/{offer_id}/extract")
async def extract_rules(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """원문에서 규칙을 뽑는다.

    뽑고 나면 **확인 전 상태로 되돌린다.** 규칙이 바뀌었으니 사람이 다시 봐야
    한다. 미분류 줄과 충돌은 그대로 실어 보낸다 — 숨기면 검사되지 않는 것을
    검사된 줄로 안다.
    """
    from ..services.ai.ai_service import AIService
    from ..services.cpa.conflicts import detect, legal_vs_offer
    from ..services.cpa.rule_extractor import extract

    offer = await _get(db, offer_id)
    found = await extract(AIService(db), offer.raw_text)

    offer.rules = found["rules"]
    offer.unmatched = found["unmatched"]
    offer.note = found.get("ai_error") or None
    offer.conflicts = detect(offer.raw_text, found["rules"]) + \
        legal_vs_offer(found["rules"])
    if found["verticals"] and not offer.vertical:
        offer.vertical = ",".join(found["verticals"])
    offer.status = ST_DRAFT
    offer.confirmed_at = None
    await db.commit()
    await db.refresh(offer)

    logger.info("[CPA] 규칙 추출 | %s | 규칙 %d · 미분류 %d · 충돌 %d",
                offer.name, len(offer.rules or []),
                len(offer.unmatched or []), len(offer.conflicts or []))
    return {"success": True, "offer": offer.to_dict()}


class RuleIn(BaseModel):
    """미분류 문장을 규칙으로 올리거나, 규칙을 직접 추가한다."""

    type: str
    scope: str = "all"
    target: str = ""
    value: str = ""
    severity: str = "block"
    source_quote: str = ""
    drop_unmatched: Optional[str] = None


@router.post("/offers/{offer_id}/rules")
async def add_rule(
    offer_id: int,
    payload: RuleIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """규칙을 손으로 추가한다.

    AI 가 못 읽은 문장을 그대로 두면 **검사되지 않는다.** 사람이 규칙으로
    올릴 수 있어야 미분류가 실제로 줄어든다.
    """
    from ..models.cpa_offer import RULE_SCOPES, RULE_TYPES

    offer = await _get(db, offer_id)
    if payload.type not in RULE_TYPES:
        raise HTTPException(status_code=400, detail=f"모르는 유형: {payload.type}")

    rule = {
        "type": payload.type,
        "scope": payload.scope if payload.scope in RULE_SCOPES else "all",
        "target": payload.target[:100], "value": payload.value[:300],
        "source_quote": (payload.source_quote or payload.drop_unmatched
                         or "")[:300],
        "severity": payload.severity if payload.severity in
        ("block", "warn", "review") else "block",
    }
    offer.rules = list(offer.rules or []) + [rule]
    if payload.drop_unmatched:
        offer.unmatched = [x for x in (offer.unmatched or [])
                           if x != payload.drop_unmatched]
    offer.status = ST_DRAFT      # 규칙이 바뀌었으니 다시 확인해야 한다
    offer.confirmed_at = None
    await db.commit()
    await db.refresh(offer)
    return {"success": True, "offer": offer.to_dict()}


class IgnoreIn(BaseModel):
    """검사할 필요 없는 문장을 목록에서 뺀다."""

    line: str


@router.post("/offers/{offer_id}/unmatched/ignore")
async def ignore_unmatched(
    offer_id: int,
    payload: IgnoreIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """이 문장은 규칙이 아니라고 사람이 판단했다.

    지우는 것이 아니라 **판단했다는 표시**다. 커버리지가 올라가 남은 것에
    집중할 수 있다.
    """
    offer = await _get(db, offer_id)
    offer.unmatched = [x for x in (offer.unmatched or []) if x != payload.line]
    await db.commit()
    await db.refresh(offer)
    return {"success": True, "offer": offer.to_dict()}


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
    """오퍼 하나. 원문과 정형 칸 배정까지 준다.

    칸을 보여줘야 **무엇을 못 뽑았는지** 알 수 있다. 유형별로만 늘어놓으면
    "이 오퍼엔 원래 없는 것" 과 "AI 가 놓친 것" 이 구분되지 않는다.
    """
    from ..services.cpa.rule_template import assign, critical_missing

    offer = await _get(db, offer_id)
    template = assign(offer.rules or [], offer.ftc_notice or "",
                      conversion=offer.conversion or {},
                      notice_position=(offer.conversion or {}).get(
                          "notice_position", "title_or_body_start"))
    return {"offer": offer.to_dict(), "raw_text": offer.raw_text,
            "template": template,
            "critical_missing": critical_missing(template)}


async def _get(db: AsyncSession, offer_id: int) -> CpaOffer:
    offer = await db.get(CpaOffer, offer_id)
    if not offer or offer.is_deleted:
        raise HTTPException(status_code=404, detail="오퍼를 찾을 수 없습니다")
    return offer


# ── 제목·글·상담페이지 ────────────────────────────────────

class TitleReq(BaseModel):
    """제목 재고 생성."""

    limit: int = Field(default=40, ge=1, le=200)
    topic_id: Optional[int] = None
    subtopic_id: Optional[int] = None


@router.post("/offers/{offer_id}/titles")
async def make_titles(
    offer_id: int,
    payload: TitleReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """오퍼에서 제목 재고를 만든다.

    만든 제목에는 `cpa_offer_id` 가 붙는다. 이 값이 있으면 **그 오퍼 전용**
    이라, 애드센스 블로그가 뽑아 쓰지 않는다.
    """
    from ..models.title import MainTitle
    from ..services.cpa.title_builder import build

    offer = await _get(db, offer_id)
    if not offer.usable:
        raise HTTPException(
            status_code=400,
            detail="확인되지 않았거나 재확인 기한이 지난 오퍼입니다")
    # 블로그 연결은 이 화면에서 다루지 않는다. 매칭은 비워 둔다.
    blog_ids: List[int] = list(offer.blog_ids or [])

    # 오퍼가 쓰는 하위주제를 제목에 붙인다. 이게 있어야 키워드·제목이
    # 같은 자리에 모이고, 화면에서 "이 오퍼가 쓰는 중" 으로 보인다.
    from ..models.category import SubTopic

    subtopic_id = payload.subtopic_id
    if not subtopic_id and (offer.subtopic_ids or []):
        subtopic_id = int(offer.subtopic_ids[0])
    topic_id = payload.topic_id
    if subtopic_id and not topic_id:
        found = await db.get(SubTopic, subtopic_id)
        topic_id = found.topic_id if found else None

    found = build(offer, limit=payload.limit)
    existing = {
        row for row in (await db.execute(
            select(MainTitle.title).where(
                MainTitle.cpa_offer_id == offer_id))).scalars().all()
    }

    added = 0
    for title in found["titles"]:
        if title in existing:
            continue
        db.add(MainTitle(
            title=title, status="available", source="cpa",
            cpa_offer_id=offer_id,
            matched_blog_ids=json.dumps(blog_ids) if blog_ids else None,
            matched_count=len(blog_ids),
            topic_id=topic_id, subtopic_id=subtopic_id))
        added += 1
    await db.commit()

    # 0개일 때 이유를 말해야 사용자가 다음에 무엇을 할지 안다.
    reason = ""
    if added == 0:
        if not found["keywords"]:
            reason = ("오퍼에 추천 키워드가 없습니다. "
                      "규칙에 content_axis 를 추가하거나 키워드를 직접 넣으세요.")
        elif not found["titles"]:
            reason = "만든 후보가 모두 규칙에 걸렸습니다."
        else:
            reason = f"후보 {len(found['titles'])}개가 모두 이미 있습니다."

    logger.info("[CPA] 제목 생성 | %s | %d개(규칙에 걸림 %d) %s",
                offer.name, added, len(found["skipped"]), reason)
    return {"success": True, "added": added,
            "keywords": found["keywords"],
            "candidates": found["titles"],
            "skipped": found["skipped"], "reason": reason}


@router.get("/offers/{offer_id}/prompt")
async def offer_prompt(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """이 오퍼로 글을 쓸 때 붙는 지시문. 사람이 미리 볼 수 있어야 한다."""
    from ..services.cpa.prompt import build, summary

    offer = await _get(db, offer_id)
    return {"prompt": build(offer), "summary": summary(offer)}


class CheckReq(BaseModel):
    """발행 전 검증."""

    title: str = ""
    body: str = ""


@router.post("/offers/{offer_id}/check")
async def check_content(
    offer_id: int,
    payload: CheckReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """글이 규칙을 지켰나. 막을 때는 어느 규칙에 걸렸는지까지 돌려준다."""
    from ..models.cpa_offer import CpaOffer as _Offer
    from ..services.cpa.gate import check

    offer = await _get(db, offer_id)
    others = [
        url for url in (await db.execute(
            select(_Offer.landing_url).where(
                _Offer.id != offer_id,
                _Offer.is_deleted.is_(False)))).scalars().all() if url
    ]
    return check(offer, payload.title, payload.body, others).to_dict()
