"""정식제목 수동 재조합 API.

재조합은 지금까지 발행 직전에만 일어나 결과가 휘발됐다. 여기서는 사람이
정식제목 탭에서 돌리고 **결과를 재고로 남긴다.**

계획서: docs/plans/title_tab_workplan.md §4-2 · §4-6
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.generation.title_recombiner import STYLE_LABELS
from ..services.recombine.service import RecombineService, stale_titles

router = APIRouter(prefix="/data/titles/recombine", tags=["data-titles"])
logger = get_logger("title_recombine_api", "app.log")


class RecombineRequest(BaseModel):
    """재조합 요청."""

    ids: List[int]
    module_id: int
    style: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    # 최신성 갱신 모드 — 연도만 바꾸면 되는 것은 AI 를 부르지 않는다
    freshness: bool = False
    # 키워드 축 확장 — 원본 키워드의 질문들을 힌트로(§4-6 ②)
    expand: bool = False


@router.get("/styles")
async def styles(current_user: User = Depends(get_current_user)) -> dict:
    """고를 수 있는 스타일 목록."""
    return {"styles": [{"code": k, "label": v}
                       for k, v in STYLE_LABELS.items()]}


@router.get("/stale")
async def stale(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """최신성 갱신 후보.

    연도가 지났거나 '올해·최신' 같은 시점 표현이 있는데 오래된 제목이다.
    `suggestion` 이 있으면 **AI 없이** 그 값으로 바꾸면 된다.
    """
    items = await stale_titles(db, limit)
    rule_only = sum(1 for i in items if i["suggestion"])
    return {"total": len(items), "rule_only": rule_only, "items": items}


@router.post("")
async def run_recombine(
    payload: RecombineRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """고른 제목을 재조합해 **같은 그룹**에 넣는다."""
    from ..services.generation.title_recombiner import TitleRecombiner

    service = RecombineService(db, current_user.id,
                               TitleRecombiner(db, current_user.id))
    result = await service.run(
        title_ids=payload.ids, module_id=payload.module_id,
        style=payload.style, provider=payload.provider, model=payload.model,
        freshness=payload.freshness, expand=payload.expand)
    logger.info("[RECOMBINE_API] user=%s | %s건", current_user.id,
                result.get("made"))
    return {"success": True, **result}
