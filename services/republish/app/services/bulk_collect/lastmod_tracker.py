"""
lastmod 추적기 (Phase B)

`BulkCollectProgress` 모델을 활용해 모듈별·도메인별 마지막 sitemap lastmod
시각과 사이클 메트릭을 보관/조회한다.

사용 예:
    tracker = LastmodTracker(db)
    last = await tracker.get_last_seen(module_id=10, blog_domain="ex.com")
    ...
    await tracker.update_last_seen(10, "ex.com", new_lastmod)
    await tracker.record_cycle_stats(10, "ex.com", 900, 120, 3)

구현 방식:
    SELECT → 존재하면 UPDATE / 없으면 INSERT (애플리케이션 레벨).
    실제 PostgreSQL UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) 는 사용하지 않는다.
    이유는 SQLite 호환을 위해 단순한 ORM 패턴으로 충분하기 때문.

Race condition 가능성:
    (module_id, blog_domain) 동시 INSERT 시 UNIQUE 제약 위반 가능.
    다만 본 트래커는 사이클당 1회 호출(LastmodTracker → record_cycle_stats)이라
    실측 위험은 낮다. 위험이 실제로 발견되면 dialect 분기로 pg_insert(...).
    on_conflict_do_update(...) 를 도입할 것.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.bulk_collect_progress import BulkCollectProgress

logger = logging.getLogger(__name__)


class LastmodTracker:
    """BulkCollectProgress 기반 lastmod / 사이클 통계 추적기.

    Attributes:
        db: AsyncSession (호출자가 commit 전략을 정함; 본 클래스는 commit 함).
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Args:
            db: 비동기 SQLAlchemy 세션.
        """
        self.db = db

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------

    async def get_last_seen(
        self,
        module_id: int,
        blog_domain: str,
    ) -> Optional[datetime]:
        """모듈·도메인 쌍의 마지막 lastmod 조회.

        Args:
            module_id: 대량 수집 모듈 ID.
            blog_domain: 블로그 도메인.

        Returns:
            저장된 last_seen_lastmod (없으면 None).
        """
        row = await self._find_row(module_id, blog_domain)
        if row is None:
            return None
        return row.last_seen_lastmod

    async def _find_row(
        self,
        module_id: int,
        blog_domain: str,
    ) -> Optional[BulkCollectProgress]:
        """내부 헬퍼: (module_id, blog_domain) row 조회."""
        stmt = (
            select(BulkCollectProgress)
            .where(BulkCollectProgress.module_id == module_id)
            .where(BulkCollectProgress.blog_domain == blog_domain)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 갱신
    # ------------------------------------------------------------------

    async def update_last_seen(
        self,
        module_id: int,
        blog_domain: str,
        lastmod: datetime,
    ) -> None:
        """`last_seen_lastmod` 만 갱신 (사이클 통계 미포함).

        Args:
            module_id: 모듈 ID.
            blog_domain: 도메인.
            lastmod: 갱신할 lastmod 값.
        """
        row = await self._find_row(module_id, blog_domain)
        if row is None:
            row = BulkCollectProgress(
                module_id=module_id,
                blog_domain=blog_domain,
                last_seen_lastmod=lastmod,
            )
            self.db.add(row)
        else:
            row.last_seen_lastmod = lastmod
        try:
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "update_last_seen 실패 module=%s domain=%s err=%s",
                module_id, blog_domain, exc,
            )
            await self.db.rollback()
            raise

    async def record_cycle_stats(
        self,
        module_id: int,
        blog_domain: str,
        duration_sec: int,
        processed: int,
        failed: int,
    ) -> None:
        """1 사이클 종료 시 통계와 lastmod 만료(now) 기록.

        Args:
            module_id: 모듈 ID.
            blog_domain: 도메인 (도메인 단위 통계가 아니라 사이클 전체 통계인 경우,
                "_cycle_" 같은 별도 키로 호출자가 의도적으로 지정 가능).
            duration_sec: 사이클 소요 시간(초).
            processed: 성공 처리 건수.
            failed: 실패 건수.
        """
        now = datetime.utcnow()
        row = await self._find_row(module_id, blog_domain)
        if row is None:
            row = BulkCollectProgress(
                module_id=module_id,
                blog_domain=blog_domain,
                last_cycle_at=now,
                last_cycle_duration_sec=int(duration_sec),
                last_cycle_processed=int(processed),
                last_cycle_failed=int(failed),
            )
            self.db.add(row)
        else:
            row.last_cycle_at = now
            row.last_cycle_duration_sec = int(duration_sec)
            row.last_cycle_processed = int(processed)
            row.last_cycle_failed = int(failed)

        try:
            await self.db.commit()
            logger.debug(
                "record_cycle_stats module=%s domain=%s dur=%ds "
                "processed=%d failed=%d",
                module_id, blog_domain, duration_sec, processed, failed,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "record_cycle_stats 실패 module=%s domain=%s err=%s",
                module_id, blog_domain, exc,
            )
            await self.db.rollback()
            raise


__all__ = ["LastmodTracker"]
