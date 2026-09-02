"""니치 도메인 조회 — 각도 참고 대상을 좁힌다.

검색 상위 제목을 그대로 각도로 쓰면 니치와 무관한 글이 섞인다. 옛
파이프라인이 임시제목 10만 건을 쌓고 통과율 2% 에 그친 이유가 그것이다.

`niche_domains`(alembic 066)는 이 니치에서 실제로 상위에 있던 도메인
목록이다. 각도 조회 결과를 그 도메인 것부터 본다.

**완전 배제는 하지 않는다.** 목록에 없는 새 경쟁자를 놓치게 되고, 목록이
비어 있는 초기에는 각도가 통째로 사라진다. 우선순위만 준다.

계획서: docs/plans/title_pipeline_redesign_plan.md §2-3
"""
from __future__ import annotations

from typing import Optional, Set
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.niche_domain import NicheDomain

logger = get_logger("title_niche", "app.log")


async def active_domains(db: AsyncSession, user_id: int) -> Set[str]:
    """각도 참고 대상 도메인. 실패는 빈 집합이다 — 각도를 멈출 이유는 없다."""
    try:
        rows = (await db.execute(
            select(NicheDomain.domain).where(
                NicheDomain.user_id == user_id,
                NicheDomain.is_active.is_(True))
        )).scalars().all()
    except Exception as e:  # noqa: BLE001
        logger.warning("[TITLE_NICHE] 도메인 조회 실패 | %s", e)
        return set()
    return {d.lower() for d in rows if d}


def host_of(link: Optional[str]) -> str:
    """URL 의 호스트. 앞의 www. 는 뗀다."""
    if not link:
        return ""
    try:
        host = (urlparse(link).netloc or "").lower()
    except (ValueError, AttributeError):
        return ""
    return host[4:] if host.startswith("www.") else host


def in_niche(link: Optional[str], domains: Set[str]) -> bool:
    """이 링크가 니치 도메인의 것인가.

    목록이 비어 있으면 판정하지 않는다(전부 통과). 초기 상태에서 각도가
    통째로 사라지는 것을 막는다.
    """
    if not domains:
        return True
    host = host_of(link)
    if not host:
        return False
    if host in domains:
        return True
    # blog.naver.com/xxx 처럼 호스트가 같고 경로로 갈리는 플랫폼도 있다.
    return any(host.endswith("." + d) or d.endswith("." + host)
               for d in domains)
