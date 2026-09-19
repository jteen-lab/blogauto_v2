"""하위 주제를 고르면 그 키워드를 펼쳐 준다.

프롬프트 템플릿과 홍보 링크는 키워드 조합을 손으로 적어 연결했다. 그런데
카테고리에는 이미 하위 주제마다 키워드가 등록돼 있다. 같은 말을 두 번 적는
셈이고, 카테고리에 키워드를 더해도 모듈은 모른다.

**고를 때 펼쳐서 저장한다.** 글을 만들 때마다 카테고리를 다시 읽지 않기
위해서다 — 고르는 일은 가끔이고 글은 매일 나간다.

순서도: docs/flowcharts/subtopic_link.md
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("subtopic_keywords", "app.log")


def _ints(values: Optional[Iterable[Any]]) -> List[int]:
    """정수 목록으로. 빈 값·이상한 값은 버린다."""
    out: List[int] = []
    for v in values or []:
        try:
            num = int(v)
        except (TypeError, ValueError):
            continue
        if num > 0 and num not in out:
            out.append(num)
    return out


async def keywords_of(db: AsyncSession,
                      subtopic_ids: Optional[Iterable[Any]]) -> List[str]:
    """이 하위 주제들에 달린 키워드 이름. 없으면 빈 목록."""
    ids = _ints(subtopic_ids)
    if not ids:
        return []
    from ...models.category import Keyword

    rows = (await db.execute(
        select(Keyword.name).where(
            Keyword.subtopic_id.in_(ids),
            Keyword.is_deleted.is_(False),
        )
    )).scalars().all()
    out: List[str] = []
    for name in rows:
        text = (name or "").strip()
        if text and text not in out:
            out.append(text)
    return out


async def expand(db: AsyncSession, subtopic_ids: Optional[Iterable[Any]],
                 manual: Optional[Iterable[str]] = None) -> List[str]:
    """하위 주제 키워드 + 손으로 적은 키워드. 순서는 하위 주제가 먼저.

    둘을 합치는 이유: 하위 주제로 큰 그물을 치고, 손으로 적은 것으로 빠진
    말을 보탠다. 고르지 않았으면 손으로 적은 것만 쓴다.
    """
    merged = await keywords_of(db, subtopic_ids)
    for word in manual or []:
        text = str(word or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


async def describe(db: AsyncSession,
                   subtopic_ids: Optional[Iterable[Any]]) -> Dict[str, Any]:
    """화면에 적을 요약 — 하위 주제 몇 개에 키워드 몇 개가 딸렸는지."""
    ids = _ints(subtopic_ids)
    words = await keywords_of(db, ids)
    return {"subtopic_count": len(ids), "keyword_count": len(words),
            "keywords": words}
