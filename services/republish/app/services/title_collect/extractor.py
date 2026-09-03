"""② 도메인 추출 — 사이트맵을 읽어 URL 을 뽑고 제목을 가져온다.

**12만 건 방치의 직접 해법이다.**

옛 흐름은 "키워드로 검색 → 목표 제목 수를 채우면 사이클 종료" 였다.
도메인 하나에서 목표를 못 채우면 중단된 도메인은 저장만 되고 다시
꺼내지지 않았다. 그래서 도메인만 쌓였다.

여기서는 도메인의 **사이트맵 전체**를 읽는다. URL 수에 상한을 두지 않는다 —
2~3백 개인 곳도, 1만 개가 넘는 곳도 있다. 801개로 자르면 캘 수 있는 것을
버린다.

**1회 추출 URL 수는 회차 전체의 예산이다**(도메인당이 아니다).

    예산 100 · A도메인에 30개 남음 → A에서 30개 캐고 B로 넘어가 70개 더
    예산 100 · A도메인에 500개 남음 → A에서 100개만 캐고 종료,
                                      다음 회차에 A의 101번째부터 이어서

이어서 캐는 위치는 `extracted_count` 다. 그 기록이 없어서 도메인이
방치됐다.

계획서: docs/plans/title_tab_workplan.md §2-2
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
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

# 한 회차에 볼 도메인 수 상한. 예산을 다 못 채워도 여기서 멈춘다 —
# 사이트맵이 비어 있는 도메인만 계속 열다 회차가 길어지는 것을 막는다.
MAX_DOMAINS_PER_RUN = 20

# 제목을 가져올 때의 동시 요청 수. 상대 서버에 부담을 주지 않는다.
FETCH_TIMEOUT = 10.0


class DomainExtractor:
    """등록된 도메인의 사이트맵에서 URL 을 뽑아 제목을 가져온다."""

    def __init__(self, db: AsyncSession, user_id: int,
                 sitemap_parser: Any = None, title_fetcher: Any = None):
        self.db = db
        self.user_id = user_id
        self._parser = sitemap_parser
        self._fetch_title = title_fetcher

    async def run(self, cfg: TitleCollectSettings,
                  gate: NicheGate) -> Dict[str, Any]:
        """한 회차. 예산을 다 채우거나 볼 도메인이 떨어지면 끝난다."""
        budget = max(1, cfg.extract_urls)
        store = TitleStore(self.db, self.user_id, gate)
        saved = blocked = visited = 0
        no_sitemap: List[str] = []

        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT,
                                     follow_redirects=True) as client:
            while budget > 0 and visited < MAX_DOMAINS_PER_RUN:
                domain = await self._next_domain()
                if domain is None:
                    break
                visited += 1

                got, empty = await self._drain(domain, budget, store, client)
                saved += got["saved"]
                blocked += got["blocked"]
                budget -= got["seen"]
                if empty:
                    no_sitemap.append(domain.domain)

        await self.db.commit()
        if not visited:
            return {"skipped": True, "saved": 0, "domains": 0,
                    "message": "추출할 도메인이 없습니다"}

        logger.info("[DOMAIN_EXTRACT] 도메인 %d개 → 제목 %d개 · 잔여예산 %d",
                    visited, saved, budget)
        return {"saved": saved, "blocked": blocked, "domains": visited,
                "no_sitemap": no_sitemap, "samples": store.samples[:100]}

    async def _next_domain(self) -> Optional[NicheDomain]:
        """다음에 캘 도메인.

        `partial` 이 먼저다 — 하다 만 것을 마저 끝내는 게 새로 여는 것보다
        낫다. 그다음이 `pending`. 같은 상태 안에서는 오래 안 본 순.
        """
        rows = list((await self.db.execute(
            select(NicheDomain)
            .where(NicheDomain.user_id == self.user_id,
                   NicheDomain.is_blocked.is_(False),
                   NicheDomain.extract_status.in_(
                       [EXTRACT_PARTIAL, EXTRACT_PENDING]))
            .order_by(NicheDomain.last_extracted_at.asc().nullslast())
            .limit(30)
        )).scalars().all())
        if not rows:
            return None
        rows.sort(key=_priority)
        return rows[0]

    async def _drain(self, domain: NicheDomain, budget: int,
                     store: TitleStore, client: Any) -> tuple:
        """도메인 하나에서 예산만큼 캔다.

        Returns:
            ({"saved", "blocked", "seen"}, 사이트맵이 비었는가)
        """
        offset = domain.extracted_count or 0
        urls = await self._sitemap(domain.domain)

        # 관측 수 = 사이트맵의 실제 URL 수. 상한을 두지 않는다.
        if urls:
            domain.url_count = len(urls)

        domain.last_extracted_at = func.now()
        if not urls:
            # 사이트맵이 없거나 못 읽는 도메인. 계속 열지 않는다.
            domain.extract_status = EXTRACT_DONE
            return {"saved": 0, "blocked": 0, "seen": 0}, True

        window = urls[offset:offset + budget]
        if not window:
            domain.extract_status = EXTRACT_DONE
            return {"saved": 0, "blocked": 0, "seen": 0}, False

        saved = blocked = 0
        for url in window:
            title = await self._title_of(url, client)
            if not title:
                continue
            result = await store.add(
                title=title, url=url, keyword=domain.domain,
                candidate_id=None, source=SRC_DOMAIN_EXTRACT)
            if result["stored"]:
                saved += 1
            elif result["reason"] in ("filtered", "off_niche"):
                blocked += 1

        seen = len(window)
        domain.extracted_count = offset + seen
        # 아직 남았으면 partial — 다음 회차에 여기서 이어 캔다.
        domain.extract_status = (
            EXTRACT_DONE if domain.extracted_count >= len(urls)
            else EXTRACT_PARTIAL)
        return {"saved": saved, "blocked": blocked, "seen": seen}, False

    async def _sitemap(self, domain: str) -> List[str]:
        """도메인의 사이트맵 URL 전체. 실패는 빈 목록.

        `max_urls=None` 이다 — 1만 개가 넘는 도메인도 있고, 자르면 캘 수
        있는 것을 버린다.
        """
        if self._parser is None:
            from ..bulk_collect.sitemap_parser import SitemapParser

            self._parser = SitemapParser()
        try:
            return await self._parser.fetch_urls(domain, max_urls=None)
        except Exception as e:  # noqa: BLE001
            logger.warning("[DOMAIN_EXTRACT] 사이트맵 실패 | %s | %s",
                           domain, e)
            return []

    async def _title_of(self, url: str, client: Any) -> Optional[str]:
        """URL 에서 제목을 가져온다. 실패는 None — 한 건이 막혀도 계속한다."""
        if self._fetch_title is None:
            from ..bulk_collect.sitemap_parser import fetch_title_from_url

            self._fetch_title = fetch_title_from_url
        try:
            return await self._fetch_title(url, client=client)
        except Exception as e:  # noqa: BLE001
            logger.debug("[DOMAIN_EXTRACT] 제목 실패 | %s | %s", url, e)
            return None


def _priority(domain: NicheDomain) -> tuple:
    """정렬 키: partial 먼저 · 승격률 높은 순 · 오래 안 본 순.

    승격률이 없는(표본 부족) 도메인은 중간에 둔다 — 나쁘다고 볼 근거도,
    좋다고 볼 근거도 없다.
    """
    stage = 0 if domain.extract_status == EXTRACT_PARTIAL else 1
    score = domain.quality_score()
    rank = -score if score is not None else -0.5
    return (stage, rank, domain.extracted_count or 0)
