"""② 도메인 추출 — 이미 저장된 도메인에서 제목을 마저 캔다.

**12만 건 방치의 직접 해법이다.**

옛 흐름은 "키워드로 검색 → 목표 제목 수를 채우면 사이클 종료" 였다.
도메인 하나에서 목표를 못 채우면 중단된 도메인은 저장만 되고 다시
꺼내지지 않았다. 다음 사이클은 또 새 키워드로 새 도메인을 찾는다.
그래서 도메인만 쌓였다(URL 126,671건 중 처리 31건).

여기서는 **`extract_status='partial'` 인 도메인을 우선 대상**으로 삼는다.
그 상태를 남기지 않던 것이 근본 원인이었다.

승격률(품질 점수)이 높은 도메인부터 본다 — 어차피 다 못 캘 바에는 좋은
곳부터 캐는 편이 낫다.

계획서: docs/plans/title_tab_workplan.md §2-2 · §2-5
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.niche_domain import (
    EXTRACT_DONE, EXTRACT_PARTIAL, EXTRACT_PENDING, NicheDomain,
)
from ..title_source import SRC_DOMAIN_EXTRACT
from .niche_gate import NicheGate
from .settings import TitleCollectSettings
from .store import TitleStore

logger = get_logger("title_extractor", "app.log")


class DomainExtractor:
    """밀린 도메인에서 제목을 마저 추출한다."""

    def __init__(self, db: AsyncSession, user_id: int, search_service: Any):
        self.db = db
        self.user_id = user_id
        self.search = search_service

    async def run(self, cfg: TitleCollectSettings,
                  gate: NicheGate) -> Dict[str, Any]:
        """한 회차."""
        targets = await self._targets(cfg.extract_domains)
        if not targets:
            return {"skipped": True, "saved": 0, "domains": 0,
                    "message": "추출할 도메인이 없습니다"}

        store = TitleStore(self.db, self.user_id, gate)
        saved = blocked = 0

        for domain in targets:
            found = await self._fetch(domain, cfg.titles_per_domain)
            got = 0
            for item in found:
                result = await store.add(
                    title=item["title"], url=item["link"],
                    keyword=domain.domain, candidate_id=None,
                    source=SRC_DOMAIN_EXTRACT)
                if result["stored"]:
                    saved += 1
                    got += 1
                elif result["reason"] in ("filtered", "off_niche"):
                    blocked += 1
            self._advance(domain, got, cfg.titles_per_domain)

        await self.db.commit()
        logger.info("[DOMAIN_EXTRACT] 도메인 %d개 → 제목 %d개",
                    len(targets), saved)
        return {"saved": saved, "blocked": blocked, "domains": len(targets),
                "samples": store.samples[:100]}

    async def _targets(self, limit: int) -> List[NicheDomain]:
        """다시 꺼낼 도메인.

        `partial` 이 먼저다 — 하다 만 것을 마저 끝내는 게 새로 여는 것보다
        낫다. 그다음이 `pending`. 같은 상태 안에서는 승격률이 높은 순.
        """
        rows = list((await self.db.execute(
            select(NicheDomain)
            .where(NicheDomain.user_id == self.user_id,
                   NicheDomain.is_blocked.is_(False),
                   NicheDomain.extract_status.in_(
                       [EXTRACT_PARTIAL, EXTRACT_PENDING]))
            .order_by(NicheDomain.extract_status.asc(),
                      NicheDomain.last_extracted_at.asc().nullsfirst())
            .limit(max(1, limit) * 3)
        )).scalars().all())

        # 승격률은 파이썬에서 정렬한다 — 표본이 적으면 None 이라 SQL 로
        # 줄세우면 신생 도메인이 0점 취급된다.
        rows.sort(key=_priority)
        return rows[:max(1, limit)]

    async def _fetch(self, domain: NicheDomain,
                     limit: int) -> List[Dict[str, str]]:
        """이 도메인의 글을 찾는다. 실패는 빈 목록.

        도메인을 직접 크롤링하지 않고 **검색으로 좁힌다.** 사이트맵 통crawl
        이 도메인당 801건을 밀어 넣던 문제를 되풀이하지 않기 위해서다.
        """
        query = " ".join(filter(None, [domain.keywords()[:1] and
                                       domain.keywords()[0], domain.domain]))
        try:
            result = await self.search.search_blog(
                query or domain.domain, display=max(1, min(100, limit)))
        except Exception as e:  # noqa: BLE001
            logger.warning("[DOMAIN_EXTRACT] 조회 실패 | %s | %s",
                           domain.domain, e)
            return []
        if not result.get("success"):
            return []

        from ..title_gen.niche import host_of

        out = []
        for item in result.get("items") or []:
            link = item.get("link") or item.get("bloggerlink") or ""
            if host_of(link) != domain.domain.lower():
                continue
            out.append({"title": item.get("title", ""), "link": link})
        return out

    @staticmethod
    def _advance(domain: NicheDomain, got: int, asked: int) -> None:
        """진행 상태를 갱신한다. **이 기록이 없어서 도메인이 방치됐다.**

        요청한 만큼 못 가져왔으면 더 캘 게 없다고 본다(`done`).
        가져왔으면 아직 남았을 수 있으므로 `partial` 로 남긴다.
        """
        domain.extracted_count = (domain.extracted_count or 0) + got
        domain.last_extracted_at = func.now()
        domain.extract_status = EXTRACT_PARTIAL if got >= asked \
            else EXTRACT_DONE


def _priority(domain: NicheDomain) -> tuple:
    """정렬 키: partial 먼저 · 승격률 높은 순 · 오래 안 본 순.

    승격률이 없는(표본 부족) 도메인은 중간에 둔다 — 나쁘다고 볼 근거도,
    좋다고 볼 근거도 없다.
    """
    stage = 0 if domain.extract_status == EXTRACT_PARTIAL else 1
    score = domain.quality_score()
    rank = -score if score is not None else -0.5
    return (stage, rank, domain.extracted_count or 0)
