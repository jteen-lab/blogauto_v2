"""채택 키워드로 제목을 미리 만들어 재고에 넣는다.

지금은 발행 시점에 AI 가 제목을 만든다. 실패하면 그 회차를 통째로
건너뛴다(수작남이 3회 연속 그랬다). 미리 만들어 두면 발행 시점에는
**꺼내 쓰기만** 하므로 시간도 실패도 늘지 않는다.

기존 재고 구조와 **관문**을 그대로 쓴다. 제목은 금지어 필터 → 카테고리
분류 → 유사도 그룹핑을 거쳐야 재고가 된다(TitleGate). 분류에 실패한 제목은
버리지 않고 임시 제목에 남겨 회수 큐로 쓴다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate, VERDICT_ADOPT
from ...models.keyword_cluster import CLUSTER_NEW, CLUSTER_TITLED, KeywordCluster
from . import intent as intent_mod
from .settings import KeywordModuleSettings
from .title_gate import TitleGate

logger = get_logger("keyword_title_maker", "app.log")

PROMPT = """다음 키워드로 한국어 블로그 글 제목을 {count}개 지어 주세요.

키워드: {keyword}
월간 검색량: {volume}

지켜야 할 것
- 키워드를 제목에 자연스럽게 넣습니다.
- {count}개가 **서로 다른 질문**에 답해야 합니다. 같은 내용을 말만 바꾸지 마세요.
- 검색한 사람이 무엇을 알고 싶어 하는지 생각해 그 답을 예고하는 제목으로.
- 낚시성 표현("충격", "이것만 알면")과 과장을 쓰지 마세요.
- 25~45자.
- 번호·따옴표·군더더기 없이 제목만 한 줄에 하나씩 출력하세요."""


CLUSTER_PROMPT = """다음은 한 주제를 이루는 키워드 묶음입니다.
이 묶음으로 블로그 글 제목을 지어 주세요.

대표 키워드: {name}
검색 의도: {intent}
포함 키워드: {keywords}
독자가 실제로 묻는 것: {questions}

만들 것
- 1번째 줄: **대표 글** 제목 1개 — 묶음 전체를 아우르는 종합 안내
- 2번째 줄부터: **곁가지 글** 제목 {subs}개 — 각각 **서로 다른 질문**에 답한다

지켜야 할 것
- 곁가지 제목끼리 내용이 겹치면 안 됩니다. 말만 바꾼 제목은 쓰지 마세요.
- 포함 키워드를 제목에 자연스럽게 녹입니다.
- 낚시성 표현("충격", "이것만 알면")과 과장을 쓰지 마세요.
- 25~45자.
- 번호·따옴표·군더더기 없이 제목만 한 줄에 하나씩 출력하세요."""


class TitleMaker:
    """키워드 하나에서 제목 여러 개를 만든다."""

    def __init__(self, db: AsyncSession, ai_service, user_id: int):
        self.db = db
        self.ai = ai_service
        self.user_id = user_id

    async def run(
        self, cfg: KeywordModuleSettings, blog, limit: int = 20,
    ) -> Dict[str, Any]:
        """채택됐고 아직 제목을 안 만든 키워드를 처리한다."""
        rows = await self._targets(blog, limit)
        if not rows:
            return {"success": True, "made": 0, "keywords": 0,
                    "message": "제목을 만들 키워드가 없습니다"}

        gate = TitleGate(self.db, self.user_id)
        made = blocked = queued = duplicates = failed = 0
        preview: List[dict] = []

        for row in rows:
            titles = await self._generate(row, cfg, blog)
            if not titles:
                failed += 1
                continue
            # 검증 모드에서는 소비 표시를 남기지 않는다 — 저장을 켰을 때
            # 같은 키워드로 다시 만들 수 있어야 한다.
            # promoted 는 "시드로 썼다", titled 는 "제목을 만들었다".
            if not cfg.dry_run:
                row.titled = True
            outcome = await gate.admit(titles, row, dry_run=cfg.dry_run)
            made += outcome["admitted"]
            blocked += outcome["blocked"]
            queued += outcome["queued"]
            duplicates += outcome["duplicates"]
            preview.extend(outcome.get("preview") or [])

        await self.db.commit()
        logger.info(
            "[TITLE_MAKER] 키워드 %d개 → 재고 %d편 | 차단 %d · 미분류 %d · "
            "중복 %d · 생성실패 %d | 검증모드=%s",
            len(rows), made, blocked, queued, duplicates, failed, cfg.dry_run,
        )
        return {"success": True, "made": made, "keywords": len(rows),
                "blocked": blocked, "queued": queued,
                "duplicates": duplicates, "failed": failed,
                "dry_run": cfg.dry_run, "preview": preview}

    async def run_clusters(self, cfg: KeywordModuleSettings, blog,
                           limit: int = 5) -> Dict[str, Any]:
        """묶음 하나에서 대표 글 1편 + 곁가지 글 N편을 만든다.

        키워드 1개 = 제목 1개는 대량 발행에 맞지 않는다. 묶음으로 만들면
        한 번의 AI 호출에서 서로 다른 질문에 답하는 제목이 여러 개 나온다.

        Args:
            cfg: 모듈 설정
            blog: 대상 블로그
            limit: 한 회차에 처리할 묶음 수

        Returns:
            {"success", "made", "clusters", ...}
        """
        clusters = await self._new_clusters(blog, limit)
        if not clusters:
            return {"success": True, "made": 0, "clusters": 0,
                    "message": "제목을 만들 묶음이 없습니다"}

        gate = TitleGate(self.db, self.user_id)
        made = blocked = queued = duplicates = failed = 0
        preview: List[dict] = []

        for cluster in clusters:
            members = await self._members(cluster)
            if not members:
                continue
            titles = await self._generate_cluster(cluster, members, cfg, blog)
            if not titles:
                failed += 1
                continue

            if not cfg.dry_run:
                for row in members:
                    row.titled = True
            outcome = await gate.admit(titles, members[0], dry_run=cfg.dry_run)
            made += outcome["admitted"]
            blocked += outcome["blocked"]
            queued += outcome["queued"]
            duplicates += outcome["duplicates"]
            for item in outcome.get("preview") or []:
                preview.append({**item, "cluster": cluster.name})

            if not cfg.dry_run:
                cluster.status = CLUSTER_TITLED
                cluster.titles_made = outcome["admitted"]

        await self.db.commit()
        logger.info(
            "[TITLE_MAKER] 묶음 %d개 → 재고 %d편 | 차단 %d · 미분류 %d · "
            "중복 %d · 생성실패 %d | 검증모드=%s",
            len(clusters), made, blocked, queued, duplicates, failed,
            cfg.dry_run,
        )
        return {"success": True, "made": made, "clusters": len(clusters),
                "blocked": blocked, "queued": queued,
                "duplicates": duplicates, "failed": failed,
                "dry_run": cfg.dry_run, "preview": preview}

    async def _generate_cluster(self, cluster: KeywordCluster,
                                members: List[KeywordCandidate],
                                cfg: KeywordModuleSettings,
                                blog) -> List[str]:
        """묶음 하나로 제목을 만든다."""
        keywords = [m.keyword for m in members]
        subs = cfg.titles_per_cluster or len(members)
        subs = max(1, min(30, subs))
        asked = intent_mod.questions(cluster.name, cluster.intent, count=3)

        prompt = CLUSTER_PROMPT.format(
            name=cluster.name,
            intent=intent_mod.INTENT_LABEL.get(cluster.intent, "정보"),
            keywords=", ".join(keywords[:12]),
            questions=" / ".join(asked),
            subs=subs,
        )
        text = await self._ask(prompt, blog, max_tokens=900)
        return self._parse(text, subs + 1)

    async def _new_clusters(self, blog, limit: int) -> List[KeywordCluster]:
        """아직 제목을 안 만든 묶음. 검색량 합계가 큰 것부터."""
        q = (select(KeywordCluster)
             .where(KeywordCluster.user_id == self.user_id,
                    KeywordCluster.status == CLUSTER_NEW)
             .order_by(KeywordCluster.total_volume.desc().nullslast())
             .limit(limit))
        if blog is not None:
            q = q.where(KeywordCluster.blog_id == blog.id)
        return list((await self.db.execute(q)).scalars().all())

    async def _members(self, cluster: KeywordCluster
                       ) -> List[KeywordCandidate]:
        """묶음 구성원. 검색량이 큰 것부터."""
        return list((await self.db.execute(
            select(KeywordCandidate)
            .where(KeywordCandidate.cluster_id == cluster.id)
            .order_by(KeywordCandidate.search_volume.desc().nullslast())
        )).scalars().all())

    async def _targets(self, blog, limit: int) -> List[KeywordCandidate]:
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.verdict == VERDICT_ADOPT,
                    KeywordCandidate.titled.is_(False),
                    # 묶음에 든 키워드는 묶음 경로가 처리한다
                    KeywordCandidate.cluster_id.is_(None))
             .order_by(KeywordCandidate.search_volume.desc().nullslast())
             .limit(limit))
        if blog is not None:
            q = q.where(KeywordCandidate.blog_id == blog.id)
        return list((await self.db.execute(q)).scalars().all())

    async def _generate(self, row: KeywordCandidate,
                        cfg: KeywordModuleSettings, blog) -> List[str]:
        prompt = PROMPT.format(
            keyword=row.keyword, count=cfg.titles_per_keyword,
            volume=row.search_volume or "알 수 없음")
        text = await self._ask(prompt, blog, max_tokens=600)
        return self._parse(text, cfg.titles_per_keyword)

    async def _ask(self, prompt: str, blog, max_tokens: int = 600) -> str:
        """블로그의 글쓰기 AI 로 제목을 받는다. 실패는 빈 문자열."""
        writing = (getattr(blog, "ai_config", None) or {}).get("writing_ai", {}) \
            if blog is not None else {}
        try:
            result = await self.ai.generate(
                prompt=prompt,
                provider=writing.get("provider"),
                model=writing.get("model"),
                max_tokens=max_tokens,
                temperature=0.9,   # 제목은 다양해야 한다
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_MAKER] 생성 실패 | %s", e)
            return ""
        return ((result or {}).get("content") or "").strip()

    @staticmethod
    def _parse(text: str, count: int) -> List[str]:
        """모델이 붙이는 번호·따옴표·군더더기를 걷어낸다."""
        out, seen = [], set()
        for line in (text or "").splitlines():
            t = line.strip()
            t = re.sub(r"^[-*•]\s*", "", t)
            t = re.sub(r"^\d+[.)]\s*", "", t)
            t = t.strip(" \"'“”‘’")
            if len(t) < 8 or len(t) > 120:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= count:
                break
        return out
