"""기존 수집 모듈이 새 정본에도 함께 적도록 잇는다.

키워드 저장소를 `keyword_candidates` 로 일원화했지만, 기존 수집 모듈
(`keyword_collector_service`)은 아직 `seed_keywords` 에 쓴다. 전환 도중에
새로 들어온 키워드가 데이터 관리 화면에서 안 보이면 안 되므로, 저장할 때
양쪽에 적는다(전환기 이중 기록).

전환이 끝나면(계획서 S6) 기존 모듈이 이 다리만 쓰게 하고 seed_keywords
쓰기를 걷어낸다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §6
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate, VERDICT_PENDING

logger = get_logger("keyword_bridge", "app.log")

# 전역 풀(특정 블로그에 매인 것이 아닌 수집 키워드)
GLOBAL_BLOG_ID = None


async def mirror_keyword(
    db: AsyncSession, keyword: str, source: str,
    user_id: int = 1,
    topic_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
) -> bool:
    """수집된 키워드를 정본(전역 풀)에도 적는다.

    지표는 비운 채(미측정) 넣는다. 측정 회차가 나중에 채운다.

    Args:
        db: DB 세션(호출자가 커밋한다)
        keyword: 키워드
        source: 어느 소스에서 왔는지
        user_id: 소유자
        topic_id: 분류된 주제(있으면)
        subtopic_id: 분류된 하위 주제(있으면)

    Returns:
        새로 적었으면 True, 이미 있으면 False
    """
    text = (keyword or "").strip()
    if not text:
        return False

    exists = (await db.execute(
        select(KeywordCandidate.id).where(
            KeywordCandidate.user_id == user_id,
            KeywordCandidate.blog_id.is_(None),
            func.lower(KeywordCandidate.keyword) == text.lower(),
        ).limit(1)
    )).first()
    if exists:
        return False

    db.add(KeywordCandidate(
        user_id=user_id,
        keyword=text,
        blog_id=GLOBAL_BLOG_ID,
        topic_id=topic_id,
        subtopic_id=subtopic_id,
        verdict=VERDICT_PENDING,
        verdict_reason="수집됨 — 아직 재지 않음",
        source=(source or "collect")[:30],
    ))
    return True
