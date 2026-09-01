"""소스가 물어온 키워드를 후보로 저장한다.

검색광고 경로(`service._collect_rows`)와 나머지 소스 경로가 **같은 저장
규칙**을 쓰도록 한 곳에 모은다. 저장 규칙이 갈라지면 소스마다 다른 결과가
나오고 무엇이 원인인지 가릴 수 없다.

규칙
    - 이 블로그가 이미 가진 키워드는 건너뛴다(블로그별 격리)
    - 니치는 시드를 물려받지 않고 **키워드 자체를 분류**해 정한다
    - 지표는 엔진별로 `keyword_metrics` 에 남기고 기본 엔진만 후보에 미러링

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from .metrics import upsert_metric
from .scoring import Thresholds, judge
from .sources.base import SOURCE_ENGINE, KeywordIdea

logger = get_logger("keyword_ingest", "app.log")


class IdeaIngestor:
    """키워드 아이디어를 후보 행으로 만든다."""

    def __init__(self, db: AsyncSession, user_id: int,
                 classify: Callable[[str, dict], Awaitable[Dict[str, Any]]],
                 thresholds: Optional[Thresholds] = None):
        """
        Args:
            db: DB 세션
            user_id: 사용자 ID
            classify: (키워드, 폴백메타) → {"topic_id","subtopic_id","seed"}
            thresholds: 판정 기준
        """
        self.db = db
        self.user_id = user_id
        self.classify = classify
        self.thresholds = thresholds

    async def save(self, ideas: List[KeywordIdea], blog_id: Optional[int],
                   existing: set, limit: int) -> Dict[str, Any]:
        """후보로 저장한다.

        Args:
            ideas: 소스가 물어온 키워드
            blog_id: 대상 블로그
            existing: 이미 가진 키워드(소문자) — 저장하며 갱신된다
            limit: 이번에 저장할 최대 수

        Returns:
            {"saved": int, "skipped": int, "by_source": {코드: 개수}}
        """
        saved, skipped = 0, 0
        by_source: Dict[str, int] = {}

        for idea in ideas:
            if saved >= limit:
                break
            key = idea.keyword.lower()
            if not key or key in existing:
                skipped += 1
                continue
            existing.add(key)

            row = await self._build(idea, blog_id)
            self.db.add(row)
            await self.db.flush()
            await self._store_metric(row, idea)

            saved += 1
            by_source[idea.source] = by_source.get(idea.source, 0) + 1

        logger.info("[KEYWORD_INGEST] 저장 %d · 중복 %d | %s",
                    saved, skipped, by_source)
        return {"saved": saved, "skipped": skipped, "by_source": by_source}

    async def _build(self, idea: KeywordIdea,
                     blog_id: Optional[int]) -> KeywordCandidate:
        """후보 행을 만든다. 니치는 키워드 자체를 분류해 정한다."""
        niche = await self.classify(idea.keyword, {"seed": idea.seed})
        verdict, reason, risk = judge(
            idea.keyword, idea.search_volume, None, self.thresholds)
        return KeywordCandidate(
            user_id=self.user_id,
            keyword=idea.keyword,
            seed=idea.seed,
            blog_id=blog_id,
            topic_id=niche.get("topic_id"),
            subtopic_id=niche.get("subtopic_id"),
            search_volume=idea.search_volume,
            search_volume_pc=idea.search_volume_pc,
            search_volume_mobile=idea.search_volume_mobile,
            competition=idea.competition,
            verdict=verdict,
            verdict_reason=reason,
            risk_label=risk,
            source=idea.source,
        )

    async def _store_metric(self, row: KeywordCandidate,
                            idea: KeywordIdea) -> None:
        """엔진 지표로 남긴다. 기본 엔진이면 후보 행에도 미러링된다."""
        engine = SOURCE_ENGINE.get(idea.source, idea.engine)
        await upsert_metric(self.db, row, engine, **idea.as_metric_values())
