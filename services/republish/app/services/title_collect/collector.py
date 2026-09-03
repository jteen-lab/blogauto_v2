"""① 제목 수집 — 채택 키워드로 검색해 제목과 도메인을 얻는다.

옛 수집과 다른 점 셋:

1. **키워드에 의존하지 않는다.** 옛 `collect` 모듈의 결과를 받지 않고
   정본(`keyword_candidates`)의 채택 키워드를 직접 시드로 쓴다.
2. **도메인당 상한이 있다.** 사이트맵을 통째로 읽어 801건씩 넣던 것을
   최신순 상위 N건으로 자른다.
3. **`candidate_id` 를 남긴다.** 어떤 채택 키워드로 찾았는지 알아야
   확장 재조합이 가능하다.

계획서: docs/plans/title_tab_workplan.md §2-1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from ...models.niche_domain import (
    EXTRACT_PARTIAL, EXTRACT_PENDING, NicheDomain,
)
from ..title_source import SRC_TITLE_COLLECT
from .niche_gate import NicheGate
from .store import TitleStore
from .settings import TitleCollectSettings

logger = get_logger("title_collector", "app.log")


class TitleCollector:
    """채택 키워드로 검색해 제목을 모은다."""

    def __init__(self, db: AsyncSession, user_id: int, search_service: Any):
        self.db = db
        self.user_id = user_id
        self.search = search_service

    async def run(self, cfg: TitleCollectSettings,
                  gate: NicheGate) -> Dict[str, Any]:
        """한 회차.

        미완료 도메인이 상한을 넘으면 **새 도메인을 찾지 않는다.** 분리만
        으로는 격차가 다시 벌어지므로 상한을 함께 둔다.
        """
        pending = await self._pending_domains()
        if pending >= cfg.max_pending_domains:
            msg = f"미완료 도메인 {pending}개 — 신규 수집을 건너뜁니다"
            logger.info("[TITLE_COLLECT] %s", msg)
            return {"skipped": True, "message": msg, "saved": 0,
                    "pending_domains": pending}

        seeds = await self._seeds(cfg.seed_limit)
        if not seeds:
            return {"skipped": True, "saved": 0,
                    "message": "채택된 키워드가 없습니다 — 키워드 탭에서 먼저 "
                               "수집·측정·분류를 돌리세요"}

        store = TitleStore(self.db, self.user_id, gate)
        saved = blocked = off_niche = 0
        domains: Dict[str, int] = {}

        for row in seeds:
            found = await self._search(row.keyword, cfg.urls_per_domain)
            for item in found:
                result = await store.add(
                    title=item["title"], url=item["link"],
                    keyword=row.keyword, candidate_id=row.id,
                    source=SRC_TITLE_COLLECT)
                if result["stored"]:
                    saved += 1
                    host = result.get("domain")
                    if host:
                        domains[host] = domains.get(host, 0) + 1
                elif result["reason"] == "filtered":
                    blocked += 1
                elif result["reason"] == "off_niche":
                    off_niche += 1

        await self._register_domains(domains, cfg.domains_per_cycle)
        await self.db.commit()

        logger.info("[TITLE_COLLECT] 시드 %d개 → 제목 %d개 · 도메인 %d개",
                    len(seeds), saved, len(domains))
        return {"saved": saved, "blocked": blocked, "off_niche": off_niche,
                "seeds": len(seeds), "domains": len(domains),
                "samples": store.samples[:100], "pending_domains": pending}

    async def _seeds(self, limit: int) -> List[KeywordCandidate]:
        """아직 제목을 안 만든 채택 키워드부터.

        `titled` 를 쓰는 이유: `promoted`(시드로 소비됨)와 뜻이 다르다.
        겸용하면 상위 키워드가 제목을 못 받는다.
        """
        from ..keyword_lab.scoring import VERDICT_ADOPT

        return list((await self.db.execute(
            select(KeywordCandidate)
            .where(KeywordCandidate.user_id == self.user_id,
                   KeywordCandidate.verdict == VERDICT_ADOPT)
            .order_by(KeywordCandidate.titled.asc(),
                      KeywordCandidate.search_volume.desc().nullslast())
            .limit(max(1, limit))
        )).scalars().all())

    async def _pending_domains(self) -> int:
        """아직 다 못 캔 도메인 수. 차단된 것은 세지 않는다."""
        return (await self.db.execute(
            select(func.count()).select_from(NicheDomain).where(
                NicheDomain.user_id == self.user_id,
                NicheDomain.is_blocked.is_(False),
                NicheDomain.extract_status.in_(
                    [EXTRACT_PENDING, EXTRACT_PARTIAL]))
        )).scalar() or 0

    async def _search(self, keyword: str, limit: int) -> List[Dict[str, str]]:
        """검색 상위 결과. 실패는 빈 목록 — 회차를 죽이지 않는다."""
        try:
            result = await self.search.search_blog(
                keyword, display=max(1, min(100, limit)))
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_COLLECT] 검색 실패 | %s | %s", keyword, e)
            return []
        if not result.get("success"):
            return []
        return [{"title": i.get("title", ""),
                 "link": i.get("link") or i.get("bloggerlink") or ""}
                for i in (result.get("items") or [])]

    async def _register_domains(self, domains: Dict[str, int],
                                limit: int) -> None:
        """새로 본 도메인을 등록한다. 이미 있으면 관측만 갱신한다.

        한 회차에 새로 들이는 도메인 수를 제한한다 — 유입이 처리를
        앞지르면 도메인만 쌓인다.
        """
        from ..title_gen.niche import host_of

        added = 0
        for host, count in sorted(domains.items(), key=lambda x: -x[1]):
            existing = (await self.db.execute(
                select(NicheDomain).where(
                    NicheDomain.user_id == self.user_id,
                    NicheDomain.domain == host)
            )).scalar_one_or_none()

            if existing:
                existing.url_count = (existing.url_count or 0) + count
                existing.last_seen_at = func.now()
                continue
            if added >= limit:
                continue
            self.db.add(NicheDomain(
                user_id=self.user_id, domain=host,
                platform=_platform(host), url_count=count,
                extract_status=EXTRACT_PENDING))
            added += 1


def _platform(host: str) -> str:
    """호스트로 플랫폼을 짐작한다. 모르면 unknown."""
    table = {"tistory.com": "tistory", "blog.naver.com": "naver",
             "blogspot.com": "blogger", "wordpress.com": "wordpress"}
    for suffix, name in table.items():
        if host.endswith(suffix) or host == suffix:
            return name
    return "unknown"
