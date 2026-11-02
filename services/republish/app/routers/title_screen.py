"""제목 D 방식 계기판 API — 블로그별 재고(며칠 치)·사이트 점수·채우기 상태.

    GET /titles/screen/inventory  블로그별 쓸 제목·안 쓴 검색어·며칠 치
    GET /titles/screen/sites      사이트 점수 요약(차단·우선 수와 상위 목록)

순서도: docs/flowcharts/title_screen_d.md (0-1)
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.title_screen import TitleSiteScore
from ..models.user import User
from ..routers.auth import get_current_user

logger = get_logger("title_screen", "app.log")

router = APIRouter(prefix="/titles/screen", tags=["title-screen"])


@router.get("/inventory")
async def inventory_board(db: AsyncSession = Depends(get_db_session),
                          user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """블로그별 재고 계기판(며칠 치가 적은 순)과 지금 채우는 블로그."""
    from ..services.title_screen import filler, inventory

    try:
        rows = await inventory.stock(db)
        state = await filler._load(db)
    except Exception as e:  # noqa: BLE001
        logger.error("[TITLE_SCREEN] 계기판 실패 | %s", e)
        raise HTTPException(status_code=500, detail=str(e)[:200])
    return {"short_days": inventory.SHORT_DAYS, "full_days": inventory.FULL_DAYS,
            "filling": state, "blogs": [r.to_dict() for r in rows]}


@router.get("/sites")
async def site_board(db: AsyncSession = Depends(get_db_session),
                     user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """사이트 점수 요약."""
    counts = dict((await db.execute(select(TitleSiteScore.status, func.count())
                                    .group_by(TitleSiteScore.status))).all())
    top = (await db.execute(select(TitleSiteScore).where(TitleSiteScore.seen >= 10)
                            .order_by((TitleSiteScore.passed * 1.0 / TitleSiteScore.seen).desc())
                            .limit(30))).scalars().all()
    return {"counts": counts,
            "top": [{"site": r.site, "seen": r.seen, "passed": r.passed,
                     "rate": round(r.rate, 3), "status": r.status} for r in top]}
