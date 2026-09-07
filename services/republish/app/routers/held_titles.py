"""보류 제목 검토 목록 — 3회 보류된 것만 사람이 본다.

근거를 못 찾아 글을 만들지 못한 제목은 **지우지 않는다.** 다음 회차에
다시 뽑히면 그때 자료가 있을 수 있고, 지워 버리면 우리가 놓친 잘못을
확인할 방법이 사라진다.

세 번이면 그 주제에 공개된 근거가 없다고 보는 편이 맞다. 그때만 목록에
올려 사람이 판단한다 — 살릴지, 제목을 고칠지, 버릴지.

순서도: docs/flowcharts/evidence_hold.md
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.category import SubTopic, Topic
from ..models.title import MainTitle
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/held-titles", tags=["data-titles"])
logger = get_logger("held_titles", "app.log")

# 이 횟수부터 검토 목록에 올린다. 한 번은 그날 검색이 나빴을 수 있고
# 두 번은 우연이 겹칠 수 있다. 세 번이면 근거가 없다고 본다.
REVIEW_THRESHOLD = 3


class HeldTitle(BaseModel):
    """보류된 제목 한 줄."""

    id: int
    title: str
    hold_count: int
    hold_reason: str = ""
    last_held_at: Optional[str] = None
    topic: str = ""
    subtopic: str = ""
    status: str = ""


class HeldSummary(BaseModel):
    items: List[HeldTitle]
    total: int = 0
    threshold: int = REVIEW_THRESHOLD
    # 아직 문턱에 못 미친 것들. 얼마나 쌓이고 있는지 보여 준다.
    pending: int = 0


@router.get("", response_model=HeldSummary)
async def list_held(
    min_count: int = Query(REVIEW_THRESHOLD, ge=1, le=20),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> HeldSummary:
    """검토가 필요한 보류 제목."""
    rows = (await db.execute(
        select(MainTitle, Topic.name, SubTopic.name)
        .outerjoin(Topic, Topic.id == MainTitle.topic_id)
        .outerjoin(SubTopic, SubTopic.id == MainTitle.subtopic_id)
        .where(MainTitle.hold_count >= min_count)
        .order_by(MainTitle.hold_count.desc(),
                  MainTitle.last_held_at.desc().nullslast())
        .limit(limit)
    )).all()

    pending = (await db.execute(
        select(func.count(MainTitle.id)).where(
            MainTitle.hold_count > 0, MainTitle.hold_count < min_count)
    )).scalar() or 0

    items = [
        HeldTitle(
            id=row[0].id, title=row[0].title,
            hold_count=row[0].hold_count or 0,
            hold_reason=row[0].hold_reason or "",
            last_held_at=(row[0].last_held_at.isoformat()
                          if row[0].last_held_at else None),
            topic=row[1] or "", subtopic=row[2] or "",
            status=row[0].status or "",
        )
        for row in rows
    ]
    return HeldSummary(items=items, total=len(items),
                       threshold=min_count, pending=int(pending))


class ResolveRequest(BaseModel):
    """검토 결과. 살릴지 버릴지 사람이 정한다."""

    ids: List[int]
    action: str          # "reset" | "archive"


@router.post("/resolve")
async def resolve_held(
    request: ResolveRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """보류 해제(다시 시도) 또는 보관(더 쓰지 않음).

    지우지 않는다 — 보관은 status 만 바꾼다. 나중에 왜 이 제목이
    걸렸는지 돌아볼 수 있어야 한다.
    """
    if request.action not in ("reset", "archive"):
        raise HTTPException(status_code=422,
                            detail="action 은 reset 또는 archive 여야 합니다")
    if not request.ids:
        return {"success": True, "changed": 0}

    rows = (await db.execute(
        select(MainTitle).where(MainTitle.id.in_(request.ids))
    )).scalars().all()

    for row in rows:
        if request.action == "reset":
            # 다시 시도한다. 사유는 남겨 둔다.
            row.hold_count = 0
            row.last_held_at = None
        else:
            row.status = "archived"
    await db.commit()
    logger.info("[HELD_TITLES] %s | %d건", request.action, len(rows))
    return {"success": True, "changed": len(rows), "action": request.action}
