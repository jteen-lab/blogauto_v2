"""
청크 프로세서 (Phase B)

대량 수집 모듈의 핵심 워커.

역할:
    1. CollectedUrl 테이블에서 처리 대기(pending) URL 중 한 청크(chunk_size 개)를 로딩
    2. 도메인별로 묶어 비동기 병렬로 제목 추출
    3. 성공/실패에 따라 CollectedUrl.title_fetch_status / title 갱신
    4. Timebox 만료 시 즉시 중단해 다음 사이클로 넘김

설계 원칙:
    - DB 세션은 호출자가 주입 (commit 책임도 호출자/메서드 분리)
    - 외부 의존성(DomainLimiter, Timebox)은 생성자/메서드 인자로 주입
    - 함수당 50줄 한도, 파일 500줄 한도 준수
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func as sa_func

from ...models.collected_url import CollectedUrl
from .domain_limiter import DomainLimiter
from ..title_collect.sitemap import fetch_title_from_url
from .timebox import Timebox

logger = logging.getLogger(__name__)


@dataclass
class ChunkStats:
    """청크 처리 결과 집계.

    Attributes:
        processed: 제목 추출 성공 건수.
        failed: 실패 건수 (네트워크/파싱 오류 등).
        duration_sec: 청크 처리 소요 시간(초, 반올림 정수).
    """

    processed: int = 0
    failed: int = 0
    duration_sec: int = 0


class ChunkProcessor:
    """`collected_urls` 의 pending row 를 청크 단위로 처리하는 워커.

    Attributes:
        db: AsyncSession.
        domain_limiter: 도메인별 동시 요청 제한기.
        timebox: 사이클 타임박스 (만료 시 중단).
        http_timeout: 개별 URL 조회 타임아웃.
    """

    def __init__(
        self,
        db: AsyncSession,
        domain_limiter: DomainLimiter,
        timebox: Timebox,
        http_timeout: float = 10.0,
        save_temp_titles: bool = True,
    ) -> None:
        """
        Args:
            db: 비동기 SQLAlchemy 세션.
            domain_limiter: 도메인 동시성 제한기.
            timebox: 사이클 타임박스.
            http_timeout: 개별 URL GET 타임아웃 (초).
            save_temp_titles: 추출 제목을 TempTitle(임시제목탭)에 저장할지 여부.
        """
        self.db = db
        self.domain_limiter = domain_limiter
        self.timebox = timebox
        self.http_timeout: float = http_timeout
        self.save_temp_titles: bool = save_temp_titles
        # 제목 저장 시 분류/필터용 (cycle당 1회 로드, 청크 간 재사용)
        self._category_matcher = None
        self._title_filters = None

    # ------------------------------------------------------------------
    # 청크 로딩
    # ------------------------------------------------------------------

    async def load_pending_chunk(
        self,
        module_id: int,
        chunk_size: int,
        source_mode: str,
        order_mode: str = "stored",
    ) -> List[CollectedUrl]:
        """다음 청크에서 제목 추출 대상 URL 을 가져온다.

        source_mode (Phase B-042):
            - "direct_input": source_module_id = module_id (모듈별 격리).
            - "from_collect_module": source_module_id IS NULL (레거시/collect 풀).

        Args:
            module_id: 호출 모듈 ID (direct_input 필터 키).
            chunk_size: 한 번에 가져올 URL 수.
            source_mode: "direct_input" | "from_collect_module".
            order_mode: "stored"(id ASC) | "random".

        Returns:
            처리 대상 CollectedUrl 리스트 (없으면 빈 리스트).
        """
        if chunk_size <= 0:
            return []

        stmt = (
            select(CollectedUrl)
            .where(CollectedUrl.title_fetch_status == "pending")
            .where(CollectedUrl.is_active.is_(True))
        )
        stmt = self._apply_source_mode_filter(stmt, source_mode, module_id)

        if order_mode == "random":
            stmt = stmt.order_by(sa_func.random())
        else:
            stmt = stmt.order_by(CollectedUrl.id.asc())
        stmt = stmt.limit(chunk_size)

        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        logger.debug(
            "load_pending_chunk module=%s mode=%s order=%s size=%d → %d rows",
            module_id, source_mode, order_mode, chunk_size, len(rows),
        )
        return rows

    def _apply_source_mode_filter(
        self,
        stmt,
        source_mode: str,
        module_id: int,
    ):
        """source_mode 에 따라 source_module_id WHERE 절을 추가.

        알 수 없는 모드는 보수적으로 레거시(NULL) 풀로 처리하고 경고 로그.
        """
        # 재설계(2026-06-04): 제목 추출 대상은 항상 "이 모듈이 사이트맵에서
        # 크롤해 적재한 포스트 URL"(source_module_id == module_id)이다.
        # NULL 풀은 Phase 1 의 '블로그 소스 URL' 전용이므로 제목 추출 대상이 아니다.
        # (direct_input/from_collect_module 모두 동일)
        return stmt.where(CollectedUrl.source_module_id == module_id)

    # ------------------------------------------------------------------
    # 청크 처리
    # ------------------------------------------------------------------

    async def process_chunk(
        self,
        urls: List[CollectedUrl],
    ) -> ChunkStats:
        """주어진 청크를 도메인 그룹별 병렬로 처리한다.

        Args:
            urls: 처리 대상 CollectedUrl 리스트.

        Returns:
            ChunkStats: 처리/실패 건수 및 소요 시간.
        """
        stats = ChunkStats()
        if not urls:
            return stats

        start = time.monotonic()
        groups = self._group_by_domain(urls)
        logger.info(
            "process_chunk start total=%d domains=%d",
            len(urls), len(groups),
        )

        async with httpx.AsyncClient(
            timeout=self.http_timeout, follow_redirects=True,
        ) as client:
            tasks = [
                asyncio.create_task(
                    self._process_one(row, client),
                )
                for row in urls
            ]
            for done in asyncio.as_completed(tasks):
                if self.timebox.expired:
                    logger.warning(
                        "process_chunk 타임박스 만료 → 남은 태스크 취소",
                    )
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    break
                try:
                    ok = await done
                    if ok:
                        stats.processed += 1
                    else:
                        stats.failed += 1
                except asyncio.CancelledError:
                    stats.failed += 1
                except Exception as exc:  # noqa: BLE001
                    stats.failed += 1
                    logger.warning("process_chunk task 예외 err=%s", exc)

        # 제목 추출 성공분을 TempTitle(임시제목탭)에 저장.
        # ※ 동시 gather 안에서 DB 쿼리를 하면 AsyncSession 동시성 위반이므로
        #   반드시 gather 종료 후 순차로 처리한다.
        if self.save_temp_titles:
            await self._persist_temp_titles(urls)

        # 변경사항 일괄 커밋 (collected_urls 상태 + TempTitle 동시 커밋)
        try:
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("process_chunk commit 실패 err=%s", exc)
            await self.db.rollback()

        stats.duration_sec = int(time.monotonic() - start)
        logger.info(
            "process_chunk done processed=%d failed=%d dur=%ds",
            stats.processed, stats.failed, stats.duration_sec,
        )
        return stats

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_domain(
        urls: Iterable[CollectedUrl],
    ) -> dict[str, List[CollectedUrl]]:
        """CollectedUrl 리스트를 도메인 기준으로 그룹화."""
        groups: dict[str, List[CollectedUrl]] = {}
        for row in urls:
            domain = (row.domain or "").strip() or "_unknown_"
            groups.setdefault(domain, []).append(row)
        return groups

    @staticmethod
    def _extract_domain(url: str) -> str:
        """URL 에서 호스트만 추출 (fallback 용)."""
        try:
            return urlparse(url).netloc or "_unknown_"
        except Exception:  # noqa: BLE001
            return "_unknown_"

    async def _process_one(
        self,
        row: CollectedUrl,
        client: httpx.AsyncClient,
    ) -> bool:
        """단일 URL 에 대해 도메인 락 잡고 제목 추출.

        Args:
            row: 처리할 CollectedUrl ORM 인스턴스.
            client: 공유 httpx 클라이언트.

        Returns:
            성공 True / 실패 False.
        """
        if self.timebox.expired:
            return False
        domain = (row.domain or "").strip() or self._extract_domain(row.url)
        try:
            async with self.domain_limiter.acquire(domain):
                title = await fetch_title_from_url(
                    row.url,
                    timeout=self.http_timeout,
                    client=client,
                )
            if title:
                row.mark_title_fetched(title)
                return True
            row.mark_title_failed("title 추출 실패(빈 결과)")
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            row.mark_title_failed(str(exc))
            logger.debug(
                "_process_one 실패 url=%s err=%s", row.url, exc,
            )
            return False


    async def _persist_temp_titles(
        self,
        urls: List[CollectedUrl],
    ) -> None:
        """제목 추출 성공 행을 TempTitle(임시제목탭)에 저장 (순차 dedup).

        gather 종료 후 호출되어야 한다(동시 DB 접근 금지). 같은 제목은
        세션 캐시 + DB(lower) 중복 체크로 한 번만 저장한다. 커밋은 호출자
        (`process_chunk`)가 일괄 수행한다.

        뉴스수집과 동일하게 제목 필터링 + 카테고리 자동 분류를 적용한다.
        """
        from app.models.title import TempTitle
        from ..title_dedup import title_exists

        await self._ensure_classifiers()

        seen: set[str] = set()
        saved = 0
        filtered = 0
        for row in urls:
            if row.title_fetch_status != "done" or not row.title:
                continue
            title = (row.title or "").strip()
            if len(title) < 5:
                continue
            key = title.lower()
            if key in seen:
                continue
            # 제목 필터 (뉴스수집 _check_filter와 동일 규칙)
            if self._match_title_filter(title):
                seen.add(key)
                filtered += 1
                continue
            # 임시(TempTitle) + 정식(MainTitle) 모두와 중복 체크
            if await title_exists(self.db, title):
                seen.add(key)
                continue
            cat = await self._match_title_category(title)
            self.db.add(self._build_temp_title(row, title, cat))
            seen.add(key)
            saved += 1
        if saved or filtered:
            logger.info(
                "process_chunk TempTitle 저장 %d건 (필터제외 %d건)",
                saved, filtered,
            )

    @staticmethod
    def _build_temp_title(
        row: CollectedUrl,
        title: str,
        cat: Tuple[Optional[int], Optional[int], Optional[int]],
    ):
        """분류 결과를 포함한 TempTitle ORM 인스턴스 생성."""
        from app.models.title import TempTitle

        blog_url = f"https://{row.domain}/" if row.domain else row.url
        topic_id, subtopic_id, matched_keyword_id = cat
        return TempTitle(
            title=title[:500],
            source_blog_url=(blog_url or "")[:1000],
            source_post_url=(row.url or "")[:1000],
            collection_stage="bulk_collect",
            status="new",
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            matched_keyword_id=matched_keyword_id,
        )

    async def _ensure_classifiers(self) -> None:
        """카테고리 매처/제목 필터를 1회 로드 (청크 간 재사용)."""
        if self._category_matcher is None:
            from ..category_matcher_service import CategoryMatcherService
            self._category_matcher = CategoryMatcherService(self.db)
        if self._title_filters is None:
            from ...models.content_filter import ContentFilter
            result = await self.db.execute(
                select(ContentFilter).where(
                    ContentFilter.is_active.is_(True)
                )
            )
            self._title_filters = list(result.scalars().all())
            logger.info(
                "대량수집 제목 필터 %d개 로드", len(self._title_filters),
            )

    def _match_title_filter(self, title: str) -> bool:
        """활성 ContentFilter(target=title/both)에 걸리면 True.

        걸린 필터의 매칭 카운트를 증가시킨다. 뉴스수집 _check_filter와
        동일 규칙(keyword/pattern/domain)을 적용한다.
        """
        import re

        text_lower = title.lower().strip()
        for f in (self._title_filters or []):
            target = (f.target_type or "both").lower().strip()
            if target not in ("title", "both"):
                continue
            value = (f.filter_value or "").lower().strip()
            if not value:
                continue
            ftype = (f.filter_type or "keyword").lower().strip()
            matched = False
            if ftype == "pattern":
                try:
                    matched = bool(re.search(value, text_lower))
                except re.error:
                    continue
            else:  # keyword / domain
                matched = value in text_lower
            if matched:
                f.increment_match()
                logger.info(
                    "대량수집 제목 필터링: '%s' → '%s'",
                    title[:40], f.filter_value,
                )
                return True
        return False

    async def _match_title_category(
        self, title: str,
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """제목 카테고리 매칭 (실패해도 저장은 계속)."""
        try:
            return await self._category_matcher.match_and_apply_to_title(
                title,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "대량수집 카테고리 매칭 오류 title='%s' err=%s",
                title[:30], exc,
            )
            return (None, None, None)


__all__ = ["ChunkProcessor", "ChunkStats"]
