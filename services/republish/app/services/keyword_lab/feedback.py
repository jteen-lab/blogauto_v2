"""성과 되먹임 — 내보낸 뒤 실제로 노출됐는지를 회수한다.

지금까지는 글을 내보내고 끝이었다. 잘 되는 축과 안 되는 축을 구분할 방법이
없으니 같은 실수를 반복한다.

두 신호를 쓴다.

1. **구글 서치콘솔 실측** — 그 키워드로 우리 글이 몇 번 노출됐고 평균 몇 위인가.
   추정이 아니라 사실이다.
2. **네이버 색인 확인** — 네이버에는 색인 API 가 없어 "검색에 잡히는가" 로
   대신한다(found/not_found).

점수는 다음 회차 **시드 우선순위**에 쓴다. 노출이 붙은 축은 더 파고,
계속 0인 축은 뒤로 민다.

계획서: docs/plans/keyword_module_redesign_plan.md §6-3
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate

logger = get_logger("keyword_feedback", "app.log")

KST = pytz.timezone("Asia/Seoul")

# 상위 몇 위 안이면 가산할지. 2페이지 안은 조금만 밀어도 유입이 붙는다.
GOOD_POSITION = 20.0

# 순위 가산 배수
POSITION_BONUS = 1.5

# 제목까지 만들었는데 노출이 하나도 없으면 0점을 적는다. NULL(미측정)과
# 구분해야 "확인했더니 없더라" 를 다음 판단에 쓸 수 있다.
NO_IMPRESSION_SCORE = 0.0

_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")


def norm(text: str) -> str:
    """비교용 정규화 — 공백·기호를 없애고 소문자로."""
    return _NON_WORD.sub("", (text or "").lower())


def score_of(impressions: int, position: Optional[float]) -> float:
    """노출과 순위로 점수를 만든다.

    노출이 기본이고, 상위권이면 가산한다. 노출 100회에 평균 80위인 것보다
    노출 40회에 평균 8위인 쪽이 더 살릴 만한 축이다.
    """
    base = float(max(0, impressions))
    if position is not None and 0 < position <= GOOD_POSITION:
        return round(base * POSITION_BONUS, 2)
    return round(base, 2)


def index_rows(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """실측 행을 정규화 키로 색인한다."""
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = norm(row.get("query", ""))
        if not key:
            continue
        current = out.get(key)
        if current is None or row.get("impressions", 0) > current.get(
                "impressions", 0):
            out[key] = row
    return out


class FeedbackCollector:
    """실측 성과를 후보 점수로 옮긴다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def apply(self, blog: Any, days: int = 28,
                    limit: int = 500) -> Dict[str, Any]:
        """이 블로그의 실측 성과를 후보에 반영한다.

        Args:
            blog: 대상 블로그
            days: 조회 기간(일)
            limit: 실측 행 상한

        Returns:
            {"matched": 점수 매긴 수, "zeroed": 노출 0으로 적은 수, ...}
        """
        from .sources.gsc import fetch_for_blog

        rows = await fetch_for_blog(self.db, blog, days, limit)
        if not rows:
            return {"matched": 0, "zeroed": 0,
                    "message": "서치콘솔 실측 데이터가 없습니다"}

        index = index_rows(rows)
        targets = await self._titled(blog)
        now = datetime.now(KST)
        matched, zeroed = 0, 0

        for row in targets:
            hit = index.get(norm(row.keyword))
            if hit:
                row.perf_score = score_of(hit.get("impressions", 0),
                                          hit.get("position"))
                matched += 1
            else:
                # 제목까지 만들었는데 노출이 없다. 미측정(NULL)과 구분한다.
                row.perf_score = NO_IMPRESSION_SCORE
                zeroed += 1
            row.perf_checked_at = now

        await self.db.commit()
        logger.info(
            "[KEYWORD_FEEDBACK] blog=%s | 실측 %d행 | 매칭 %d · 노출없음 %d",
            getattr(blog, "id", None), len(rows), matched, zeroed,
        )
        return {"matched": matched, "zeroed": zeroed, "rows": len(rows)}

    async def _titled(self, blog: Any) -> List[KeywordCandidate]:
        """제목까지 만든 키워드. 아직 안 쓴 키워드는 성과를 물을 수 없다."""
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.titled.is_(True)))
        if blog is not None:
            q = q.where(KeywordCandidate.blog_id == blog.id)
        return list((await self.db.execute(q)).scalars().all())
