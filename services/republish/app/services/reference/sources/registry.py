"""소스 선택과 호출 — **코드가 아니라 데이터로** 고른다.

글 하나를 쓸 때마다 등록된 소스 중 이 주제에 맞는 것을 찾아 부른다.
새 API 를 붙일 때 이 파일을 고치지 않는다(어댑터가 이미 있는 규격이면).

    제목 + 니치 → external_sources 조회 → 맞는 것만 호출 → SourceFact

**못 찾으면 조용히 넘어간다.** 비슷한 상품을 억지로 붙이면 "주담대 일반론"
이 "우리아파트론의 조건" 으로 둔갑한다 — 2026-09-06 에 실제로 난 사고다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.logger import get_logger
from ....models.external_source import (
    ADAPTER_DATA_GO_KR, ADAPTER_FSS_FINLIFE, ExternalSource,
)
from ..relevance import matches
from .base import SourceAdapter, SourceResult

logger = get_logger("reference_registry", "app.log")

# 한 회차에 부를 소스 수. 여러 개가 걸려도 무한정 부르지 않는다.
MAX_SOURCES = 3


def _adapter(code: str) -> Optional[SourceAdapter]:
    """어댑터 코드 → 구현체. 모르는 코드는 None(그 소스만 건너뜀)."""
    if code == ADAPTER_DATA_GO_KR:
        from .data_go_kr import DataGoKrAdapter

        return DataGoKrAdapter()
    if code == ADAPTER_FSS_FINLIFE:
        from .fss_finlife import FssFinlifeAdapter

        return FssFinlifeAdapter()
    logger.warning("[REF_SOURCE] 모르는 어댑터 | %s", code)
    return None


def pick(sources: Sequence[ExternalSource], title: str,
         topics: Sequence[str]) -> List[ExternalSource]:
    """이 글에 쓸 소스를 고른다.

    조건은 둘 중 하나면 된다.
      · 이 글의 주제가 `match_topics` 에 있다
      · 제목에 `match_keywords` 의 말이 있다

    **둘 다 비어 있으면 고르지 않는다.** "아무 때나 쓴다" 로 읽으면
    엉뚱한 니치에서 금융 API 를 부르게 된다.

    Args:
        sources: 켜져 있는 등록 소스
        title: 재조합된 제목
        topics: 이 글의 주제·하위주제 이름들

    Returns:
        부를 소스 목록(최대 MAX_SOURCES)
    """
    topic_set = {t.strip() for t in topics if t and t.strip()}
    picked: List[ExternalSource] = []

    for source in sources:
        want_topics = [t for t in (source.match_topics or []) if t]
        want_words = [w for w in (source.match_keywords or []) if w]
        if not want_topics and not want_words:
            continue

        by_topic = bool(topic_set & set(want_topics))
        by_word = bool(want_words) and matches(title, want_words)
        if by_topic or by_word:
            picked.append(source)
            logger.info("[REF_SOURCE] 후보 | %s | 주제일치=%s 낱말일치=%s",
                        source.code, by_topic, by_word)
        if len(picked) >= MAX_SOURCES:
            break
    return picked


async def load_enabled(db: AsyncSession) -> List[ExternalSource]:
    """켜진 소스 전부. 등록이 없으면 빈 목록이다."""
    try:
        rows = (await db.execute(
            select(ExternalSource)
            .where(ExternalSource.enabled.is_(True))
            .order_by(ExternalSource.id)
        )).scalars().all()
        return list(rows)
    except Exception as e:  # noqa: BLE001 — 표가 아직 없어도 글은 나와야 한다
        logger.warning("[REF_SOURCE] 소스 목록 조회 실패 | %s", e)
        return []


async def gather(db: AsyncSession, title: str, topics: Sequence[str],
                 query: str, entities: Sequence[str]) -> Dict[str, Any]:
    """맞는 소스를 모두 불러 사실을 모은다.

    Returns:
        {"results": [SourceResult], "prompt": str, "used": [코드]}
        아무것도 못 찾으면 prompt 가 빈 문자열이다.
    """
    sources = pick(await load_enabled(db), title, topics)
    if not sources:
        return {"results": [], "prompt": "", "used": []}

    results: List[SourceResult] = []
    for source in sources:
        adapter = _adapter(source.adapter or "")
        if adapter is None:
            continue
        try:
            found = await adapter.fetch(source, query, list(entities))
        except Exception as e:  # noqa: BLE001 — 소스 하나가 글을 막지 않는다
            logger.warning("[REF_SOURCE] 호출 실패 | %s | %s", source.code, e)
            continue
        if found.error:
            logger.info("[REF_SOURCE] %s | %s", source.code, found.error)
        if found.ok:
            results.append(found)
            logger.info("[REF_SOURCE] %s | 사실 %d건", source.code,
                        len(found.facts))

    prompt = "\n\n".join(r.to_prompt() for r in results if r.to_prompt())
    return {"results": results, "prompt": prompt,
            "used": [r.code for r in results]}
