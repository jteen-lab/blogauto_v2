"""엔진별 지표 저장 — 후보 한 줄에 엔진마다 지표 한 줄.

화면과 기존 판정은 아직 `keyword_candidates` 의 컬럼을 읽는다. 그래서
**기본 엔진 지표는 후보 행에도 미러링**한다. 화면을 한 번에 갈아엎지 않고
넘어가기 위한 다리이며, 값의 출처는 `keyword_metrics` 다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from ...models.keyword_metric import PRIMARY_ENGINE, KeywordMetric

logger = get_logger("keyword_metrics", "app.log")

# 후보 행에 미러링하는 컬럼(기본 엔진일 때만)
MIRROR_FIELDS = (
    "search_volume", "search_volume_pc", "search_volume_mobile",
    "competition", "doc_count", "monthly_pub_count", "saturation",
)


async def upsert_metric(db: AsyncSession, candidate: KeywordCandidate,
                        engine: str, **values: Any) -> KeywordMetric:
    """엔진 지표를 넣거나 갱신한다.

    Args:
        db: DB 세션
        candidate: 대상 후보
        engine: naver | google
        **values: KeywordMetric 컬럼 값

    Returns:
        저장된 지표 행
    """
    row = (await db.execute(
        select(KeywordMetric).where(
            KeywordMetric.candidate_id == candidate.id,
            KeywordMetric.engine == engine,
        )
    )).scalar_one_or_none()

    if row is None:
        row = KeywordMetric(candidate_id=candidate.id, engine=engine)
        db.add(row)

    for key, value in values.items():
        if hasattr(row, key):
            setattr(row, key, value)

    if engine == PRIMARY_ENGINE:
        mirror_to_candidate(candidate, values)
    return row


def mirror_to_candidate(candidate: KeywordCandidate, values: dict) -> None:
    """기본 엔진 지표를 후보 행에 복사한다(화면 호환용)."""
    for key in MIRROR_FIELDS:
        if key in values and hasattr(candidate, key):
            setattr(candidate, key, values[key])


async def metric_for(db: AsyncSession, candidate_id: int,
                     engine: str = PRIMARY_ENGINE) -> Optional[KeywordMetric]:
    """한 후보의 특정 엔진 지표."""
    return (await db.execute(
        select(KeywordMetric).where(
            KeywordMetric.candidate_id == candidate_id,
            KeywordMetric.engine == engine,
        )
    )).scalar_one_or_none()
