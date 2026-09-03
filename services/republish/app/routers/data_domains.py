"""니치 도메인 API — 데이터 관리의 '도메인' 탭.

옛 'URL 수집' 탭을 대체한다. URL 12만 건은 소비되지 않았고, 실제로
쓸 수 있는 정보는 **"이 니치에서 누가 상위에 있는가"** 였다(alembic 066).

각도 조회(`title_gen/angles.py`)가 여기 활성 도메인만 참조한다.

계획서: docs/plans/title_pipeline_redesign_plan.md §2-3
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.niche_domain import NicheDomain
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/domains", tags=["data-domains"])
logger = get_logger("data_domains", "app.log")

SORTABLE = {"url_count", "domain", "last_seen_at", "created_at",
            "extracted_count", "promoted_count", "deleted_title_count"}


class DomainResponse(BaseModel):
    """도메인 한 건."""

    id: int
    domain: str
    platform: str
    url_count: int
    is_active: bool
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    extract_status: str = "pending"
    extracted_count: int = 0
    promoted_count: int = 0
    deleted_title_count: int = 0
    # 승격률. 표본이 적으면 None — 화면은 '-' 로 표시한다.
    quality_score: Optional[float] = None
    sample_titles: List[str] = []
    top_keywords: List[str] = []
    last_seen_at: Optional[str] = None


class DomainListResponse(BaseModel):
    items: List[DomainResponse]
    total: int
    page: int
    size: int
    has_next: bool


class DomainStatsResponse(BaseModel):
    total: int
    active: int
    urls_summarized: int
    blocked: int = 0
    pending_extract: int = 0


class IdsRequest(BaseModel):
    ids: List[int]


def _to_response(row: NicheDomain) -> DomainResponse:
    """모델 → 응답. 줄바꿈으로 붙여 둔 샘플을 목록으로 편다."""
    return DomainResponse(
        id=row.id, domain=row.domain, platform=row.platform,
        url_count=row.url_count, is_active=row.is_active,
        is_blocked=bool(row.is_blocked), blocked_reason=row.blocked_reason,
        extract_status=row.extract_status or "pending",
        extracted_count=row.extracted_count or 0,
        promoted_count=row.promoted_count or 0,
        deleted_title_count=row.deleted_title_count or 0,
        quality_score=row.quality_score(),
        sample_titles=row.titles()[:5], top_keywords=row.keywords()[:5],
        last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
    )


@router.get("", response_model=DomainListResponse)
async def list_domains(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_blocked: Optional[bool] = Query(None),
    extract_status: Optional[str] = Query(None),
    sort_field: str = Query("url_count"),
    sort_dir: str = Query("desc"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DomainListResponse:
    """도메인 목록. 기본 정렬은 관측 수 — 존재감이 큰 곳이 위로."""
    query = select(NicheDomain).where(NicheDomain.user_id == current_user.id)
    if search:
        query = query.where(NicheDomain.domain.ilike(f"%{search}%"))
    if platform:
        query = query.where(NicheDomain.platform == platform)
    if is_active is not None:
        query = query.where(NicheDomain.is_active == is_active)
    if is_blocked is not None:
        query = query.where(NicheDomain.is_blocked == is_blocked)
    if extract_status:
        query = query.where(NicheDomain.extract_status == extract_status)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery()))).scalar() or 0

    field = sort_field if sort_field in SORTABLE else "url_count"
    column = getattr(NicheDomain, field)
    query = query.order_by(column.asc() if sort_dir == "asc" else column.desc())
    query = query.offset((page - 1) * size).limit(size)

    rows = (await db.execute(query)).scalars().all()
    return DomainListResponse(
        items=[_to_response(r) for r in rows], total=total, page=page,
        size=size, has_next=(page * size) < total)


@router.get("/stats", response_model=DomainStatsResponse)
async def domain_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DomainStatsResponse:
    """탭 상단 요약."""
    mine = NicheDomain.user_id == current_user.id
    total = (await db.execute(
        select(func.count()).select_from(NicheDomain).where(mine))).scalar() or 0
    active = (await db.execute(
        select(func.count()).select_from(NicheDomain)
        .where(mine, NicheDomain.is_active.is_(True)))).scalar() or 0
    urls = (await db.execute(
        select(func.coalesce(func.sum(NicheDomain.url_count), 0))
        .where(mine))).scalar() or 0
    from ..models.niche_domain import EXTRACT_PARTIAL, EXTRACT_PENDING

    blocked = (await db.execute(
        select(func.count()).select_from(NicheDomain)
        .where(mine, NicheDomain.is_blocked.is_(True)))).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(NicheDomain).where(
            mine, NicheDomain.is_blocked.is_(False),
            NicheDomain.extract_status.in_(
                [EXTRACT_PENDING, EXTRACT_PARTIAL])))).scalar() or 0
    return DomainStatsResponse(total=total, active=active,
                               urls_summarized=int(urls),
                               blocked=int(blocked),
                               pending_extract=int(pending))


@router.post("/{domain_id}/toggle")
async def toggle_domain(
    domain_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """각도 조회 대상에서 넣고 뺀다. 스팸·무관 사이트를 끌 때 쓴다."""
    row = (await db.execute(
        select(NicheDomain).where(NicheDomain.id == domain_id,
                                  NicheDomain.user_id == current_user.id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="도메인을 찾을 수 없습니다")

    row.is_active = not row.is_active
    await db.commit()
    logger.info("[DOMAINS] 토글 | %s → %s", row.domain, row.is_active)
    return {"success": True, "is_active": row.is_active}


@router.post("/bulk-toggle")
async def bulk_toggle(
    payload: IdsRequest,
    active: bool = Query(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """선택한 도메인을 한 번에 켜거나 끈다."""
    if not payload.ids:
        return {"success": True, "updated": 0}
    result = await db.execute(
        update(NicheDomain)
        .where(NicheDomain.id.in_(payload.ids),
               NicheDomain.user_id == current_user.id)
        .values(is_active=active))
    await db.commit()
    return {"success": True, "updated": result.rowcount or 0}


@router.post("/bulk-delete")
async def bulk_delete(
    payload: IdsRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """선택 삭제. 다시 관측되면 새로 쌓인다."""
    if not payload.ids:
        return {"success": True, "deleted": 0}
    result = await db.execute(
        delete(NicheDomain).where(NicheDomain.id.in_(payload.ids),
                                  NicheDomain.user_id == current_user.id))
    await db.commit()
    logger.info("[DOMAINS] 삭제 %s건 | user=%s", result.rowcount,
                current_user.id)
    return {"success": True, "deleted": result.rowcount or 0}
