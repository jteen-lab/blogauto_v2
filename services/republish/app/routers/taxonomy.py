"""분류표 관리 API — 니치 추천과 plan/apply/rollback.

**API 를 먼저 만들면 엔진은 나중에 고를 수 있다.** 화면이든 클로드 코드든
다른 에이전트든 스크립트든, 같은 통로를 지나면 같은 검증·미리보기·롤백을
받는다. 그래서 서버에 개발 도구를 내장할 필요가 없다.

1차 범위는 **카테고리(니치)뿐**이다. 전체 설정을 한 번에 열면 잘못된 호출
하나가 운영을 멈춘다(계획서 §9-6).

계획서: docs/plans/title_tab_workplan.md §9
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.taxonomy_change import ACTOR_UI
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.taxonomy import ai_suggest, changes, suggest

router = APIRouter(prefix="/admin/taxonomy", tags=["taxonomy"])
logger = get_logger("taxonomy_api", "app.log")


class PlanRequest(BaseModel):
    """변경안. 적용하지 않고 영향만 계산한다."""

    items: List[dict]
    actor: str = ACTOR_UI
    summary: Optional[str] = None


class AiSuggestRequest(BaseModel):
    """AI 배치 제안 요청."""

    candidates: List[dict]
    provider: Optional[str] = None
    model: Optional[str] = None
    threshold: float = ai_suggest.MIN_CONFIDENCE


@router.get("")
async def get_tree(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """전체 분류표. 어디에 넣을지 판단하는 근거다."""
    return {"topics": await changes.tree(db)}


@router.get("/suggest")
async def get_suggestions(
    top: int = Query(suggest.DEFAULT_TOP, ge=1, le=200),
    min_count: int = Query(suggest.MIN_COUNT, ge=1, le=10_000),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """미분류에서 빠진 분류어 후보. **AI 를 부르지 않는다.**"""
    result = await suggest.suggest(db, top=top, min_count=min_count)
    summary = await suggest.unclassified_summary(db)
    return {**result, **summary}


@router.post("/suggest/ai")
async def ai_place(
    payload: AiSuggestRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """후보어를 어느 하위주제에 넣을지 AI 에게 묻는다. 사람은 승인만."""
    ask = await _make_ask(db, current_user.id, payload.provider,
                          payload.model)
    tree = await changes.tree(db)
    result = await ai_suggest.AiTaxonomySuggester(ask).run(
        payload.candidates, tree, payload.threshold)
    return {"success": not result.get("error"), **result}


@router.post("/plan")
async def plan_change(
    payload: PlanRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """변경안의 영향을 계산한다. **DB 를 바꾸지 않는다.**"""
    return await changes.plan(db, current_user.id, payload.items,
                              payload.actor, payload.summary)


@router.post("/apply/{change_id}")
async def apply_change(
    change_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """승인된 계획을 적용한다. 적용 전 상태를 스냅샷으로 남긴다."""
    return await changes.apply(db, current_user.id, change_id)


@router.post("/rollback/{change_id}")
async def rollback_change(
    change_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """되돌린다. 스냅샷이 근거다."""
    return await changes.rollback(db, current_user.id, change_id)


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """누가 무엇을 언제 바꿨는지."""
    return {"items": await changes.history(db, current_user.id, limit)}


async def _make_ask(db: AsyncSession, user_id: int,
                    provider: Optional[str], model: Optional[str]) -> Any:
    """AI 호출 함수를 만든다. 제공자가 없으면 None(제안하지 않는다)."""
    if not provider:
        return None

    from ..services.ai.ai_service import AIService

    service = AIService(db, user_id)

    async def ask(prompt: str) -> str:
        result = await service.generate(
            prompt=prompt, provider=provider, model=model, max_tokens=2000)
        return (result or {}).get("content") or ""

    return ask
