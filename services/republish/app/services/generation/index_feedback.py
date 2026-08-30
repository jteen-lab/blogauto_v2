"""색인률을 발행량에 되먹인다.

검색 노출이 죽은 상태에서 계속 발행하면 신호가 더 나빠진다. 구글은 사이트
품질을 우려하면 크롤링과 색인을 함께 줄이는데(2026-07 John Mueller), 그때
발행을 유지하면 색인 안 되는 URL 만 쌓인다.

실제로 12개 블로그가 전부 색인 0건인 상태에서 하루 30개씩 발행하고 있었다.
색인 점검 기능은 있었지만 그 결과가 발행 결정에 전혀 반영되지 않았다.

진단: docs/plans/search_visibility_all_blogs.md
순서도: docs/flowcharts/index_feedback_and_quality_gate.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.search_visibility import SearchVisibilityUrl

logger = get_logger("index_feedback", "app.log")

# 최근 며칠치 발행분을 볼 것인가
WINDOW_DAYS = 30
# 이 미만이면 판단하지 않는다. 새 블로그는 점검 이력이 없어 색인률이 0으로
# 보이는데, 그걸로 막으면 시작조차 못 한다.
MIN_SAMPLE = 5

# 색인률 구간별 일일 발행 상한 (None = 상한 없음)
TIER_HEALTHY = 0.30      # 이상이면 제한 없음
TIER_WEAK = 0.10         # 이상이면 절반
CAP_WEAK_RATIO = 0.5
CAP_POOR = 1             # 10% 미만이면 하루 1개
# 0% 가 이 기간 이어지면 생성을 멈춘다
STOP_AFTER_DAYS = 30

SETTING_KEY = "index_feedback_enabled"


@dataclass
class IndexVerdict:
    """색인 상태에 따른 발행 제한 판정."""

    checked: int            # 점검된 URL 수
    indexed: int            # 그중 색인된 수
    ratio: Optional[float]  # 색인률(표본 부족이면 None)
    cap: Optional[int]      # 일일 발행 상한(None = 제한 없음)
    stop: bool              # 생성 자체를 멈출지
    reason: str             # 사용자에게 보여줄 사유

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checked": self.checked, "indexed": self.indexed,
            "ratio": self.ratio, "cap": self.cap,
            "stop": self.stop, "reason": self.reason,
        }


def _verdict(checked: int, indexed: int, oldest_days: int,
             base_daily: Optional[int]) -> IndexVerdict:
    """숫자만으로 판정한다(DB 없이 테스트 가능하도록 분리)."""
    if checked < MIN_SAMPLE:
        return IndexVerdict(
            checked, indexed, None, None, False,
            f"색인 점검 표본 부족({checked}건) — 제한 없음",
        )

    ratio = indexed / checked

    if ratio >= TIER_HEALTHY:
        return IndexVerdict(
            checked, indexed, ratio, None, False,
            f"색인률 {ratio*100:.0f}% — 정상",
        )

    if ratio >= TIER_WEAK:
        cap = max(1, int((base_daily or 2) * CAP_WEAK_RATIO))
        return IndexVerdict(
            checked, indexed, ratio, cap, False,
            f"색인률 {ratio*100:.0f}% — 발행량을 {cap}개로 줄임",
        )

    if ratio > 0:
        return IndexVerdict(
            checked, indexed, ratio, CAP_POOR, False,
            f"색인률 {ratio*100:.0f}% — 하루 {CAP_POOR}개로 제한",
        )

    # 색인 0건. 기간이 짧으면 아직 기다려 볼 수 있다.
    if oldest_days < STOP_AFTER_DAYS:
        return IndexVerdict(
            checked, indexed, 0.0, CAP_POOR, False,
            f"색인 0건({oldest_days}일차) — 하루 {CAP_POOR}개로 제한",
        )
    return IndexVerdict(
        checked, indexed, 0.0, 0, True,
        f"{oldest_days}일간 색인 0건 — 생성을 멈춥니다. "
        "발행을 늘리기 전에 콘텐츠 품질 점검이 필요합니다",
    )


class IndexFeedback:
    """블로그의 색인 상태를 읽어 발행 상한을 정한다."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self, blog_id: int, base_daily: Optional[int] = None,
    ) -> IndexVerdict:
        """최근 발행분의 색인률로 판정한다."""
        since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

        row = (await self.db.execute(
            select(
                func.count(SearchVisibilityUrl.id),
                func.count(SearchVisibilityUrl.id).filter(
                    SearchVisibilityUrl.index_state == "indexed"),
                func.min(SearchVisibilityUrl.published_at),
            ).where(
                SearchVisibilityUrl.blog_id == blog_id,
                SearchVisibilityUrl.index_state != "unknown",
                SearchVisibilityUrl.published_at >= since,
            )
        )).one()

        checked, indexed, oldest = row[0] or 0, row[1] or 0, row[2]
        oldest_days = 0
        if oldest:
            # PostgreSQL 은 aware, SQLite 는 naive 로 돌려준다.
            # 섞어서 빼면 TypeError 가 난다(052 에서 겪은 문제).
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            oldest_days = (datetime.now(timezone.utc) - oldest).days

        verdict = _verdict(checked, indexed, oldest_days, base_daily)
        if verdict.cap is not None or verdict.stop:
            logger.info(
                "[INDEX_FEEDBACK] blog=%s | %s", blog_id, verdict.reason,
            )
        return verdict


async def is_enabled(db: AsyncSession) -> bool:
    """되먹임을 쓸지. 기본 켜짐 — 끄려면 명시적으로 꺼야 한다."""
    from ..system_settings_service import SystemSettingsService

    raw = await SystemSettingsService.get(SETTING_KEY, db)
    if raw is None or raw == "":
        return True
    return str(raw).lower() not in ("0", "false", "off", "no")
