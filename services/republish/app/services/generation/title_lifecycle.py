"""제목 소비 — 어떤 스타일로 다듬고, 무엇을 함께 소진할지.

`generator.py` 가 500줄을 넘어 분리했다. 파이프라인 흐름은 그대로 두고
**제목 하나를 쓰는 규칙**만 여기로 옮긴다.

계획서: docs/plans/title_tab_workplan.md §4-4 · §4-5
"""
from __future__ import annotations

import json
import logging
import random
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.title import MainTitle

logger = logging.getLogger(__name__)


async def pick_style(db: AsyncSession, styles: list,
                     blog_id: Optional[int]) -> Optional[str]:
    """스타일 선택. 성과가 좋았던 쪽에 무게를 준다.

    무작위를 없애지는 않는다 — 한 스타일로 고정하면 다른 스타일의 성과를
    다시는 알 수 없다(탐색이 죽는다). 통계가 실패해도 생성은 계속한다.
    """
    from .style_picker import pick

    try:
        return await pick(db, styles or [], blog_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[GENERATOR] 스타일 선택 실패: {e}")
        return random.choice(styles) if styles else None


async def consume_group(db: AsyncSession, source_title: Any) -> int:
    """제목을 소진한다. 그룹이 있으면 **그룹 전체**를 소진한다.

    그룹은 "같은 소재의 변형들"(유사 제목 + 재조합 제목)이다. 하나를
    쓰면 나머지도 쓸 이유가 없다. 재조합 제목만 소진하면 원본이 남아
    같은 소재로 또 쓰게 된다(계획서 §4-4 C).

    Returns:
        소진한 제목 수(원본 포함).
    """
    source_title.mark_used()
    if not source_title.group_id:
        return 1

    rows = (await db.execute(
        select(MainTitle).where(
            MainTitle.group_id == source_title.group_id,
            MainTitle.id != source_title.id,
            MainTitle.status == "available")
    )).scalars().all()
    for row in rows:
        row.mark_used()
    return 1 + len(rows)


def title_keywords(row: Any) -> List[str]:
    """재조합이 지켜야 할 핵심어.

    없으면 빈 목록이다 — 프롬프트에 아무것도 붙지 않는다.
    """
    raw = getattr(row, "keywords", None)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(k) for k in parsed if k] if isinstance(parsed, list) else []
