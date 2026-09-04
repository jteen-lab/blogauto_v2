"""재조합 결과 중복 검사 — 두 경로가 함께 쓴다.

재조합은 **관문 밖**에서 일어난다. 생성 파이프라인의 관문(금지어·분류·
유사도)은 재고를 만들 때 걸리고, 재조합은 그 뒤라 무검사였다.

정식제목 탭의 수동 재조합과 생성 프롬프트 모듈의 자동 재조합이 **같은
검사**를 써야 한다. 한쪽만 걸면 다른 쪽으로 중복이 새어 나간다.

계획서: docs/plans/title_tab_workplan.md §4-5 C
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.title import MainTitle

logger = get_logger("recombine_dedup", "app.log")

# 훑을 기존 제목 수. 전량 비교하면 한 건당 수천 번 비교하게 된다.
# 최근 것부터 본다 — 오래된 제목과 겹치는 일은 드물다.
SIMILARITY_SCAN = 500


def similarity_service() -> Any:
    """유사도 서비스. 못 불러오면 None — 검사를 건너뛰고 계속한다."""
    for path in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
    try:
        from services.similarity_service import SimilarityService

        return SimilarityService()
    except Exception as e:  # noqa: BLE001
        logger.warning("[RECOMBINE_DEDUP] 유사도 서비스 없음 | %s", e)
        return None


async def find_clash(db: AsyncSession, text: str,
                     origin: Any) -> Optional[str]:
    """이미 있는 제목과 겹치는가. 겹치면 그 제목을 돌려준다.

    같은 그룹 안은 원래 비슷한 것들이라 검사에서 뺀다 — 재조합 결과가
    원본과 닮은 것은 정상이다. 그룹 **밖**과 겹치는 것이 문제다.

    실패는 `None`(겹치지 않음)이다. 검사 때문에 생성이 멈추면 안 된다.
    """
    service = similarity_service()
    if service is None or not text:
        return None

    origin_group = getattr(origin, "group_id", None)
    origin_title = getattr(origin, "title", None)

    try:
        rows = (await db.execute(
            select(MainTitle.title, MainTitle.group_id)
            .where(MainTitle.status.in_(["available", "used"]))
            .order_by(MainTitle.id.desc())
            .limit(SIMILARITY_SCAN)
        )).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("[RECOMBINE_DEDUP] 조회 실패 | %s", e)
        return None

    for title, group_id in rows:
        if origin_group and group_id == origin_group:
            continue
        if not title or title == origin_title:
            continue
        try:
            verdict = service.calculate_similarity_v3(text, title)
        except Exception:  # noqa: BLE001
            continue
        if verdict.get("groupable"):
            return title
    return None
