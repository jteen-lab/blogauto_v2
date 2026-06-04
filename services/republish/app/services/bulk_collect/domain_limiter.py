"""
도메인별 Rate Limiter (Phase B)

대량 수집 모듈에서 같은 블로그 도메인에 동시 요청이 몰리지 않도록
- 전역 동시 요청 수
- 도메인 단위 동시 요청 수
를 함께 제한하는 비동기 컨텍스트 매니저를 제공한다.

사용 예:
    limiter = DomainLimiter(global_concurrency=20, per_domain_concurrency=2)
    async with limiter.acquire("example.com"):
        await client.get(url)

설계:
    - 전역 Semaphore 1개로 총 동시 호출 수를 제한
    - 도메인별 Semaphore 는 lazy init (도메인을 처음 보면 생성, 이후 캐시)
    - 락 보호된 dict 로 race condition 방지
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

logger = logging.getLogger(__name__)


class DomainLimiter:
    """전역 + 도메인별 동시 요청 수 제한기.

    Attributes:
        _global_sem: 전체 동시 호출 수 제한 세마포어.
        _per_domain_concurrency: 도메인당 최대 동시 호출 수.
        _domain_sems: 도메인별 세마포어 캐시 (lazy init).
        _dict_lock: `_domain_sems` 변경 보호용 비동기 락.
    """

    def __init__(
        self,
        global_concurrency: int,
        per_domain_concurrency: int,
    ) -> None:
        """리미터를 초기화한다.

        Args:
            global_concurrency: 전체 동시 호출 상한 (1 이상).
            per_domain_concurrency: 도메인당 동시 호출 상한 (1 이상).

        Raises:
            ValueError: 상한이 1 미만이면 발생.
        """
        if global_concurrency < 1:
            raise ValueError("global_concurrency 는 1 이상이어야 합니다")
        if per_domain_concurrency < 1:
            raise ValueError("per_domain_concurrency 는 1 이상이어야 합니다")

        self._global_sem: asyncio.Semaphore = asyncio.Semaphore(global_concurrency)
        self._per_domain_concurrency: int = per_domain_concurrency
        self._domain_sems: Dict[str, asyncio.Semaphore] = {}
        self._dict_lock: asyncio.Lock = asyncio.Lock()

        logger.debug(
            "DomainLimiter init global=%d per_domain=%d",
            global_concurrency, per_domain_concurrency,
        )

    async def _get_domain_sem(self, domain: str) -> asyncio.Semaphore:
        """도메인 세마포어 조회 (없으면 생성)."""
        # fast path: 락 없이 한 번 더 보기
        sem = self._domain_sems.get(domain)
        if sem is not None:
            return sem

        async with self._dict_lock:
            # 락 안에서 다시 확인 (다른 코루틴이 만들었을 수 있음)
            sem = self._domain_sems.get(domain)
            if sem is None:
                sem = asyncio.Semaphore(self._per_domain_concurrency)
                self._domain_sems[domain] = sem
                logger.debug(
                    "DomainLimiter 신규 도메인 세마포어 생성 domain=%s limit=%d",
                    domain, self._per_domain_concurrency,
                )
            return sem

    @asynccontextmanager
    async def acquire(self, domain: str) -> AsyncIterator[None]:
        """도메인에 대해 전역 + 도메인 세마포어를 동시에 획득한다.

        Args:
            domain: 대상 도메인(`urlparse(url).netloc` 등).

        Yields:
            None — 임계 구역 진입 표시.
        """
        if not domain:
            # 빈 도메인은 전역만으로 처리
            domain = "_unknown_"

        domain_sem = await self._get_domain_sem(domain)

        # 전역 먼저 잡고 도메인 잡는 순서로 데드락 위험 회피
        await self._global_sem.acquire()
        try:
            await domain_sem.acquire()
            try:
                yield
            finally:
                domain_sem.release()
        finally:
            self._global_sem.release()


__all__ = ["DomainLimiter"]
