"""
타임박스 (Phase B)

대량 수집 사이클이 미리 정해진 최대 시간(초)을 넘기면
중단할 수 있도록 시간 만료 여부를 알려주는 단순 컨텍스트 매니저.

사용 예:
    with Timebox(max_seconds=900) as tb:
        while not tb.expired:
            await do_some_work()
        logger.info("경과: %.1f초", tb.elapsed)

설계:
    - `time.monotonic()` 사용 (시스템 시계 변경 영향 X)
    - 컨텍스트 매니저로 사용해도 되고, 단순 인스턴스로 사용해도 동작.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class Timebox:
    """최대 실행 시간을 추적하는 단순 타이머.

    Attributes:
        max_seconds: 허용된 최대 실행 시간 (초).
        _start: monotonic 시작 시각. `__enter__` 또는 `start()` 호출 시 세팅.
    """

    def __init__(self, max_seconds: int) -> None:
        """
        Args:
            max_seconds: 0 이하면 ValueError. 양수면 그 초만큼 허용.
        """
        if max_seconds <= 0:
            raise ValueError("max_seconds 는 양수여야 합니다")
        self.max_seconds: int = max_seconds
        self._start: Optional[float] = None

    # ------------------------------------------------------------------
    # 컨텍스트 매니저
    # ------------------------------------------------------------------

    def __enter__(self) -> "Timebox":
        """`with` 진입 시 타이머 시작."""
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """`with` 종료 시 별도 처리 없음 (로깅만)."""
        if self._start is not None:
            logger.debug(
                "Timebox 종료 elapsed=%.2fs max=%ds expired=%s",
                self.elapsed, self.max_seconds, self.expired,
            )

    # ------------------------------------------------------------------
    # 명시적 제어
    # ------------------------------------------------------------------

    def start(self) -> None:
        """타이머를 (재)시작한다."""
        self._start = time.monotonic()

    # ------------------------------------------------------------------
    # 상태 프로퍼티
    # ------------------------------------------------------------------

    @property
    def elapsed(self) -> float:
        """경과 시간(초). 시작 전이라면 0.0."""
        if self._start is None:
            return 0.0
        return time.monotonic() - self._start

    @property
    def remaining(self) -> float:
        """남은 시간(초). 만료되었으면 0.0 또는 음수가 아닌 0.0."""
        rem = self.max_seconds - self.elapsed
        return max(rem, 0.0)

    @property
    def expired(self) -> bool:
        """이미 max_seconds를 초과했는지 여부."""
        if self._start is None:
            return False
        return self.elapsed >= self.max_seconds


__all__ = ["Timebox"]
