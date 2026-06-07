"""프롬프트 빌더 옵션 블록 CRUD 서비스.

라우터(`routers/prompt_blocks.py`)가 호출한다. 코드 미지정 생성 시 고유 코드를
자동 생성하며, (block_type, code) UNIQUE 충돌을 사전 검사한다.
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_block import PromptBlock
from app.schemas.prompt_block import PromptBlockCreate, PromptBlockUpdate

logger = logging.getLogger(__name__)


async def list_blocks(
    db: AsyncSession, block_type: Optional[str] = None,
) -> List[PromptBlock]:
    """블록 목록 조회(관리용, 비활성 포함). 타입 필터 선택."""
    stmt = select(PromptBlock)
    if block_type:
        stmt = stmt.where(PromptBlock.block_type == block_type)
    stmt = stmt.order_by(
        PromptBlock.block_type.asc(),
        PromptBlock.sort_order.asc(),
        PromptBlock.id.asc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_block(db: AsyncSession, block_id: int) -> Optional[PromptBlock]:
    """ID로 블록 단건 조회."""
    return await db.get(PromptBlock, block_id)


async def _code_exists(
    db: AsyncSession, block_type: str, code: str,
) -> bool:
    """(block_type, code) 중복 여부."""
    row = await db.execute(
        select(PromptBlock.id)
        .where(PromptBlock.block_type == block_type)
        .where(PromptBlock.code == code)
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _next_sort_order(db: AsyncSession, block_type: str) -> int:
    """해당 축의 다음 정렬값(맨 뒤)."""
    cur = (
        await db.execute(
            select(func.max(PromptBlock.sort_order)).where(
                PromptBlock.block_type == block_type
            )
        )
    ).scalar()
    return (cur or 0) + 1


async def create_block(
    db: AsyncSession, data: PromptBlockCreate,
) -> PromptBlock:
    """블록 생성. code 미지정 시 자동 생성, 중복 시 ValueError."""
    code = (data.code or "").strip()
    if not code:
        code = f"custom-{data.block_type}-{uuid.uuid4().hex[:8]}"
    if await _code_exists(db, data.block_type, code):
        raise ValueError(f"이미 존재하는 코드입니다: {data.block_type}/{code}")

    sort_order = data.sort_order or await _next_sort_order(db, data.block_type)
    block = PromptBlock(
        block_type=data.block_type,
        code=code,
        label=data.label,
        body=data.body,
        cluster=(data.cluster or None),
        sort_order=sort_order,
        is_active=data.is_active,
        is_builtin=False,
    )
    db.add(block)
    await db.commit()
    await db.refresh(block)
    logger.info("[PROMPT_BLOCK] 생성 type=%s code=%s", data.block_type, code)
    return block


async def update_block(
    db: AsyncSession, block_id: int, data: PromptBlockUpdate,
) -> Optional[PromptBlock]:
    """블록 부분 수정. 없으면 None."""
    block = await db.get(PromptBlock, block_id)
    if block is None:
        return None
    for field in ("label", "body", "cluster", "sort_order", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(block, field, value)
    await db.commit()
    await db.refresh(block)
    logger.info("[PROMPT_BLOCK] 수정 id=%s", block_id)
    return block


async def delete_block(db: AsyncSession, block_id: int) -> bool:
    """블록 삭제. 성공 True, 없으면 False."""
    block = await db.get(PromptBlock, block_id)
    if block is None:
        return False
    await db.delete(block)
    await db.commit()
    logger.info("[PROMPT_BLOCK] 삭제 id=%s code=%s", block_id, block.code)
    return True
