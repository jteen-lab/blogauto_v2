"""
콘텐츠 필터 관리 API

Features:
- ContentFilter CRUD
- 시스템 필터 보호
- 페이지네이션
- 기존 데이터에 필터 적용 삭제
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.content_filter import ContentFilter
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/data/filters", tags=["data-filters"])
logger = get_logger("data_filters", "app.log")


# Pydantic Schemas
class FilterResponse(BaseModel):
    id: int
    name: str
    filter_type: str
    filter_value: str
    target_type: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool
    match_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FilterCreate(BaseModel):
    name: str
    filter_type: str = "keyword"
    filter_value: str
    target_type: str = "both"
    description: Optional[str] = None


class FilterUpdate(BaseModel):
    name: Optional[str] = None
    filter_type: Optional[str] = None
    filter_value: Optional[str] = None
    target_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FilterListResponse(BaseModel):
    items: List[FilterResponse]
    total: int
    page: int
    size: int
    has_next: bool


class FilterTypesResponse(BaseModel):
    filter_types: List[dict]
    target_types: List[dict]


class BulkFilterCreate(BaseModel):
    """대량 필터 등록"""
    filter_type: str = "keyword"
    filter_values: List[str]
    target_type: str = "both"


class BulkFilterDelete(BaseModel):
    """대량 필터 삭제"""
    ids: List[int]


# API Endpoints
@router.get("", response_model=FilterListResponse)
async def list_filters(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    filter_type: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    is_system: Optional[bool] = Query(None),
    sort_field: Optional[str] = Query("created_at", description="정렬 필드"),
    sort_dir: Optional[str] = Query("desc", description="정렬 방향 (asc/desc)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 목록 조회"""
    query = select(ContentFilter)

    # 필터 적용
    if search:
        query = query.where(
            ContentFilter.name.ilike(f"%{search}%") |
            ContentFilter.filter_value.ilike(f"%{search}%")
        )
    if filter_type:
        query = query.where(ContentFilter.filter_type == filter_type)
    if target_type:
        query = query.where(ContentFilter.target_type == target_type)
    if is_active is not None:
        query = query.where(ContentFilter.is_active == is_active)
    if is_system is not None:
        query = query.where(ContentFilter.is_system == is_system)

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 정렬 적용
    sort_columns = {
        "filter_value": ContentFilter.filter_value,
        "filter_type": ContentFilter.filter_type,
        "target_type": ContentFilter.target_type,
        "match_count": ContentFilter.match_count,
        "is_active": ContentFilter.is_active,
        "is_system": ContentFilter.is_system,
        "created_at": ContentFilter.created_at,
    }
    sort_column = sort_columns.get(sort_field, ContentFilter.created_at)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # 페이지네이션
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    filters = result.scalars().all()

    items = [FilterResponse.model_validate(f) for f in filters]

    return FilterListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        has_next=(page * size) < total
    )


@router.get("/types", response_model=FilterTypesResponse)
async def get_filter_types():
    """필터 타입 목록 조회"""
    return FilterTypesResponse(
        filter_types=[
            {"value": "keyword", "label": "키워드", "description": "키워드 포함 시 차단"},
            {"value": "pattern", "label": "패턴", "description": "정규식 패턴 매칭 시 차단"},
            {"value": "domain", "label": "도메인", "description": "특정 도메인 차단"},
        ],
        target_types=[
            {"value": "keyword", "label": "키워드만", "description": "키워드 수집 시에만 적용"},
            {"value": "title", "label": "제목만", "description": "제목 수집 시에만 적용"},
            {"value": "both", "label": "모두", "description": "키워드와 제목 모두 적용"},
        ]
    )


@router.post("", response_model=FilterResponse)
async def create_filter(
    data: FilterCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 생성"""
    # 중복 체크
    existing = await db.execute(
        select(ContentFilter).where(
            ContentFilter.filter_value == data.filter_value,
            ContentFilter.filter_type == data.filter_type
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 필터입니다")

    filter_obj = ContentFilter(
        name=data.name,
        filter_type=data.filter_type,
        filter_value=data.filter_value,
        target_type=data.target_type,
        description=data.description,
        is_system=False,  # 사용자 생성 필터
        is_active=True  # ★ 명시적으로 활성화 설정
    )
    db.add(filter_obj)
    await db.commit()
    await db.refresh(filter_obj)

    return FilterResponse.model_validate(filter_obj)


@router.post("/bulk-delete")
async def delete_filters_bulk(
    data: BulkFilterDelete,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 일괄 삭제 (시스템 필터 제외)"""
    deleted_count = 0
    skipped_count = 0

    for filter_id in data.ids:
        filter_obj = await db.get(ContentFilter, filter_id)
        if not filter_obj:
            continue
        if filter_obj.is_system:
            skipped_count += 1
            continue
        await db.delete(filter_obj)
        deleted_count += 1

    await db.commit()
    logger.info(f"[BULK_DELETE_FILTER] 삭제: {deleted_count}개, 스킵(시스템): {skipped_count}개")

    return {
        "deleted": deleted_count,
        "skipped": skipped_count,
        "message": f"{deleted_count}개 필터가 삭제되었습니다"
    }


@router.delete("/delete-all")
async def delete_all_filters(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """사용자 필터 전체 삭제 (시스템 필터 제외)"""
    # 사용자 필터만 카운트
    query = select(func.count()).select_from(ContentFilter).where(ContentFilter.is_system == False)
    total_before = (await db.execute(query)).scalar() or 0

    # 사용자 필터만 삭제
    from sqlalchemy import delete
    delete_query = delete(ContentFilter).where(ContentFilter.is_system == False)
    await db.execute(delete_query)
    await db.commit()

    logger.info(f"[DELETE_ALL_FILTER] 사용자 필터 전체 삭제: {total_before}개")

    return {
        "deleted": total_before,
        "message": f"{total_before}개 필터가 삭제되었습니다 (시스템 필터 제외)"
    }


@router.put("/{filter_id}", response_model=FilterResponse)
async def update_filter(
    filter_id: int,
    data: FilterUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 수정"""
    filter_obj = await db.get(ContentFilter, filter_id)
    if not filter_obj:
        raise HTTPException(status_code=404, detail="필터를 찾을 수 없습니다")

    # 시스템 필터는 활성화 상태만 변경 가능
    if filter_obj.is_system:
        if data.is_active is not None:
            filter_obj.is_active = data.is_active
        else:
            raise HTTPException(
                status_code=403,
                detail="시스템 필터는 활성화 상태만 변경할 수 있습니다"
            )
    else:
        if data.name is not None:
            filter_obj.name = data.name
        if data.filter_type is not None:
            filter_obj.filter_type = data.filter_type
        if data.filter_value is not None:
            filter_obj.filter_value = data.filter_value
        if data.target_type is not None:
            filter_obj.target_type = data.target_type
        if data.description is not None:
            filter_obj.description = data.description
        if data.is_active is not None:
            filter_obj.is_active = data.is_active

    await db.commit()
    await db.refresh(filter_obj)

    return FilterResponse.model_validate(filter_obj)


@router.delete("/{filter_id}")
async def delete_filter(
    filter_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 삭제"""
    filter_obj = await db.get(ContentFilter, filter_id)
    if not filter_obj:
        raise HTTPException(status_code=404, detail="필터를 찾을 수 없습니다")

    if filter_obj.is_system:
        raise HTTPException(status_code=403, detail="시스템 필터는 삭제할 수 없습니다")

    await db.delete(filter_obj)
    await db.commit()

    return {"message": "삭제되었습니다"}


@router.get("/stats")
async def get_filter_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 통계 조회"""
    total = (await db.execute(
        select(func.count()).select_from(ContentFilter)
    )).scalar() or 0

    active = (await db.execute(
        select(func.count()).select_from(ContentFilter).where(ContentFilter.is_active == True)
    )).scalar() or 0

    system_count = (await db.execute(
        select(func.count()).select_from(ContentFilter).where(ContentFilter.is_system == True)
    )).scalar() or 0

    user_count = (await db.execute(
        select(func.count()).select_from(ContentFilter).where(ContentFilter.is_system == False)
    )).scalar() or 0

    total_matches = (await db.execute(
        select(func.sum(ContentFilter.match_count))
    )).scalar() or 0

    return {
        "total": total,
        "active": active,
        "system": system_count,
        "user": user_count,
        "total_matches": total_matches
    }


@router.post("/bulk")
async def create_filters_bulk(
    data: BulkFilterCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """필터 대량 등록"""
    created_count = 0
    skipped_count = 0

    for filter_value in data.filter_values:
        filter_value = filter_value.strip()
        if not filter_value:
            continue

        # 중복 체크
        existing = await db.execute(
            select(ContentFilter).where(
                ContentFilter.filter_value == filter_value,
                ContentFilter.filter_type == data.filter_type
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue

        filter_obj = ContentFilter(
            name=filter_value,  # 필터명 = 필터값으로 자동 설정
            filter_type=data.filter_type,
            filter_value=filter_value,
            target_type=data.target_type,
            is_system=False,
            is_active=True  # ★ 명시적으로 활성화 설정
        )
        db.add(filter_obj)
        created_count += 1

    await db.commit()
    logger.info(f"[BULK_FILTER] 등록: {created_count}개, 중복 스킵: {skipped_count}개")

    return {"created": created_count, "skipped": skipped_count}


@router.post("/fix-null-active")
async def fix_null_active_filters(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    is_active가 NULL인 필터들을 True로 수정
    (기존 데이터 호환성 문제 해결용)
    """
    from sqlalchemy import update

    # NULL인 필터 수 확인
    null_count_query = select(func.count()).select_from(ContentFilter).where(
        ContentFilter.is_active.is_(None)
    )
    null_count = (await db.execute(null_count_query)).scalar() or 0

    if null_count == 0:
        return {"fixed": 0, "message": "수정이 필요한 필터가 없습니다"}

    # NULL → True로 업데이트
    update_query = (
        update(ContentFilter)
        .where(ContentFilter.is_active.is_(None))
        .values(is_active=True)
    )
    await db.execute(update_query)
    await db.commit()

    logger.info(f"[FIX_FILTER] is_active=NULL → True로 {null_count}개 수정")

    return {"fixed": null_count, "message": f"{null_count}개 필터가 활성화되었습니다"}


@router.post("/activate-all")
async def activate_all_filters(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    모든 필터를 활성화 (is_active=True)
    """
    from sqlalchemy import update

    # 비활성 필터 수 확인
    inactive_count_query = select(func.count()).select_from(ContentFilter).where(
        (ContentFilter.is_active == False) | (ContentFilter.is_active.is_(None))
    )
    inactive_count = (await db.execute(inactive_count_query)).scalar() or 0

    if inactive_count == 0:
        return {"activated": 0, "message": "모든 필터가 이미 활성화되어 있습니다"}

    # 전체 활성화
    update_query = (
        update(ContentFilter)
        .values(is_active=True)
    )
    await db.execute(update_query)
    await db.commit()

    logger.info(f"[ACTIVATE_ALL_FILTER] {inactive_count}개 필터 활성화")

    return {"activated": inactive_count, "message": f"{inactive_count}개 필터가 활성화되었습니다"}


@router.post("/remove-duplicates")
async def remove_duplicate_filters(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    중복 필터 수동 제거

    동일한 filter_value를 가진 필터 중 가장 오래된 것만 남기고 삭제합니다.
    시스템 필터는 삭제되지 않습니다.
    """
    # 1. 모든 사용자 필터 조회 (시스템 필터 제외)
    result = await db.execute(
        select(ContentFilter)
        .where(ContentFilter.is_system == False)
        .order_by(ContentFilter.created_at.asc())
    )
    all_filters = result.scalars().all()

    # 2. filter_value 기준으로 중복 찾기 (대소문자 무시, 가장 오래된 것 유지)
    seen = {}  # {lowercase_filter_value: first_id}
    duplicates_to_delete = []

    for f in all_filters:
        key = f.filter_value.strip().lower()
        if key in seen:
            # 중복 발견 - 나중에 추가된 것 삭제 대상
            duplicates_to_delete.append(f.id)
        else:
            seen[key] = f.id

    # 3. 중복 삭제
    deleted_count = 0
    for filter_id in duplicates_to_delete:
        filter_obj = await db.get(ContentFilter, filter_id)
        if filter_obj:
            await db.delete(filter_obj)
            deleted_count += 1

    await db.commit()

    logger.info(f"[DEDUP_FILTER] 수동 중복 제거: {deleted_count}개 삭제됨")

    return {
        "deleted": deleted_count,
        "total_before": len(all_filters),
        "total_after": len(all_filters) - deleted_count,
        "message": f"{deleted_count}개 중복 필터가 삭제되었습니다"
    }


@router.post(
    "/apply-to-existing",
    summary="기존 데이터에 필터 적용 삭제",
    description="활성 필터를 임시제목/시드키워드에 적용하여 매칭 항목을 삭제합니다",
)
async def apply_filters_to_existing(
    async_mode: bool = False,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """활성 필터를 기존 임시제목·시드키워드에 적용하여 매칭 항목 삭제.

    Args:
        async_mode: True 이면 Celery 워커로 디스패치 + task_id 반환 (Phase 3).
                    프론트는 /api/v1/tasks/{task_id} 로 폴링.
    """
    # Phase 3: 비동기 디스패치
    if async_mode:
        from ..core.celery_match_tasks import task_apply_filters
        task = task_apply_filters.delay()
        return {
            "async": True,
            "task_id": task.id,
            "state": "queued",
            "poll_url": f"/api/v1/tasks/{task.id}",
        }

    # 동기 (기존 동작)
    from ..services.filter_apply_service import apply_filters_to_existing_data

    result = await apply_filters_to_existing_data(db)
    return {
        "success": True,
        "deleted_titles": result.deleted_titles,
        "deleted_keywords": result.deleted_keywords,
        "message": (
            f"필터 적용 완료: 임시제목 {result.deleted_titles}건, "
            f"시드키워드 {result.deleted_keywords}건 삭제됨"
        ) if result.total > 0 else "활성 필터에 매칭되는 항목이 없습니다",
    }
