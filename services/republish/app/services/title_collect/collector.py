"""① 제목 수집 — 채택 키워드로 검색해 제목을 얻는다.

**하는 일은 이것뿐이다.**

    채택 키워드에서 시드 N개 → 검색 → 설정한 수만큼 제목
      → 제목은 바로 임시제목으로
      → 그 제목이 있던 도메인은 니치도메인에 등록(URL 은 캐지 않는다)

도메인에서 URL 을 뽑는 것은 ②도메인 추출의 몫이다. 두 일을 한 사이클에
섞었던 것이 옛 설계의 문제였다.

**상한을 두지 않는다.** 도메인당 URL 수·회차당 새 도메인·미완료 도메인
상한을 걸었더니 초기 상태(도메인 287개 전부 미처리)에서 수집이 영구히
건너뛰어졌다. 누적을 걱정하지 않고 수집만 한다.

계획서: docs/plans/title_tab_workplan.md §2-1
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from ...models.niche_domain import EXTRACT_PENDING, NicheDomain
from ..title_source import SRC_TITLE_COLLECT
from .niche_gate import NicheGate
from .settings import TitleCollectSettings
from .store import TitleStore

logger = get_logger("title_collector", "app.log")


class TitleCollector:
    """채택 키워드로 검색해 제목을 모으고 도메인을 등록한다."""

    def __init__(self, db: AsyncSession, user_id: int, search_service: Any):
        self.db = db
        self.user_id = user_id
        self.search = search_service

    async def run(self, cfg: TitleCollectSettings,
                  gate: NicheGate) -> Dict[str, Any]:
        """한 회차. 건너뛰는 조건은 없다 — 시드가 없을 때만 멈춘다."""
        seeds = await self._seeds(cfg.seed_limit, cfg)
        if not seeds:
            return {"skipped": True, "saved": 0,
                    "message": "채택된 키워드가 없습니다 — 키워드 탭에서 먼저 "
                               "수집·측정·분류를 돌리세요"}

        store = TitleStore(self.db, self.user_id, gate)
        saved = blocked = off_niche = 0
        domains: Dict[str, int] = {}

        for row in seeds:
            found = await self._search(row.keyword, cfg.titles_per_keyword)
            for item in found:
                result = await store.add(
                    title=item["title"], url=item["link"],
                    keyword=row.keyword, candidate_id=row.id,
                    source=SRC_TITLE_COLLECT)
                host = result.get("domain")
                if host:
                    # 걸러진 제목의 도메인도 센다 — 그 도메인에 다른 글이
                    # 있을 수 있고, 추출은 도메인 단위로 돈다.
                    domains[host] = domains.get(host, 0) + 1
                if result["stored"]:
                    saved += 1
                elif result["reason"] == "filtered":
                    blocked += 1
                elif result["reason"] == "off_niche":
                    off_niche += 1
            # 이 키워드로 제목을 만들었음을 표시한다
            row.titled = True

        registered = await self._register_domains(domains)
        await self.db.commit()

        logger.info("[TITLE_COLLECT] 시드 %d개 → 제목 %d개 · 도메인 %d개(신규 %d)",
                    len(seeds), saved, len(domains), registered)
        return {"saved": saved, "blocked": blocked, "off_niche": off_niche,
                "seeds": len(seeds), "domains": len(domains),
                "new_domains": registered, "samples": store.samples[:100]}

    async def _seeds(self, limit: int,
                     cfg: TitleCollectSettings) -> List[KeywordCandidate]:
        """아직 제목을 안 만든 채택 키워드부터.

        `titled` 를 쓰는 이유: `promoted`(시드로 소비됨)와 뜻이 다르다.
        겸용하면 상위 키워드가 제목을 못 받는다.

        **재고가 부족한 니치를 먼저 본다.** 어디를 채워야 하는지는 화면
        (니치 현황)이 보여 주는 것과 같은 기준으로 정한다.
        """
        from ..keyword_lab.scoring import VERDICT_ADOPT

        base = (select(KeywordCandidate)
                .where(KeywordCandidate.user_id == self.user_id,
                       KeywordCandidate.verdict == VERDICT_ADOPT))
        order = [KeywordCandidate.titled.asc(),
                 KeywordCandidate.search_volume.desc().nullslast()]

        picked: List[KeywordCandidate] = []
        if cfg.prioritize_low_niche:
            from .niche_demand import low_subtopics

            low = await low_subtopics(self.db, self.user_id,
                                      cfg.low_niche_threshold)
            if low:
                picked = list((await self.db.execute(
                    base.where(KeywordCandidate.subtopic_id.in_(list(low)))
                    .order_by(*order).limit(max(1, limit))
                )).scalars().all())

        if len(picked) >= limit:
            return picked[:limit]

        # 부족 니치만으로 못 채우면 나머지를 일반 순서로 붙인다 —
        # 부족한 곳이 없다고 회차가 노는 것은 낭비다.
        seen = {row.id for row in picked}
        rest = list((await self.db.execute(
            base.order_by(*order).limit(max(1, limit) * 2)
        )).scalars().all())
        for row in rest:
            if row.id in seen:
                continue
            picked.append(row)
            if len(picked) >= limit:
                break
        return picked[:limit]

    async def _search(self, keyword: str, limit: int) -> List[Dict[str, str]]:
        """검색 상위 결과. 실패는 빈 목록 — 회차를 죽이지 않는다."""
        try:
            result = await self.search.search_blog(
                keyword, display=max(1, min(100, limit)))
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_COLLECT] 검색 실패 | %s | %s", keyword, e)
            return []
        if not result.get("success"):
            logger.warning("[TITLE_COLLECT] 검색 실패 | %s | %s",
                           keyword, result.get("error"))
            return []
        return [{"title": i.get("title", ""),
                 "link": i.get("link") or i.get("bloggerlink") or ""}
                for i in (result.get("items") or [])]

    async def _register_domains(self, domains: Dict[str, int]) -> int:
        """본 도메인을 니치도메인에 등록한다.

        **여기서 URL 을 캐지 않는다.** 도메인만 남기고, 사이트맵을 읽어
        URL 을 뽑는 것은 ②도메인 추출이 맡는다.

        Returns:
            새로 등록한 도메인 수.
        """
        added = 0
        for host, count in sorted(domains.items(), key=lambda x: -x[1]):
            existing = (await self.db.execute(
                select(NicheDomain).where(
                    NicheDomain.user_id == self.user_id,
                    NicheDomain.domain == host)
            )).scalar_one_or_none()

            if existing:
                existing.last_seen_at = func.now()
                continue

            self.db.add(NicheDomain(
                user_id=self.user_id, domain=host,
                platform=_platform(host),
                # 관측 수는 사이트맵을 읽을 때 실제 URL 수로 채워진다.
                url_count=0, extract_status=EXTRACT_PENDING))
            added += 1
        return added


def _platform(host: str) -> str:
    """호스트로 플랫폼을 짐작한다. 모르면 unknown."""
    table = {"tistory.com": "tistory", "blog.naver.com": "naver",
             "blogspot.com": "blogger", "wordpress.com": "wordpress"}
    for suffix, name in table.items():
        if host.endswith(suffix) or host == suffix:
            return name
    return "unknown"
