"""수집 키워드 풀 작업 — 측정·분류·재판정.

데이터 관리 키워드 탭이 정본(`keyword_candidates`)을 다루면서 필요한
일괄 작업을 모은다. 모듈이 자동으로 하는 일을 **사람이 같은 코드로**
직접 돌릴 수 있어야 한다. 다른 코드를 타면 자동에서만 나는 버그가 생긴다.

세 가지 일:
    측정  검색량 없는 것은 검색광고로 채우고, 공급(월 발행량)을 잰다
    분류  미분류 키워드에 카테고리를 붙인다
    재판정 기준값만 바꿔 다시 판정한다(API 호출 없음)

이관된 옛 시드는 **검색량조차 없다**(seed_keywords 에 지표 컬럼이 없었다).
그래서 측정은 공급만 재는 것이 아니라 수요 보강부터 한다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from datetime import datetime

import pytz
from sqlalchemy import func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from .scoring import Thresholds, judge

logger = get_logger("keyword_pool", "app.log")

KST = pytz.timezone("Asia/Seoul")

# 한 번에 처리할 기본 건수. 네이버 검색광고는 5개씩, 검색은 키워드당 2회다.
DEFAULT_MEASURE_LIMIT = 50
DEFAULT_CLASSIFY_LIMIT = 500


async def stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """풀 현황 — 무엇이 남았는지 한눈에."""
    total = (await db.execute(
        select(func.count(KeywordCandidate.id))
        .where(KeywordCandidate.user_id == user_id)
    )).scalar() or 0

    by_verdict = dict((await db.execute(
        select(KeywordCandidate.verdict, func.count(KeywordCandidate.id))
        .where(KeywordCandidate.user_id == user_id)
        .group_by(KeywordCandidate.verdict)
    )).all())

    unmeasured = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(
            KeywordCandidate.user_id == user_id,
            KeywordCandidate.measured_at.is_(None))
    )).scalar() or 0

    no_volume = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(
            KeywordCandidate.user_id == user_id,
            KeywordCandidate.search_volume.is_(None))
    )).scalar() or 0

    unclassified = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(
            KeywordCandidate.user_id == user_id,
            KeywordCandidate.topic_id.is_(None),
            KeywordCandidate.subtopic_id.is_(None))
    )).scalar() or 0

    return {
        "total": total,
        "by_verdict": by_verdict,
        "unmeasured": unmeasured,
        "no_volume": no_volume,
        "unclassified": unclassified,
    }


async def classify(db: AsyncSession, user_id: int,
                   limit: int = DEFAULT_CLASSIFY_LIMIT,
                   retry_all: bool = False) -> Dict[str, Any]:
    """미분류 키워드에 카테고리를 붙인다. API 를 부르지 않는다.

    **아직 안 훑은 것부터** 가져간다. 분류기는 결정적이라 안 붙은 것을
    다시 훑어도 결과가 같다 — 시도 기록이 없으면 같은 앞부분만 반복해서
    훑고 진행이 없다(실제로 "훑음 2000건" 이 반복됐다).

    분류표에 없는 말은 미분류로 남는다. 그 목록이 곧 분류표에 무엇이
    빠졌는지 알려 준다.

    Args:
        db: DB 세션
        user_id: 사용자
        limit: 이번에 훑을 최대 건수
        retry_all: 분류표를 보강한 뒤 처음부터 다시 훑을 때 True

    Returns:
        {"scanned", "matched", "unmatched", "remaining", "unclassified",
         "message"}
    """
    from ..category_matcher_service import CategoryMatcherService

    if retry_all:
        # 분류표가 자랐다. 지난 실패를 다시 본다.
        await db.execute(
            sa_update(KeywordCandidate)
            .where(KeywordCandidate.user_id == user_id,
                   KeywordCandidate.topic_id.is_(None),
                   KeywordCandidate.subtopic_id.is_(None))
            .values(classify_tried_at=None))
        await db.commit()

    base = [KeywordCandidate.user_id == user_id,
            KeywordCandidate.topic_id.is_(None),
            KeywordCandidate.subtopic_id.is_(None)]

    rows = (await db.execute(
        select(KeywordCandidate)
        .where(*base, KeywordCandidate.classify_tried_at.is_(None))
        .order_by(KeywordCandidate.id)
        .limit(limit)
    )).scalars().all()

    unclassified = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(*base))).scalar() or 0

    if not rows:
        message = ("미분류 키워드가 없습니다" if not unclassified else
                   f"남은 {unclassified:,}건은 이미 다 훑었습니다 — "
                   "분류표에 없는 말입니다. 분류표를 보강한 뒤 "
                   "'처음부터 다시 분류' 를 쓰세요")
        return {"scanned": 0, "matched": 0, "unmatched": 0, "remaining": 0,
                "unclassified": unclassified, "message": message}

    matcher = CategoryMatcherService(db, user_id)
    now = datetime.now(KST)
    matched = 0
    for row in rows:
        row.classify_tried_at = now      # 실패한 것도 기록한다
        try:
            topic_id, subtopic_id, _ = \
                await matcher.match_and_apply_to_keyword(row.keyword)
        except Exception as e:  # noqa: BLE001
            logger.warning("[KEYWORD_POOL] 분류 실패 | %s | %s", row.keyword, e)
            continue
        if topic_id or subtopic_id:
            row.topic_id, row.subtopic_id = topic_id, subtopic_id
            matched += 1

    await db.commit()

    remaining = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(
            *base, KeywordCandidate.classify_tried_at.is_(None))
    )).scalar() or 0

    logger.info("[KEYWORD_POOL] 분류 | 훑음 %d · 매칭 %d · 남은 %d",
                len(rows), matched, remaining)
    return {"scanned": len(rows), "matched": matched,
            "unmatched": len(rows) - matched, "remaining": remaining,
            "unclassified": max(0, unclassified - matched)}


async def rejudge(db: AsyncSession, user_id: int,
                  min_volume: Optional[int] = None,
                  max_volume: Optional[int] = None,
                  min_saturation: Optional[float] = None) -> Dict[str, Any]:
    """기준값만 바꿔 다시 판정한다. API 를 부르지 않는다."""
    th = Thresholds.build(min_volume, min_saturation, max_volume)
    rows = (await db.execute(
        select(KeywordCandidate).where(KeywordCandidate.user_id == user_id)
    )).scalars().all()

    for row in rows:
        row.verdict, row.verdict_reason, row.risk_label = judge(
            row.keyword, row.search_volume, row.doc_count, th,
            monthly_pub_count=row.monthly_pub_count)

    await db.commit()
    tally: Dict[str, int] = {}
    for row in rows:
        tally[row.verdict] = tally.get(row.verdict, 0) + 1
    logger.info("[KEYWORD_POOL] 재판정 %d건 | %s", len(rows), tally)
    return {"total": len(rows), "by_verdict": tally,
            "thresholds": {"min_volume": th.min_volume,
                           "max_volume": th.max_volume,
                           "min_saturation": th.min_saturation}}


async def measure(db: AsyncSession, user_settings: Any, user_id: int,
                  limit: int = DEFAULT_MEASURE_LIMIT,
                  min_volume: Optional[int] = None,
                  max_volume: Optional[int] = None,
                  min_saturation: Optional[float] = None,
                  window_days: int = 30) -> Dict[str, Any]:
    """수요를 채우고 공급을 잰다.

    1) 검색량이 없는 키워드에 검색광고 검색량을 채운다(이관분이 여기 해당)
    2) 아직 공급을 안 잰 키워드의 월 발행량·문서수를 잰다

    Returns:
        {"enriched": 채운 수, "measured": 잰 수, "remaining": 남은 수}
    """
    from .service import KeywordLabService

    enriched = await _enrich_volumes(db, user_settings, user_id, limit)

    svc = KeywordLabService(db, user_settings, user_id)
    measured = await svc.measure(
        limit=limit, min_volume=min_volume, max_volume=max_volume,
        min_saturation=min_saturation, window_days=window_days)

    remaining = (await db.execute(
        select(func.count(KeywordCandidate.id)).where(
            KeywordCandidate.user_id == user_id,
            or_(KeywordCandidate.measured_at.is_(None),
                KeywordCandidate.search_volume.is_(None)))
    )).scalar() or 0

    return {"enriched": enriched,
            "measured": measured.get("measured", 0),
            "failed": measured.get("failed", 0),
            "error": measured.get("error"),
            "remaining": remaining}


async def _enrich_volumes(db: AsyncSession, user_settings: Any, user_id: int,
                          limit: int) -> int:
    """검색량이 비어 있는 키워드를 검색광고로 채운다.

    이관된 옛 시드는 지표가 아예 없어서, 이 단계를 안 거치면 판정이
    영원히 "검색량 미측정" 에 머문다.
    """
    from .sources.base import SRC_NAVER_ADS, KeywordIdea
    from .sources.registry import enrich_volumes

    rows = (await db.execute(
        select(KeywordCandidate).where(
            KeywordCandidate.user_id == user_id,
            KeywordCandidate.search_volume.is_(None),
        ).limit(limit)
    )).scalars().all()
    if not rows:
        return 0

    ideas = [KeywordIdea(keyword=r.keyword, source=SRC_NAVER_ADS)
             for r in rows]
    result = await enrich_volumes(user_settings, ideas, limit=limit)

    found = {i.keyword.replace(" ", "").lower(): i
             for i in ideas if i.search_volume is not None}
    filled = 0
    for row in rows:
        idea = found.get(row.keyword.replace(" ", "").lower())
        if idea is None:
            continue
        row.search_volume = idea.search_volume
        row.search_volume_pc = idea.search_volume_pc
        row.search_volume_mobile = idea.search_volume_mobile
        row.competition = idea.competition
        filled += 1

    await db.commit()
    logger.info("[KEYWORD_POOL] 검색량 보강 %d/%d | API 오류 %s",
                filled, len(rows), result.get("errors") or "없음")
    return filled
