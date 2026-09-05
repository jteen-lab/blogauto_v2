"""글 성과 판정 — 이 글을 어떻게 할 것인가.

지금 재발행은 **날짜만** 본다. 주기가 오면 잘 되는 글도 갈아엎는다.
여기서 28일 추세를 읽어 글마다 동작을 다르게 정한다.

    유지    들어오는 사람이 유지된다 → 건드리지 않는다  ★ 지금 없는 선택지
    보강    들어오지만 줄고 있다     → 기존 글을 살려 확장
    제목    노출은 되는데 안 들어온다 → 제목·도입부만, 본문 유지
    재작성  노출도 유입도 없다        → 지금 동작

**데이터가 없으면 판정하지 않는다.** 없는 것을 0 으로 읽으면 "유입 없는 글" 이
되어 멀쩡한 글이 갈아엎힌다. 판정 불가는 legacy(지금 동작)로 돌려보낸다.

임계값은 설정으로 뺀다. 우리 데이터로 검증되지 않은 숫자를 코드에 박으면
근거 없는 상수가 된다.

계획서: docs/plans/analytics_integration_plan.md §6
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.post_metric import PostMetricDaily

logger = get_logger("analytics_performance", "app.log")

# 동작
ACT_KEEP = "keep"          # 건드리지 않는다
ACT_AUGMENT = "augment"    # 보강(기존 본문 확장)
ACT_TITLE = "title"        # 제목·도입부만
ACT_REWRITE = "rewrite"    # 전면 재작성
ACT_LEGACY = "legacy"      # 판단 근거 없음 → 지금 동작

# 기본 임계값. 업계 통용치를 출발점으로 삼는다.
DEFAULTS = {
    # 28일 세션이 직전 28일 대비 이만큼 빠지면 감쇠로 본다
    "decay_ratio": 0.20,
    # 노출은 되는데 안 들어오는 구간. 본문이 아니라 제목 문제일 확률이 높다.
    "ctr_position_min": 8.0,
    "ctr_position_max": 20.0,
    # 이만큼 쌓이지 않으면 판정하지 않는다
    "min_days": 14,
}


@dataclass
class Performance:
    """한 글의 28일 성적과 판정."""

    url_id: int
    action: str = ACT_LEGACY
    reason: str = ""
    sessions: int = 0
    prev_sessions: int = 0
    impressions: int = 0
    clicks: int = 0
    position: float = 0.0
    days: int = 0

    @property
    def decay(self) -> Optional[float]:
        """직전 28일 대비 증감률. 비교 대상이 없으면 None."""
        if not self.prev_sessions:
            return None
        return (self.sessions - self.prev_sessions) / self.prev_sessions

    def to_dict(self) -> Dict[str, Any]:
        return {"url_id": self.url_id, "action": self.action,
                "reason": self.reason, "sessions": self.sessions,
                "prev_sessions": self.prev_sessions,
                "impressions": self.impressions, "clicks": self.clicks,
                "position": self.position, "days": self.days,
                "decay": self.decay}


def decide_action(perf: Performance,
                  thresholds: Optional[dict] = None) -> Performance:
    """성적을 보고 동작을 정한다. 순수 함수 — 테스트가 쉬워야 한다.

    Args:
        perf: 집계된 성적
        thresholds: 임계값 덮어쓰기(블로그 설정)

    Returns:
        action·reason 이 채워진 같은 객체
    """
    cfg = {**DEFAULTS, **(thresholds or {})}

    if perf.days < cfg["min_days"]:
        perf.action = ACT_LEGACY
        perf.reason = f"데이터 {perf.days}일 — 판정 보류"
        return perf

    if perf.sessions > 0:
        decay = perf.decay
        if decay is not None and decay <= -abs(cfg["decay_ratio"]):
            perf.action = ACT_AUGMENT
            perf.reason = (f"세션 {perf.prev_sessions}→{perf.sessions} "
                           f"({int(decay * 100)}%) — 보강")
        else:
            perf.action = ACT_KEEP
            perf.reason = f"세션 {perf.sessions} 유지 — 건드리지 않음"
        return perf

    # 세션 0. 노출이 있으면 아직 살릴 여지가 있다.
    if perf.impressions > 0:
        if cfg["ctr_position_min"] <= perf.position <= cfg["ctr_position_max"]:
            perf.action = ACT_TITLE
            perf.reason = (f"노출 {perf.impressions} · 평균 {perf.position}위 "
                           "— 제목·도입부")
        else:
            perf.action = ACT_AUGMENT
            perf.reason = (f"노출 {perf.impressions} · 유입 0 · "
                           f"평균 {perf.position}위 — 보강")
        return perf

    perf.action = ACT_REWRITE
    perf.reason = "노출·유입 모두 0 — 재작성"
    return perf


async def evaluate(db: AsyncSession, url_id: int, window: int = 28,
                   thresholds: Optional[dict] = None) -> Performance:
    """URL 하나의 성적을 모아 판정한다."""
    today = date.today()
    cur_from = today - timedelta(days=window)
    prev_from = today - timedelta(days=window * 2)

    cur = await _sum(db, url_id, cur_from, today)
    prev = await _sum(db, url_id, prev_from, cur_from)

    perf = Performance(
        url_id=url_id,
        sessions=cur["sessions"], prev_sessions=prev["sessions"],
        impressions=cur["impressions"], clicks=cur["clicks"],
        position=cur["position"], days=cur["days"],
    )
    return decide_action(perf, thresholds)


async def _sum(db: AsyncSession, url_id: int, start: date,
               end: date) -> Dict[str, Any]:
    """기간 합계. 순위는 평균이다 — 합치면 뜻이 없다."""
    row = (await db.execute(
        select(
            func.coalesce(func.sum(PostMetricDaily.sessions), 0),
            func.coalesce(func.sum(PostMetricDaily.clicks), 0),
            func.coalesce(func.sum(PostMetricDaily.impressions), 0),
            func.coalesce(func.avg(PostMetricDaily.position), 0.0),
            func.count(PostMetricDaily.id),
        ).where(PostMetricDaily.url_id == url_id,
                PostMetricDaily.date >= start,
                PostMetricDaily.date < end)
    )).first()
    sessions, clicks, impressions, position, days = row or (0, 0, 0, 0.0, 0)
    return {"sessions": int(sessions or 0), "clicks": int(clicks or 0),
            "impressions": int(impressions or 0),
            "position": round(float(position or 0.0), 1),
            "days": int(days or 0)}


async def evaluate_blog(db: AsyncSession, blog_id: int, window: int = 28,
                        thresholds: Optional[dict] = None
                        ) -> List[Performance]:
    """블로그의 모든 글을 판정한다. 대시보드·일괄 재발행용."""
    url_ids = list((await db.execute(
        select(PostMetricDaily.url_id)
        .where(PostMetricDaily.blog_id == blog_id).distinct()
    )).scalars().all())
    return [await evaluate(db, uid, window, thresholds) for uid in url_ids]


def summarize(rows: List[Performance]) -> Dict[str, int]:
    """판정 분포. 한쪽으로 쏠리면 임계값을 다시 봐야 한다."""
    out = {ACT_KEEP: 0, ACT_AUGMENT: 0, ACT_TITLE: 0, ACT_REWRITE: 0,
           ACT_LEGACY: 0}
    for row in rows:
        out[row.action] = out.get(row.action, 0) + 1
    return out
