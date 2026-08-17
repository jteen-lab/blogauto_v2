"""F8 — 발행 전 근접 중복(주제 중복) 게이트.

발행 직전, 같은 블로그에 이미 발행된 글 제목과 Jaccard 토큰 유사도를 비교해
근접 중복이면 발행을 차단한다(보수 임계값). 수집 단계의 정확일치 dedup
(``title_dedup``)이 못 거른 "거의 같은 제목"을 발행 직전에 막는 것이 목적이다.

계획서 F8, 순서도 ``docs/flowcharts/adsense_f8_publish_dedup.md``.
"""
from __future__ import annotations

import re
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.crawled_post import CrawledPost

logger = get_logger("topic_dedup_gate", "app.log")

# 보수 임계값: Jaccard 0.82(82%) 이상이면 근접 중복으로 차단.
# 수집 단계 정확일치 dedup을 보완해 '거의 동일한 제목'만 걸러 오차단을 최소화한다.
PUBLISH_DEDUP_THRESHOLD: float = 0.82
# 비교 대상 상한(성능 보호): 최근 발행 제목 N개까지만 비교.
PUBLISH_DEDUP_MAX_COMPARE: int = 800


def _tokenize(text: str) -> Set[str]:
    """제목 토큰화.

    ``similarity_matcher_service``와 동일 규칙: 특수문자 제거 → 소문자 →
    2자 이상 토큰만 유지(조사·접속사 등 제거 효과).
    """
    cleaned = re.sub(r"[^\w\s]", " ", text or "")
    return {tok for tok in cleaned.lower().split() if len(tok) >= 2}


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Jaccard 유사도 J(A,B) = |A∩B| / |A∪B| (0.0~1.0)."""
    if not set1 or not set2:
        return 0.0
    union = len(set1 | set2)
    return len(set1 & set2) / union if union else 0.0


async def check_topic_duplicate(
    db: AsyncSession,
    blog_id: int,
    title: str,
    exclude_post_id: Optional[int] = None,
    threshold: float = PUBLISH_DEDUP_THRESHOLD,
) -> Optional[str]:
    """근접 중복이면 사유 문자열, 아니면 None.

    같은 블로그의 발행완료 글(``CrawledPost.published_at IS NOT NULL``) 제목과
    Jaccard 유사도를 비교해 최고 점수가 임계값 이상이면 차단 사유를 반환한다.

    Args:
        db: 비동기 세션
        blog_id: 발행 대상 블로그 id
        title: 발행하려는 글 제목
        exclude_post_id: 비교에서 제외할 글 id(자기 자신)
        threshold: 차단 임계값(Jaccard, 0.0~1.0)

    Returns:
        차단 시 사유 문자열, 통과 시 None
    """
    tokens = _tokenize(title)
    if not tokens:
        return None

    stmt = (
        select(CrawledPost.id, CrawledPost.title)
        .where(CrawledPost.blog_id == blog_id)
        .where(CrawledPost.published_at.isnot(None))
        .order_by(CrawledPost.published_at.desc())
        .limit(PUBLISH_DEDUP_MAX_COMPARE)
    )
    rows = (await db.execute(stmt)).all()

    best_score = 0.0
    best_title = ""
    for post_id, post_title in rows:
        if exclude_post_id is not None and post_id == exclude_post_id:
            continue
        score = jaccard_similarity(tokens, _tokenize(post_title))
        if score > best_score:
            best_score = score
            best_title = post_title

    if best_score >= threshold:
        reason = (
            f"발행 전 중복 차단: 기존 발행글과 제목 유사도 {best_score * 100:.0f}% "
            f"(기준 {threshold * 100:.0f}%) — 유사 제목: \"{best_title}\""
        )
        logger.info(
            "[F8] 근접 중복 차단 | blog_id=%s | title=%s | score=%.2f | 유사=%s",
            blog_id, title, best_score, best_title,
        )
        return reason
    return None
