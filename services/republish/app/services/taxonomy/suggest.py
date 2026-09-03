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
from typing import Any, Dict, List, Optional, Set  # noqa: F401

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

# 조합 후보를 만들 때 한 제목에서 볼 말의 수. 전부 조합하면 제목당
# n(n-1)/2 개가 나와 폭발한다.
PAIR_SOURCE_LIMIT = 5

# 조합의 최소 등장 기준은 단일어의 1/N. 둘이 함께 나오는 일은 더 드물다.
PAIR_COUNT_DIVISOR = 3


async def known_terms(db: AsyncSession) -> Set[str]:
    """이미 분류표에 있는 말. 주제·하위주제 이름도 포함한다.

    키워드만 보면 "주제 이름과 같은 말" 을 계속 추천하게 된다.
    """
    out: Set[str] = set()
    # 삭제된 것은 "이미 있는 말" 로 치지 않는다 — 분류 매처가 그것을
    # 쓰지 않으므로, 세면 살아 있는 후보를 놓친다.
    for model, condition in ((Keyword, Keyword.is_deleted.is_(False)),
                             (SubTopic, SubTopic.is_deleted.is_(False)),
                             (Topic, Topic.is_deleted.is_(False))):
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

    **단일어와 조합(`A+B`)을 함께 제안한다.** 운영 분류표의 84%(751/897)가
    조합이다. 단일어만 제안하면 "검사" 같은 흔한 말이 분류표에 들어가
    엉뚱한 제목까지 끌어온다.

    Returns:
        {"scanned", "candidates": [{term, count, samples, kind}]}
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
    pair_counts: Dict[str, int] = {}
    pair_samples: Dict[str, List[str]] = {}

    for title in rows:
        fresh: List[str] = []
        for token in service.content_tokens(title or ""):
            term = (token or "").strip().lower()
            if len(term) < MIN_TOKEN_LEN or term in known or term in fresh:
                continue
            fresh.append(term)
            counts[term] = counts.get(term, 0) + 1
            if len(samples.setdefault(term, [])) < 3:
                samples[term].append(title)

        # 같은 제목에 함께 나온 말들을 짝지어 센다. 조합은 단독보다
        # 좁아서 오분류가 적다.
        for pair in _pairs(fresh):
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
            if len(pair_samples.setdefault(pair, [])) < 3:
                pair_samples[pair].append(title)

    candidates = [
        {"term": term, "count": count, "kind": "single",
         "samples": samples.get(term, [])}
        for term, count in counts.items() if count >= max(1, min_count)
    ]
    # 조합은 기준을 낮춘다 — 둘이 함께 나오는 일은 단독보다 드물다.
    pair_floor = max(1, min_count // PAIR_COUNT_DIVISOR)
    candidates += [
        {"term": term, "count": count, "kind": "combo",
         "samples": pair_samples.get(term, [])}
        for term, count in pair_counts.items() if count >= pair_floor
    ]
    candidates.sort(key=lambda x: (-x["count"], x["kind"] != "combo"))

    logger.info("[TAXONOMY] 미분류 %d건 → 후보 %d개(단일 기준 %d · 조합 기준 %d)",
                len(rows), len(candidates), min_count, pair_floor)
    return {"scanned": len(rows), "known": len(known),
            "candidates": candidates[:max(1, top)]}


def _pairs(terms: List[str]) -> List[str]:
    """한 제목에서 나온 말들의 조합. `A+B` 형태(사전순)로 만든다.

    말이 많은 제목에서 조합이 폭발하지 않게 앞쪽 몇 개만 본다 —
    토큰화가 이미 중요도 순으로 주지는 않지만, 제목 앞부분이 핵심인
    경우가 많다.
    """
    picked = terms[:PAIR_SOURCE_LIMIT]
    out = []
    for i, first in enumerate(picked):
        for second in picked[i + 1:]:
            out.append("+".join(sorted((first, second))))
    return out


def _match_conditions(term: str) -> List[Any]:
    """분류 매처와 **같은 규칙**으로 조건을 만든다.

    `CategoryMatcherService._is_keyword_match` 는 `+` 를 AND 로 읽는다.
    여기서 그것을 흉내 내지 않으면 "회수 예상 건수" 가 실제와 어긋나
    미리보기가 거짓말을 한다.
    """
    parts = [p.strip() for p in (term or "").split("+") if p.strip()]
    return [TempTitle.title.ilike(f"%{p}%") for p in parts]


async def recovery_estimate(db: AsyncSession, term: str) -> int:
    """이 말을 분류표에 넣으면 몇 건이 살아나는가."""
    conditions = _match_conditions(term)
    if not conditions:
        return 0
    from sqlalchemy import func

    return (await db.execute(
        select(func.count()).select_from(TempTitle).where(
            TempTitle.topic_id.is_(None), *conditions)
    )).scalar() or 0


async def recovery_samples(db: AsyncSession, term: str,
                           limit: int = 8) -> List[str]:
    """이 말을 넣으면 **어떤 제목들이** 걸리는지.

    숫자만 보고 승인하면 오분류를 눈으로 확인할 수 없다. "검사" 같은 흔한
    말이 엉뚱한 제목을 끌어오는 것은 표본을 봐야 알 수 있다.
    """
    conditions = _match_conditions(term)
    if not conditions:
        return []
    rows = (await db.execute(
        select(TempTitle.title)
        .where(TempTitle.topic_id.is_(None), *conditions)
        .limit(max(1, limit))
    )).scalars().all()
    return list(rows)


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
