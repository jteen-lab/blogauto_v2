"""니치 추천 — 미분류 제목에서 빠진 분류어를 찾는다.

**미분류는 쓰레기가 아니라 분류표의 구멍 목록이다.**

분류 매칭은 문자열 포함 검사다(`CategoryMatcherService._is_keyword_match`).
등록된 키워드 896개 중 어느 것도 제목에 없으면 무조건 미분류가 된다.
미분류 64,575건에는 "우리 니치인데 분류어가 없어서 못 걸린" 것이 섞여 있고,
사람이 10만 건을 훑어 채워 넣을 수는 없다.

**AI 없이 된다.** 미분류 제목에서 자주 나오는 말 중 분류표에 없는 것을
세면 그것이 곧 빠진 니치다. 토큰화는 이미 있는 것을 쓴다.

계획서: docs/plans/title_tab_workplan.md §9-2
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import Keyword, SubTopic, Topic
from ...models.title import TempTitle

for _path in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from services.similarity_service import SimilarityService  # noqa: E402

logger = get_logger("taxonomy_suggest", "app.log")

# 이보다 적게 나오는 말은 노이즈일 확률이 높다.
MIN_COUNT = 50

# 한 화면에서 처리할 수 있는 양.
DEFAULT_TOP = 30

# 훑을 미분류 제목 수. 전량을 토큰화하면 오래 걸린다.
SCAN_LIMIT = 20_000

# 너무 짧은 토큰은 분류어가 못 된다.
MIN_TOKEN_LEN = 2


async def known_terms(db: AsyncSession) -> Set[str]:
    """이미 분류표에 있는 말. 주제·하위주제 이름도 포함한다.

    키워드만 보면 "주제 이름과 같은 말" 을 계속 추천하게 된다.
    """
    out: Set[str] = set()
    for model, condition in ((Keyword, Keyword.is_deleted.is_(False)),
                             (SubTopic, None), (Topic, None)):
        query = select(model.name)
        if condition is not None:
            query = query.where(condition)
        rows = (await db.execute(query)).scalars().all()
        for name in rows:
            for part in str(name or "").replace("+", " ").split():
                if part.strip():
                    out.add(part.strip().lower())
    return out


async def suggest(db: AsyncSession, top: int = DEFAULT_TOP,
                  min_count: int = MIN_COUNT,
                  scan_limit: int = SCAN_LIMIT) -> Dict[str, Any]:
    """미분류 제목에서 빠진 분류어 후보를 뽑는다.

    Returns:
        {"scanned": int, "candidates": [{term, count, samples}]}
    """
    rows = (await db.execute(
        select(TempTitle.title)
        .where(TempTitle.topic_id.is_(None))
        .limit(max(1, scan_limit))
    )).scalars().all()

    if not rows:
        return {"scanned": 0, "candidates": [], "known": 0}

    known = await known_terms(db)
    service = SimilarityService()

    counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    for title in rows:
        seen: Set[str] = set()
        for token in service.content_tokens(title or ""):
            term = (token or "").strip().lower()
            if len(term) < MIN_TOKEN_LEN or term in known or term in seen:
                continue
            seen.add(term)
            counts[term] = counts.get(term, 0) + 1
            if len(samples.setdefault(term, [])) < 3:
                samples[term].append(title)

    candidates = [
        {"term": term, "count": count, "samples": samples.get(term, [])}
        for term, count in counts.items() if count >= max(1, min_count)
    ]
    candidates.sort(key=lambda x: -x["count"])

    logger.info("[TAXONOMY] 미분류 %d건 → 후보 %d개(기준 %d회 이상)",
                len(rows), len(candidates), min_count)
    return {"scanned": len(rows), "known": len(known),
            "candidates": candidates[:max(1, top)]}


async def recovery_estimate(db: AsyncSession, term: str) -> int:
    """이 말을 분류표에 넣으면 몇 건이 살아나는가.

    분류 매칭이 문자열 포함이므로 같은 방식으로 센다 — 실제 재분류 결과와
    어긋나지 않게 한다.
    """
    if not term or not term.strip():
        return 0
    from sqlalchemy import func

    return (await db.execute(
        select(func.count()).select_from(TempTitle).where(
            TempTitle.topic_id.is_(None),
            TempTitle.title.ilike(f"%{term.strip()}%"))
    )).scalar() or 0


async def unclassified_summary(db: AsyncSession) -> Dict[str, Any]:
    """회수 큐 요약 — 미분류가 몇 건이고 무엇이 많은가(W12)."""
    from sqlalchemy import func

    total = (await db.execute(
        select(func.count()).select_from(TempTitle).where(
            TempTitle.topic_id.is_(None)))).scalar() or 0
    by_source = dict((await db.execute(
        select(TempTitle.collection_stage, func.count(TempTitle.id))
        .where(TempTitle.topic_id.is_(None))
        .group_by(TempTitle.collection_stage))).all())
    return {"unclassified": int(total),
            "by_source": {k: int(v) for k, v in by_source.items()}}
