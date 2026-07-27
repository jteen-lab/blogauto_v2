"""제목 카테고리 재분류(대량) — 백그라운드용 최적화 로직.

기존 엔드포인트는 제목마다 키워드 재정렬 + 개별 UPDATE로 수만 건에서
프록시 타임아웃(504)이 발생했다. 여기서는:
- 키워드를 1회만 로드·정렬
- 매칭 결과를 모아 청크 단위 executemany 벌크 UPDATE
로 처리한다. celery 태스크에서 호출된다.
"""
from typing import Any, Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.title import MainTitle, TempTitle
from .category_matcher_service import CategoryMatcherService

logger = get_logger("title_reclassify", "app.log")

_CHUNK = 1000


async def reclassify_titles(
    db: AsyncSession,
    target: str = "temp",
    force_all: bool = False,
    user_id: int = 1,
) -> Dict[str, Any]:
    """제목 카테고리 재분류(최적화).

    Args:
        db: DB 세션
        target: "temp"(임시) 또는 "main"(정식)
        force_all: True면 전체, False면 미분류(topic_id IS NULL)만
        user_id: 키워드 소유 사용자

    Returns:
        {"success": bool, "total": int, "matched": int}
    """
    model = MainTitle if target == "main" else TempTitle

    q = select(model.id, model.title)
    if not force_all:
        q = q.where(model.topic_id.is_(None))
    rows = (await db.execute(q)).all()
    if not rows:
        return {"success": True, "total": 0, "matched": 0}

    matcher = CategoryMatcherService(db, user_id=user_id)
    keywords = await matcher._load_keywords(force_reload=True)
    # 키워드는 1회만 정렬(우선순위 오름차순 → 길이 내림차순)
    sorted_kw = sorted(
        keywords, key=lambda x: (x["priority"], -x["keyword_length"])
    )

    updates = []
    for title_id, title_text in rows:
        text_lower = (title_text or "").lower()
        if len(text_lower.strip()) < 2:
            continue
        for kw in sorted_kw:
            if matcher._is_keyword_match(text_lower, kw["keyword"]):
                # SQLAlchemy 2.0 "ORM bulk update by PK": 각 레코드에 PK(id)와
                # 갱신 컬럼을 담아 update(model)로 executemany 한다(WHERE 불필요).
                row = {
                    "id": title_id,
                    "topic_id": kw["topic_id"],
                    "subtopic_id": kw["subtopic_id"],
                }
                if target == "temp":
                    row["matched_keyword_id"] = kw["keyword_id"]
                updates.append(row)
                break

    matched = len(updates)
    if matched:
        stmt = update(model)
        for i in range(0, matched, _CHUNK):
            await db.execute(stmt, updates[i:i + _CHUNK])
        await db.commit()

    logger.info(
        f"[RECLASSIFY] {target} force_all={force_all} | "
        f"전체 {len(rows)}개 중 {matched}개 매칭"
    )
    return {"success": True, "total": len(rows), "matched": matched}
