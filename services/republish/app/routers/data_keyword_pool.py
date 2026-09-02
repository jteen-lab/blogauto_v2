"""데이터 관리 — 수집 키워드 풀(정본).

키워드 저장소를 `keyword_candidates` 로 일원화하면서, 데이터 관리 화면이
지표(검색량·월 발행량·포화도)와 판정을 보고 **기준값으로 직접 분류**할 수
있게 하는 API 다.

자동 모듈이 하는 일을 사람이 **같은 코드로** 돌린다(`pool_ops`). 다른 코드를
타면 자동에서만 나는 버그가 생긴다.

측정은 오래 걸린다(키워드당 검색 API 2회). 요청을 붙잡으면 프록시가 끊으므로
토큰을 주고 폴링하게 한다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-1
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models import User
from ..models.category import SubTopic, Topic
from ..models.keyword_candidate import KeywordCandidate
from ..models.user_settings import UserSettings
from ..routers.auth import get_current_user
from ..services.in_memory_ttl_cache import cache_get, cache_set
from ..services.keyword_lab import pool_ops

logger = get_logger("keyword_pool_router", "app.log")

router = APIRouter(prefix="/data/keyword-pool", tags=["data-keyword-pool"])

TASK_PREFIX = "keyword_pool_task:"
TASK_TTL = 1800.0

SORTABLE = {
    "keyword": KeywordCandidate.keyword,
    "search_volume": KeywordCandidate.search_volume,
    "monthly_pub_count": KeywordCandidate.monthly_pub_count,
    "doc_count": KeywordCandidate.doc_count,
    "saturation": KeywordCandidate.saturation,
    "verdict": KeywordCandidate.verdict,
    "created_at": KeywordCandidate.created_at,
}


def _task_key(task_id: str) -> str:
    return f"{TASK_PREFIX}{task_id}"


@router.get("/stats", summary="풀 현황")
async def pool_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """무엇이 얼마나 남았는지 — 미측정·미분류·판정별."""
    return await pool_ops.stats(db, current_user.id)


@router.get("", summary="수집 키워드 목록")
async def list_pool(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    classified: Optional[bool] = Query(None, description="분류 여부"),
    measured: Optional[bool] = Query(None, description="측정 여부"),
    sort_field: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """지표·판정과 함께 목록을 준다."""
    stmt = select(KeywordCandidate).where(
        KeywordCandidate.user_id == current_user.id)

    if search:
        stmt = stmt.where(KeywordCandidate.keyword.ilike(f"%{search}%"))
    if verdict:
        stmt = stmt.where(KeywordCandidate.verdict == verdict)
    if classified is True:
        stmt = stmt.where(or_(KeywordCandidate.topic_id.isnot(None),
                              KeywordCandidate.subtopic_id.isnot(None)))
    elif classified is False:
        stmt = stmt.where(KeywordCandidate.topic_id.is_(None),
                          KeywordCandidate.subtopic_id.is_(None))
    if measured is True:
        stmt = stmt.where(KeywordCandidate.measured_at.isnot(None))
    elif measured is False:
        stmt = stmt.where(KeywordCandidate.measured_at.is_(None))

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    column = SORTABLE.get(sort_field, KeywordCandidate.created_at)
    order = column.desc().nullslast() if sort_dir == "desc" \
        else column.asc().nullsfirst()
    rows = (await db.execute(
        stmt.order_by(order).offset((page - 1) * size).limit(size)
    )).scalars().all()

    return {
        "items": await _decorate(db, rows),
        "total": total, "page": page, "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


async def _decorate(db: AsyncSession,
                    rows: List[KeywordCandidate]) -> List[Dict[str, Any]]:
    """니치 이름을 붙인다. id 만 주면 화면에서 알아볼 수 없다."""
    topic_ids = {r.topic_id for r in rows if r.topic_id} or {0}
    sub_ids = {r.subtopic_id for r in rows if r.subtopic_id} or {0}
    topics = dict((await db.execute(
        select(Topic.id, Topic.name).where(Topic.id.in_(topic_ids)))).all())
    subs = dict((await db.execute(
        select(SubTopic.id, SubTopic.name).where(
            SubTopic.id.in_(sub_ids)))).all())

    def niche(row: KeywordCandidate) -> str:
        sub, top = subs.get(row.subtopic_id), topics.get(row.topic_id)
        if sub and top:
            return f"{top} > {sub}"
        return sub or top or "미분류"

    return [{
        "id": r.id, "keyword": r.keyword, "niche": niche(r),
        "topic_id": r.topic_id, "subtopic_id": r.subtopic_id,
        "search_volume": r.search_volume,
        "monthly_pub_count": r.monthly_pub_count,
        "doc_count": r.doc_count, "saturation": r.saturation,
        "competition": r.competition,
        "verdict": r.verdict, "verdict_reason": r.verdict_reason,
        "risk_label": r.risk_label, "intent": r.intent,
        "source": r.source, "titled": r.titled,
        "measured_at": r.measured_at.isoformat() if r.measured_at else None,
    } for r in rows]


@router.post("/classify", summary="미분류 키워드 분류")
async def classify_pool(
    limit: int = Body(500),
    retry_all: bool = Body(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """분류표로 카테고리를 붙인다. API 를 부르지 않아 빠르다.

    아직 안 훑은 것부터 가져간다. `retry_all` 은 분류표를 보강한 뒤
    지난 실패까지 다시 볼 때 쓴다.
    """
    return await pool_ops.classify(db, current_user.id,
                                   limit=max(1, min(5000, limit)),
                                   retry_all=retry_all)


@router.post("/rejudge", summary="기준값 재판정")
async def rejudge_pool(
    min_volume: Optional[int] = Body(None),
    max_volume: Optional[int] = Body(None),
    min_saturation: Optional[float] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """기준만 바꿔 다시 판정한다. API 를 부르지 않는다."""
    return await pool_ops.rejudge(db, current_user.id, min_volume,
                                  max_volume, min_saturation)


@router.post("/measure", summary="수요 보강 + 공급 측정 (백그라운드)")
async def measure_pool(
    limit: int = Body(50),
    min_volume: Optional[int] = Body(None),
    max_volume: Optional[int] = Body(None),
    min_saturation: Optional[float] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """검색량이 없는 것은 채우고, 공급을 잰다.

    키워드당 검색 API 2회라 오래 걸린다. 토큰을 주고 폴링하게 한다.
    """
    settings = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )).scalar_one_or_none()
    if not settings:
        raise HTTPException(400, "사용자 설정이 없습니다. API 키를 먼저 등록하세요")

    task_id = uuid.uuid4().hex
    asyncio.create_task(_measure_in_background(
        task_id, current_user.id, max(1, min(200, limit)),
        min_volume, max_volume, min_saturation))
    logger.info("[KEYWORD_POOL] 측정 시작 | %s | limit=%s", task_id, limit)
    return {"status": "running", "task_id": task_id}


async def _measure_in_background(task_id: str, user_id: int, limit: int,
                                 min_volume: Optional[int],
                                 max_volume: Optional[int],
                                 min_saturation: Optional[float]) -> None:
    """요청과 분리해 측정한다. 요청 세션은 응답과 함께 닫힌다."""
    from ..core.database import db_manager

    try:
        async with db_manager.get_session() as db:
            settings = (await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )).scalar_one_or_none()
            result = await pool_ops.measure(
                db, settings, user_id, limit=limit, min_volume=min_volume,
                max_volume=max_volume, min_saturation=min_saturation)
        cache_set(_task_key(task_id), {"status": "done", "result": result})
    except Exception as e:  # noqa: BLE001
        logger.error("[KEYWORD_POOL] 측정 오류 | %s | %s", task_id, e)
        cache_set(_task_key(task_id),
                  {"status": "failed", "error": str(e)[:300]})


@router.get("/task/{task_id}", summary="작업 결과 조회")
async def task_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    row = cache_get(_task_key(task_id), TASK_TTL)
    return row if row is not None else {"status": "running"}


@router.post("/delete", summary="선택 삭제")
async def delete_pool(
    ids: Optional[List[int]] = Body(None),
    verdict: Optional[str] = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """고른 것 또는 판정 전체를 지운다. 대상 없이 전체 삭제는 막는다."""
    if not ids and not verdict:
        raise HTTPException(422, "대상이 비어 있습니다")

    stmt = sa_delete(KeywordCandidate).where(
        KeywordCandidate.user_id == current_user.id)
    if ids:
        stmt = stmt.where(KeywordCandidate.id.in_(ids))
    if verdict:
        stmt = stmt.where(KeywordCandidate.verdict == verdict)

    result = await db.execute(stmt)
    await db.commit()
    return {"success": True, "deleted": result.rowcount or 0}
