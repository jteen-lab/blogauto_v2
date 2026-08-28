"""프롬프트 빌더 옵션 블록 DB 저장/조회 레이어.

- ensure_seeded(db): prompt_blocks 가 비어 있으면 기본값(blocks.py 상수)을 시드.
- load_blocks_for_template(db): 빌더 UI 에 넘길 dict 를 DB 기반으로 구성.

옵션(페르소나·독자·패턴·톤)은 DB(prompt_blocks)에서, 공통원칙·구조·프리셋·구분선은
당분간 상수(blocks.py)에서 가져온다(후속 단계에서 확장).
"""
from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_block import PromptBlock
from app.services.prompt_builder import blocks as B

logger = logging.getLogger(__name__)

# block_type 코드 ↔ blocks.py 상수 매핑
_DEFAULT_SOURCES = {
    "persona": B.PERSONAS,
    "reader": B.READERS,
    "pattern": B.PATTERNS,
    "tone": B.TONES,
    "common": B.COMMONS,
}


async def ensure_seeded(db: AsyncSession) -> None:
    """기본 블록을 **코드 단위로** 시드한다(멱등, 추가만).

    이전에는 "해당 타입 행이 하나도 없을 때만" 시드했다. 그래서 이미 시드된 DB에
    **새 블록을 추가하면 영원히 들어가지 않았다** — 프리셋이 존재하지 않는 코드를
    가리켜 조용히 깨진다(2026-08-28 니치 블록 추가 시 발견).

    지금은 타입별로 **없는 코드만** 넣는다. 운영자가 편집한 기존 행은 코드가
    이미 있으므로 건드리지 않는다.
    """
    rows: List[PromptBlock] = []
    for block_type, items in _DEFAULT_SOURCES.items():
        existing_codes = set(
            (
                await db.execute(
                    select(PromptBlock.code).where(
                        PromptBlock.block_type == block_type
                    )
                )
            ).scalars().all()
        )
        max_order = (
            await db.execute(
                select(func.max(PromptBlock.sort_order)).where(
                    PromptBlock.block_type == block_type
                )
            )
        ).scalar()
        next_order = (max_order or 0) + 1 if existing_codes else 0

        for idx, item in enumerate(items):
            if item["code"] in existing_codes:
                continue
            rows.append(
                PromptBlock(
                    block_type=block_type,
                    code=item["code"],
                    label=item["label"],
                    body=item["body"],
                    cluster=item.get("cluster") or None,
                    sort_order=(next_order + idx) if existing_codes else idx,
                    is_active=True,
                    is_builtin=True,
                )
            )
    if not rows:
        return
    db.add_all(rows)
    await db.commit()
    logger.info("[PROMPT_BUILDER] 기본 블록 %d개 시드 완료 | %s", len(rows),
                ", ".join(sorted({r.code for r in rows})))


async def _load_by_type(db: AsyncSession, block_type: str) -> List[dict]:
    """특정 축의 활성 블록을 정렬 순서대로 dict 리스트로 반환."""
    result = await db.execute(
        select(PromptBlock)
        .where(PromptBlock.block_type == block_type)
        .where(PromptBlock.is_active.is_(True))
        .order_by(PromptBlock.sort_order.asc(), PromptBlock.id.asc())
    )
    return [row.to_block_dict() for row in result.scalars().all()]


async def load_blocks_for_template(db: AsyncSession) -> Dict[str, object]:
    """빌더 템플릿용 dict 를 DB 기반으로 구성(빈 DB 는 자동 시드).

    구조는 기존 ``blocks_for_template()`` 와 100% 동일하다(옵션 출처만 DB).
    """
    await ensure_seeded(db)
    try:
        personas = await _load_by_type(db, "persona")
        readers = await _load_by_type(db, "reader")
        patterns = await _load_by_type(db, "pattern")
        tones = await _load_by_type(db, "tone")
        commons = await _load_by_type(db, "common")
    except Exception as exc:  # noqa: BLE001 - DB 문제 시 상수 폴백
        logger.warning("[PROMPT_BUILDER] DB 블록 로드 실패, 상수 폴백: %s", exc)
        return B.blocks_for_template()

    # 폴백: 특정 축이 비면 상수 사용(데이터 유실 방지)
    return {
        "personas": personas or B.PERSONAS,
        "readers": readers or B.READERS,
        "patterns": patterns or B.PATTERNS,
        "tones": tones or B.TONES,
        "commons": commons or B.COMMONS,
        "presets": B.PRESETS,
        "common_rules": B.COMMON_RULES,
        "structure": B.STRUCTURE,
        "divider": B.DIVIDER,
    }
