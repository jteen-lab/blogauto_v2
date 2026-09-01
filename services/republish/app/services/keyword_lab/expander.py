"""시드 확장 — 소재 고갈을 막는다.

블로그 카테고리만 시드로 쓰면 매번 같은 결과가 나온다. 두 가지로 넓힌다.

1. **수식어 결합** — 시드 하나로 후보를 여러 개 만든다. 검색광고는 한 번에
   5개를 받으므로 결합한 것을 묶어 보내면 API 호출이 늘지 않는다.
2. **채택 키워드 재귀** — 지난 회차에 채택된 키워드를 다음 시드로 쓴다.
   쓴 것은 promoted 로 표시해 반복을 막는다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate, VERDICT_ADOPT
from .settings import KeywordModuleSettings

logger = get_logger("keyword_expander", "app.log")


def combine(seed: str, modifiers: List[str]) -> List[str]:
    """시드에 수식어를 붙여 후보를 만든다.

    시드 자신도 넣는다 — 시드가 좋은 키워드일 때 놓치면 안 된다.

    공백은 여기서 없앤다. 수식어에 공백이 섞여 있으면 결합 결과에 남고,
    네이버는 공백 든 키워드를 거부한다(400, 11001). 보내는 쪽에서도
    한 번 더 다듬지만, 만들 때부터 깨끗한 편이 낫다.
    """
    base = re.sub(r"\s+", "", seed or "")
    if not base:
        return []
    out = [base]
    seen = {base}
    for m in modifiers or []:
        m = re.sub(r"\s+", "", m or "")
        if not m:
            continue
        kw = f"{base}{m}"
        if kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


async def pick_seeds(
    db: AsyncSession, user_id: int, cfg: KeywordModuleSettings,
    category_seeds: List[Dict[str, Any]], blog_id: Optional[int],
) -> List[Dict[str, Any]]:
    """이번 회차에 쓸 시드를 고른다.

    우선순위: 직접 입력 → 아직 안 쓴 채택 키워드 → 블로그 카테고리.
    **채택 키워드를 앞에 두는 이유**: 카테고리는 매번 같아서 뒤로 밀어야
    새 가지가 자란다.

    채택 키워드끼리는 **관찰된 성과**로 줄을 세운다. 노출이 붙은 축을 먼저
    파고, "확인했더니 노출이 없더라"(perf_score=0)는 맨 뒤로 민다.
    아직 안 재 본 것(NULL)은 그 사이에 둔다 — 실패로 단정할 근거가 없다.
    """
    picked: List[Dict[str, Any]] = []
    seen = set()

    def _add(seed: str, meta: Optional[dict] = None) -> None:
        key = (seed or "").strip()
        if not key or key in seen or len(picked) >= cfg.seed_limit:
            return
        seen.add(key)
        picked.append({
            "seed": key,
            "topic_id": (meta or {}).get("topic_id"),
            "subtopic_id": (meta or {}).get("subtopic_id"),
        })

    for s in cfg.seeds:
        _add(s)

    if cfg.recurse_adopted and len(picked) < cfg.seed_limit:
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == user_id,
                    KeywordCandidate.verdict == VERDICT_ADOPT,
                    KeywordCandidate.promoted.is_(False))
             .order_by(
                 case((KeywordCandidate.perf_score.is_(None), 0.5),
                      else_=KeywordCandidate.perf_score).desc(),
                 KeywordCandidate.search_volume.desc().nullslast())
             .limit(cfg.seed_limit))
        if blog_id:
            q = q.where(KeywordCandidate.blog_id == blog_id)
        for row in (await db.execute(q)).scalars().all():
            _add(row.keyword, {"topic_id": row.topic_id,
                               "subtopic_id": row.subtopic_id})
            row.promoted = True     # 다음 회차에 다시 뽑히지 않게

    if cfg.use_blog_categories:
        for meta in category_seeds:
            _add(meta.get("seed"), meta)

    logger.info("[KEYWORD_EXPANDER] 시드 %d개 | 상한 %d",
                len(picked), cfg.seed_limit)
    return picked


def expand(seeds: List[Dict[str, Any]],
           cfg: KeywordModuleSettings) -> List[Dict[str, Any]]:
    """시드마다 수식어를 붙여 조회 후보로 펼친다."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for meta in seeds:
        for kw in combine(meta.get("seed", ""), cfg.modifiers):
            if kw in seen:
                continue
            seen.add(kw)
            out.append({**meta, "seed": kw, "origin": meta.get("seed")})
    return out
