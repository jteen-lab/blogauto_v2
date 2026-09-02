"""발견(Discovery) — 시드 없이 "지금 무엇을 찾는가" 를 잡는다.

확장(Expansion)과 입력이 근본적으로 다르다.

    발견  입력 없음 → 세상이 지금 찾는 말
    확장  시드 필요 → 이 주제의 가지

기존 수집 모듈은 둘을 한 덩어리로 두고, 발견에도 시드를 요구하는 API 를
쓰느라 시드를 코드에 박아 넣었다(`건강/맛집/여행…`). 그래서 취업 블로그에
"맛집" 이 들어왔다.

**확인된 API 제약**: 네이버 데이터랩은 연관 키워드를 주지 않는다. 시드
키워드의 트렌드 지표만 준다(`collect_trending_keywords` 주석). 그러므로
데이터랩은 발견 소스가 아니라 **검증(트렌드 확인) 소스**다. 시드 없는 발견은
구글 트렌드 실시간 인기 검색어가 맡는다.

발견 결과는 니치와 무관한 말이 섞이므로 **반드시 니치 필터를 통과시킨다.**

계획서: docs/plans/keyword_pipeline_restructure_review.md §3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....core.logger import get_logger
from .base import KeywordIdea, normalize

logger = get_logger("keyword_discovery", "app.log")

SRC_GOOGLE_TRENDING = "google_trending"
SRC_NAVER_DATALAB = "naver_datalab"

DISCOVERY_SOURCES = (SRC_GOOGLE_TRENDING, SRC_NAVER_DATALAB)

# 데이터랩 트렌드 점수 하한. 이보다 낮으면 지금 아무도 안 찾는다.
MIN_TREND_SCORE = 1


async def google_trending(limit: int = 50) -> List[KeywordIdea]:
    """구글 실시간 인기 검색어. **시드가 필요 없는 유일한 발견 소스다.**

    검색량은 주지 않으므로 비워 둔다 — 뒤의 보강 단계가 채운다.
    """
    from ...google_trends_service import GoogleTrendsService

    try:
        result = await GoogleTrendsService().get_trending_searches(
            country="south_korea")
    except Exception as e:  # noqa: BLE001
        logger.warning("[DISCOVERY] 구글 트렌드 실패 | %s", e)
        return []

    if not result.get("success"):
        logger.warning("[DISCOVERY] 구글 트렌드 실패 | %s", result.get("error"))
        return []

    out: List[KeywordIdea] = []
    for row in result.get("trending") or []:
        raw = row.get("keyword") if isinstance(row, dict) else row
        keyword = normalize(str(raw or ""))
        if not keyword:
            continue
        out.append(KeywordIdea(keyword=keyword, source=SRC_GOOGLE_TRENDING,
                               engine="google"))
        if len(out) >= limit:
            break
    logger.info("[DISCOVERY] 구글 실시간 인기 %d개", len(out))
    return out


async def datalab_scores(user_settings: Any, keywords: List[str],
                         limit: int = 50) -> Dict[str, int]:
    """데이터랩 트렌드 점수. **발견이 아니라 검증이다.**

    데이터랩은 연관 키워드를 주지 않으므로 새 키워드를 못 만든다. 이미 가진
    키워드가 지금 뜨는지 확인하는 데만 쓴다.

    Returns:
        {키워드: 트렌드 점수}
    """
    from ...naver_datalab_service import NaverDatalabService

    service = NaverDatalabService(user_settings)
    if not service.is_configured() or not keywords:
        return {}

    try:
        result = await service.collect_trending_keywords(
            keywords[:limit], max_keywords=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("[DISCOVERY] 데이터랩 실패 | %s", e)
        return {}

    if not result.get("success"):
        return {}

    scores = {}
    for row in result.get("keywords") or []:
        keyword = (row.get("keyword") or "").strip()
        score = row.get("trend_score")
        if keyword and score is not None:
            scores[keyword] = int(score)
    logger.info("[DISCOVERY] 데이터랩 점수 %d개", len(scores))
    return scores


async def filter_by_niche(db: Any, user_id: int, ideas: List[KeywordIdea],
                          blog: Any = None) -> Dict[str, Any]:
    """발견 결과에서 우리 니치에 맞는 것만 남긴다.

    이 필터가 없으면 취업 블로그에 "맛집" 이 들어온다. 실제로 기존 수집이
    그랬다.

    판정 기준
        블로그가 있으면 → 그 블로그의 활성 카테고리에 걸리는 것만
        블로그가 없으면 → 분류표에 걸리는 것만(어느 니치든 우리 것)

    Returns:
        {"kept": [KeywordIdea], "dropped": int}
    """
    from ...category_matcher_service import CategoryMatcherService

    allowed = await _blog_categories(db, blog) if blog is not None else None
    matcher = CategoryMatcherService(db, user_id)

    kept: List[KeywordIdea] = []
    for idea in ideas:
        try:
            topic_id, subtopic_id, _ = \
                await matcher.match_and_apply_to_keyword(idea.keyword)
        except Exception:  # noqa: BLE001
            continue
        if not (topic_id or subtopic_id):
            continue        # 분류표에 없는 말 = 우리 니치가 아니다
        if allowed is not None and subtopic_id not in allowed \
                and topic_id not in allowed:
            continue
        idea.extra["topic_id"] = topic_id
        idea.extra["subtopic_id"] = subtopic_id
        kept.append(idea)

    dropped = len(ideas) - len(kept)
    logger.info("[DISCOVERY] 니치 필터 | 통과 %d · 제외 %d", len(kept), dropped)
    return {"kept": kept, "dropped": dropped}


async def _blog_categories(db: Any, blog: Any) -> Optional[set]:
    """블로그의 활성 카테고리 id 집합. 없으면 None(제한 없음)."""
    from sqlalchemy import select

    from ....models.category import BlogCategory

    rows = (await db.execute(
        select(BlogCategory.topic_id, BlogCategory.subtopic_id).where(
            BlogCategory.blog_id == blog.id,
            BlogCategory.is_active.is_(True))
    )).all()
    ids = {v for row in rows for v in row if v}
    return ids or None
