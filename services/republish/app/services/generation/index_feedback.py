"""색인률을 발행량에 되먹인다.

검색 노출이 죽은 상태에서 계속 발행하면 신호가 더 나빠진다. 구글은 사이트
품질을 우려하면 크롤링과 색인을 함께 줄이는데(2026-07 John Mueller), 그때
발행을 유지하면 색인 안 되는 URL 만 쌓인다.

실제로 12개 블로그가 전부 색인 0건인 상태에서 하루 30개씩 발행하고 있었다.
색인 점검 기능은 있었지만 그 결과가 발행 결정에 전혀 반영되지 않았다.

**생성이 아니라 발행에 건다.** 구글이 보는 것은 발행된 글이고, 재고로
쌓인 글은 검색 신호에 영향이 없다. 생성까지 막았더니 재고가 비어, 색인이
회복돼도 낼 글이 없었다(2026-09-08 실측: 미발행 재고 0~3개).

진단: docs/plans/search_visibility_all_blogs.md
순서도: docs/flowcharts/index_feedback.md
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
# 정지는 따로 켠다. 실측(2026-09-08) 12개 블로그가 36~79일째 색인 0건이라
# 조건을 그대로 적용하면 전 블로그 발행이 한 번에 멈춘다. 멈출지는 운영
# 판단이므로 기본은 꺼 두고, 조건 충족 사실만 로그에 남긴다.
SETTING_STOP_KEY = "index_feedback_stop_enabled"


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
        f"{oldest_days}일간 색인 0건 — 발행을 멈춥니다. "
        "발행을 늘리기 전에 콘텐츠 품질 점검이 필요합니다",
    )


class IndexFeedback:
    """블로그의 색인 상태를 읽어 **발행** 상한을 정한다.

    생성은 보지 않는다. 구글이 보는 것은 발행된 글이고, 재고로 쌓인 글은
    검색 신호에 영향이 없다. 생성은 `min_inventory` 재고 상한이 이미 막는다.
    순서도: docs/flowcharts/index_feedback.md
    """

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
            ).where(
                SearchVisibilityUrl.blog_id == blog_id,
                SearchVisibilityUrl.index_state != "unknown",
                SearchVisibilityUrl.published_at >= since,
            )
        )).one()

        checked, indexed = row[0] or 0, row[1] or 0

        # 색인 0건일 때만, **창을 걷고** 첫 점검 글까지 거슬러 잰다.
        # 창(30일) 안에서 재면 값이 30을 넘을 수 없어 정지 조건이 영원히
        # 성립하지 않는다(2026-09-08 실측: 12개 블로그 전부 29일차).
        oldest_days = 0
        if checked and not indexed:
            oldest = (await self.db.execute(
                select(func.min(SearchVisibilityUrl.published_at)).where(
                    SearchVisibilityUrl.blog_id == blog_id,
                    SearchVisibilityUrl.index_state != "unknown",
                )
            )).scalar()
            if oldest:
                # PostgreSQL 은 aware, SQLite 는 naive 로 돌려준다.
                # 섞어서 빼면 TypeError 가 난다(052 에서 겪은 문제).
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                oldest_days = (datetime.now(timezone.utc) - oldest).days

        verdict = _verdict(checked, indexed, oldest_days, base_daily)
        if verdict.stop and not await stop_enabled(self.db):
            verdict = IndexVerdict(
                verdict.checked, verdict.indexed, verdict.ratio,
                CAP_POOR, False,
                f"{oldest_days}일간 색인 0건 — 하루 {CAP_POOR}개로 제한"
                f"(정지 조건 충족, 정지는 꺼져 있음)",
            )
        if verdict.cap is not None or verdict.stop:
            logger.info(
                "[INDEX_FEEDBACK] blog=%s | %s", blog_id, verdict.reason,
            )
        return verdict


def effective_cap(gp_daily: Optional[int],
                  verdict: Optional[IndexVerdict]) -> Optional[int]:
    """오늘 실제로 허용할 발행 수. 둘 중 작은 값이다.

    Args:
        gp_daily: 성장 프로파일이 정한 하루 발행 수
        verdict: 색인 되먹임 판정(None 이면 되먹임 꺼짐)

    Returns:
        상한. None 이면 제한 없음
    """
    caps = [c for c in (gp_daily, verdict.cap if verdict else None)
            if c is not None]
    return min(caps) if caps else None


def cap_note(gp_daily: Optional[int],
             verdict: Optional[IndexVerdict]) -> str:
    """왜 줄었는지 한 줄로. 막을 때는 사유를 반드시 남긴다.

    성장 프로파일 값과 실제 상한이 다르면 그 사실을 밝힌다. "제한" 이라고만
    쓰면 GP 설정이 무시된 것처럼 보인다.
    """
    if verdict is None or verdict.cap is None:
        return ""
    note = f" — {verdict.reason}"
    if gp_daily and gp_daily != verdict.cap:
        note += (f" · 성장 프로파일 {gp_daily}개 → "
                 f"되먹임 {verdict.cap}개")
    return note


async def stop_enabled(db: AsyncSession) -> bool:
    """정지까지 적용할지. **기본 꺼짐** — 켜면 해당 블로그 발행이 멈춘다."""
    from ..system_settings_service import SystemSettingsService

    raw = await SystemSettingsService.get(SETTING_STOP_KEY, db)
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "on", "yes")


async def is_enabled(db: AsyncSession) -> bool:
    """되먹임을 쓸지. 기본 켜짐 — 끄려면 명시적으로 꺼야 한다."""
    from ..system_settings_service import SystemSettingsService

    raw = await SystemSettingsService.get(SETTING_KEY, db)
    if raw is None or raw == "":
        return True
    return str(raw).lower() not in ("0", "false", "off", "no")
