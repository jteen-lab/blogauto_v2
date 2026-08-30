"""프롬프트 빌더 옵션 블록 CRUD API (운영자 내부 도구).

빌더 화면에서 옵션(페르소나·독자·패턴·톤)을 영구적으로 추가/수정/삭제한다.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..schemas.prompt_block import (
    PromptBlockCreate,
    PromptBlockResponse,
    PromptBlockUpdate,
)
from ..services.prompt_builder import crud

logger = get_logger("prompt_blocks", "app.log")

router = APIRouter(
    prefix="/api/v1/prompt-builder/blocks",
    tags=["프롬프트 빌더 블록"],
)


@router.get("/approval-presets")
async def list_approval_presets() -> dict:
    """애드센스 승인 전에만 쓸 수 있는 프리셋 목록.

    빌더 프리셋 목록에서는 제외되고(평소 프롬프트 전용), 프롬프트/생성 모듈의
    애드센스 설정에서 고른다. 설계: prompt_switch_on_approval_plan.md §7
    """
    from ..services.generation.adsense_prompt_switch import approval_presets

    return {
        "presets": [
            {
                "code": p["code"],
                "label": p["label"],
                "categories": p.get("categories", ""),
            }
            for p in approval_presets()
        ],
    }


@router.get("", response_model=List[PromptBlockResponse])
async def list_prompt_blocks(
    block_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """블록 목록(관리용, 비활성 포함)."""
    return await crud.list_blocks(db, block_type)


@router.post("", response_model=PromptBlockResponse, status_code=201)
async def create_prompt_block(
    data: PromptBlockCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """블록 생성."""
    try:
        return await crud.create_block(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{block_id}", response_model=PromptBlockResponse)
async def update_prompt_block(
    block_id: int,
    data: PromptBlockUpdate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """블록 수정(부분)."""
    block = await crud.update_block(db, block_id, data)
    if block is None:
        raise HTTPException(status_code=404, detail="블록을 찾을 수 없습니다")
    return block


@router.delete("/{block_id}")
async def delete_prompt_block(
    block_id: int,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    """블록 삭제."""
    ok = await crud.delete_block(db, block_id)
    if not ok:
        raise HTTPException(status_code=404, detail="블록을 찾을 수 없습니다")
    return {"deleted": block_id}
