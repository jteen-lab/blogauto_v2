"""채택 키워드를 클러스터로 묶어 저장한다.

묶는 규칙 자체는 `clustering.py`(순수 함수)에 있고, 여기서는 DB 를 다룬다.
분리해 둔 이유는 묶는 규칙이 튜닝 대상이라 테스트가 쉬워야 하기 때문이다.

묶이지 않은(작은) 키워드는 버리지 않는다. 클러스터가 아닌 채로 남아
기존 방식(키워드 1개 → 제목 N편)으로 처리된다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate, VERDICT_ADOPT
from ...models.keyword_cluster import CLUSTER_NEW, KeywordCluster
from . import clustering
from . import intent as intent_mod

logger = get_logger("keyword_cluster_builder", "app.log")

# 한 회차에 묶을 최대 후보 수. 전부 훑으면 회차가 길어진다.
DEFAULT_POOL_LIMIT = 300


class ClusterBuilder:
    """채택 키워드를 묶음으로 만든다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def build(self, cfg: Any, blog: Any,
                    pool_limit: int = DEFAULT_POOL_LIMIT) -> Dict[str, Any]:
        """아직 안 묶인 채택 키워드를 묶는다.

        Args:
            cfg: 키워드 모듈 설정
            blog: 대상 블로그(없으면 전역)
            pool_limit: 한 회차에 볼 최대 후보 수

        Returns:
            {"clusters": 만든 묶음 수, "assigned": 묶인 키워드 수}
        """
        if not getattr(cfg, "cluster_enabled", True):
            return {"clusters": 0, "assigned": 0, "skipped": "꺼짐"}

        rows = await self._unclustered(blog, pool_limit)
        if len(rows) < cfg.cluster_min_size:
            return {"clusters": 0, "assigned": 0,
                    "message": f"묶을 후보가 적음 ({len(rows)}개)"}

        groups = clustering.build(
            rows, threshold=cfg.cluster_threshold,
            min_size=cfg.cluster_min_size, max_size=cfg.cluster_max_size)

        made, assigned = 0, 0
        for group in groups:
            cluster = await self._store(group, blog)
            if cluster is None:
                continue
            made += 1
            assigned += len(group)

        # 묶이지 않은 것도 의도는 붙여 둔다 — 단독 제목 생성에 쓰인다.
        for row in rows:
            if row.intent is None:
                row.intent = intent_mod.classify(row.keyword)

        await self.db.commit()
        logger.info("[CLUSTER_BUILDER] 후보 %d개 → 묶음 %d개 · 소속 %d개",
                    len(rows), made, assigned)
        return {"clusters": made, "assigned": assigned, "pool": len(rows)}

    async def _store(self, group: List[KeywordCandidate],
                     blog: Any) -> Optional[KeywordCluster]:
        """묶음을 저장하고 구성원에 소속을 적는다."""
        summary = clustering.describe(group)
        blog_id = getattr(blog, "id", None)

        exists = (await self.db.execute(
            select(KeywordCluster).where(
                KeywordCluster.user_id == self.user_id,
                KeywordCluster.blog_id == blog_id,
                KeywordCluster.name == summary["name"],
            )
        )).scalar_one_or_none()
        if exists is not None:
            # 같은 대표 키워드로 이미 묶었다. 다시 만들지 않는다.
            return None

        cluster = KeywordCluster(
            user_id=self.user_id, blog_id=blog_id,
            name=summary["name"], intent=summary["intent"],
            size=summary["size"], total_volume=summary["total_volume"],
            topic_id=summary["topic_id"], subtopic_id=summary["subtopic_id"],
            status=CLUSTER_NEW,
        )
        self.db.add(cluster)
        await self.db.flush()

        for row in group:
            row.cluster_id = cluster.id
            row.intent = row.intent or intent_mod.classify(row.keyword)
        return cluster

    async def _unclustered(self, blog: Any,
                           limit: int) -> List[KeywordCandidate]:
        """채택됐지만 아직 어느 묶음에도 안 든 키워드."""
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.verdict == VERDICT_ADOPT,
                    KeywordCandidate.cluster_id.is_(None),
                    KeywordCandidate.titled.is_(False))
             .order_by(KeywordCandidate.search_volume.desc().nullslast())
             .limit(limit))
        if blog is not None:
            q = q.where(KeywordCandidate.blog_id == blog.id)
        return list((await self.db.execute(q)).scalars().all())
