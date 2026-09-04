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


def is_recombined(row: Any) -> bool:
    """이미 재조합된 제목인가.

    값이 **정수일 때만** 참으로 본다. `getattr(...)` 만 쓰면 목 객체나
    지연 로딩 프록시가 truthy 로 잡혀, 멀쩡한 원본 제목까지 "이미
    재조합됨" 으로 오인하고 재조합을 건너뛴다.
    """
    value = getattr(row, "recombined_from_id", None)
    return isinstance(value, int) and value > 0


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

    # 그룹 소진은 부가 동작이다. 여기서 실패해도 글은 이미 만들어졌으므로
    # 파이프라인 전체를 되돌리지 않는다 — 최소한 원본은 소진된다.
    try:
        rows = (await db.execute(
            select(MainTitle).where(
                MainTitle.group_id == source_title.group_id,
                MainTitle.id != source_title.id,
                MainTitle.status == "available")
        )).scalars().all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[GENERATOR] 그룹 소진 실패(원본만 소진): {e}")
        return 1

    count = 0
    for row in rows:
        row.mark_used()
        count += 1
    return 1 + count


async def resolve_provider(db: AsyncSession, user_id: int,
                           provider: Optional[str]) -> Optional[str]:
    """제목 AI 제공자. 블로그 설정이 비면 등록된 활성 키에서 찾는다.

    `TitleRecombiner` 는 제공자가 없으면 예외 대신 **원본을 그대로**
    돌려준다. 그러면 재조합이 조용히 무효가 되고 원인을 알 수 없다.
    수동 재조합과 같은 폴백을 여기도 둔다.
    """
    if provider:
        return provider
    try:
        from ...models.ai_api_key import AIApiKey

        return (await db.execute(
            select(AIApiKey.provider)
            .where(AIApiKey.user_id == user_id,
                   AIApiKey.is_active.is_(True),
                   AIApiKey.status == "active")
            .order_by(AIApiKey.priority.asc())
            .limit(1)
        )).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[GENERATOR] 기본 AI 조회 실패: {e}")
        return None


async def distinct_or_original(db: AsyncSession, result: Any,
                               source_title: Any) -> str:
    """재조합 결과가 기존 제목과 겹치면 원본을 쓴다.

    재조합은 관문 밖이라 무검사였다. 수동 재조합과 **같은 검사**를 쓴다
    (계획서 §4-5 C). 겹치면 원본으로 되돌린다 — 발행 직전이라 재시도로
    시간을 끌기보다 안전한 쪽을 택한다.
    """
    text = (getattr(result, "recombined_title", None) or "").strip()
    if not text or text == getattr(source_title, "title", None):
        return getattr(source_title, "title", "") or text

    try:
        from ..recombine.dedup import find_clash

        clash = await find_clash(db, text, source_title)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[GENERATOR] 중복 검사 실패(그대로 사용): {e}")
        return text

    if clash:
        logger.info(
            f"[GENERATOR] 재조합 결과가 기존 제목과 겹침 → 원본 사용 | "
            f"'{text[:30]}' ≈ '{clash[:30]}'")
        return getattr(source_title, "title", "") or text
    return text


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
