"""6단계 사이트 점수 — 출처 사이트마다 '모은 제목 중 몇 %가 통과했나'.

| 조건 | 처리 |
| 20개 이상 봤는데 통과율 10% 미만 | 차단(90일 뒤 다시 확인 — 그때 셈을 비우고 새로 본다) |
| 통과율 30% 이상(10개 이상 봄) | 우선 — 사이트 통째로 훑기 허용 |
| 그 사이 | 지금처럼 |

'버린 제목이 하나라도 있으면 차단' 은 모든 사이트를 막는다(10개 넘는 256곳 모두 해당).
호스트만으로 된 사이트가 차단되면 니치 도메인에도 차단을 걸어 추출이 멈추게 한다.

순서도: docs/flowcharts/title_screen_d.md (6)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Set, Tuple

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.title_screen import SITE_BLOCKED, SITE_NORMAL, SITE_PRIORITY, TitleSiteScore

logger = get_logger("title_screen", "app.log")

BLOCK_MIN_SEEN = 20
BLOCK_RATE = 0.10
PRIORITY_MIN_SEEN = 10
PRIORITY_RATE = 0.30
RECHECK_DAYS = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def judge(seen: int, passed: int) -> str:
    """셈 → 상태."""
    rate = passed / seen if seen else 0.0
    if seen >= BLOCK_MIN_SEEN and rate < BLOCK_RATE:
        return SITE_BLOCKED
    if seen >= PRIORITY_MIN_SEEN and rate >= PRIORITY_RATE:
        return SITE_PRIORITY
    return SITE_NORMAL


async def blocked_sites(db: AsyncSession) -> Set[str]:
    """지금 차단 중인 사이트. 90일이 지난 것은 셈을 비우고 풀어 준다."""
    await db.execute(
        update(TitleSiteScore)
        .where(TitleSiteScore.status == SITE_BLOCKED, TitleSiteScore.recheck_at < _now())
        .values(status=SITE_NORMAL, seen=0, passed=0, blocked_at=None, recheck_at=None))
    rows = (await db.execute(select(TitleSiteScore.site).where(
        TitleSiteScore.status == SITE_BLOCKED))).scalars().all()
    return set(rows)


async def priority_sites(db: AsyncSession) -> Set[str]:
    """통과율 30% 이상 사이트."""
    rows = (await db.execute(select(TitleSiteScore.site).where(
        TitleSiteScore.status == SITE_PRIORITY))).scalars().all()
    return set(rows)


async def record(db: AsyncSession, user_id: int,
                 counts: Dict[str, Tuple[int, int]]) -> Dict[str, int]:
    """(본 수, 통과 수)를 더하고 상태를 다시 매긴다. 새로 막힌·우선 된 수를 돌려준다."""
    changed = {"blocked": 0, "priority": 0}
    if not counts:
        return changed
    rows = {r.site: r for r in (await db.execute(select(TitleSiteScore).where(
        TitleSiteScore.site.in_(list(counts))))).scalars().all()}
    newly_blocked = []
    for site, (seen, passed) in counts.items():
        row = rows.get(site)
        if row is None:
            row = TitleSiteScore(site=site, seen=0, passed=0, status=SITE_NORMAL)
            db.add(row)
        row.seen = (row.seen or 0) + seen
        row.passed = (row.passed or 0) + passed
        status = judge(row.seen, row.passed)
        if status != row.status:
            changed[status] = changed.get(status, 0) + 1
            if status == SITE_BLOCKED:
                row.blocked_at = _now()
                row.recheck_at = _now() + timedelta(days=RECHECK_DAYS)
                newly_blocked.append(site)
            row.status = status
    await _block_domains(db, user_id, newly_blocked)
    return changed


async def _block_domains(db: AsyncSession, user_id: int, sites: list) -> None:
    """호스트만으로 된 사이트는 니치 도메인 추출도 막는다."""
    from ...models.niche_domain import NicheDomain

    hosts = [s for s in sites if "/" not in s]
    if not hosts:
        return
    await db.execute(
        update(NicheDomain)
        .where(NicheDomain.user_id == user_id, NicheDomain.domain.in_(hosts),
               or_(NicheDomain.is_blocked.is_(False), NicheDomain.is_blocked.is_(None)))
        .values(is_blocked=True, blocked_at=_now(),
                blocked_reason="D 사이트 점수 — 통과율 10% 미만(90일 뒤 재확인)"))
    logger.info("[TITLE_SCREEN] 사이트 차단 %d곳(니치 도메인 포함)", len(sites))
