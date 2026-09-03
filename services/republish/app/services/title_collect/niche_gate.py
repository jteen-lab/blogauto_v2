"""저장 시점 니치 대조 — 세 번째 검사.

금지어 필터와 카테고리 분류는 **이미 동작하고 있다**(chunk_processor).
운영 필터 167개가 전부 `target_type='both'` 라 키워드·제목에 함께 걸린다.

그런데도 니치 무관 제목이 22,501건 쌓였다. 세 검사가 묻는 것이 다르기
때문이다.

    금지어 필터   "금지어가 들어 있나"          → 통과
    카테고리 분류 "어느 주제인가"                → 통과(주제 붙음)
    니치 대조     "그 주제를 쓰는 블로그가 있나" → **검사하지 않았다**

`쿠키런 킹덤 공략` 은 금지어가 없고 "게임" 으로 분류도 된다. 우리 블로그
중 게임을 쓰는 곳이 없으면 영원히 안 쓰이는 재고가 된다.

⚠️ 활성 카테고리가 하나도 없으면 **검사를 건너뛴다.** 카테고리를 아직 안
   붙인 상태에서 전량 차단되면 수집이 통째로 멈춘다. 임시제목 정리(B안)의
   가드와 같은 원칙이다.

계획서: docs/plans/title_tab_workplan.md §2-4
"""
from __future__ import annotations

from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import BlogCategory
from .settings import NICHE_BLOCK, NICHE_MARK

logger = get_logger("title_niche_gate", "app.log")

# 판정 결과
VERDICT_PASS = "pass"          # 우리 니치다
VERDICT_UNKNOWN = "unknown"    # 분류가 안 됐다 — 회수 큐로
VERDICT_OFF = "off_niche"      # 분류는 됐지만 쓰는 블로그가 없다
VERDICT_SKIP = "skipped"       # 판정 불가(활성 카테고리 없음)


class NicheGate:
    """활성 니치와 대조한다. 한 회차 동안 목록을 재사용한다."""

    def __init__(self, db: AsyncSession, mode: str = NICHE_MARK):
        self.db = db
        self.mode = mode
        self._topics: Optional[Set[int]] = None

    async def topics(self) -> Set[int]:
        """블로그가 실제로 쓰는 주제. 실패는 빈 집합(=판정 안 함)."""
        if self._topics is None:
            try:
                rows = (await self.db.execute(
                    select(BlogCategory.topic_id).where(
                        BlogCategory.is_active.is_(True),
                        BlogCategory.topic_id.is_not(None))
                )).scalars().all()
                self._topics = {t for t in rows if t}
            except Exception as e:  # noqa: BLE001
                logger.warning("[NICHE_GATE] 활성 니치 조회 실패 | %s", e)
                self._topics = set()
        return self._topics

    async def judge(self, topic_id: Optional[int]) -> str:
        """이 주제가 우리 니치인가."""
        active = await self.topics()
        if not active:
            return VERDICT_SKIP
        if topic_id is None:
            return VERDICT_UNKNOWN
        return VERDICT_PASS if topic_id in active else VERDICT_OFF

    async def should_store(self, topic_id: Optional[int]) -> bool:
        """저장할 것인가.

        `mark` 모드는 무관해도 저장한다 — 무엇이 걸러졌는지 보이는 편이
        낫고, 되돌릴 수 있다. `block` 모드에서만 버린다.
        """
        if self.mode != NICHE_BLOCK:
            return True
        return await self.judge(topic_id) != VERDICT_OFF
