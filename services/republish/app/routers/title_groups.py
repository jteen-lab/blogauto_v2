"""
제목 그룹 API

Features:
- TitleGroup CRUD
- 그룹 관리 (대표 변경, 추가/제거, 병합)
- 페이지네이션, 검색, 필터링
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.title import MainTitle, TitleGroup
from ..models.user import User
from ..routers.auth import get_current_user
from ..schemas.title import (
    MainTitleResponse,
    TitleGroupCreate,
    TitleGroupUpdate,
    TitleGroupResponse,
    TitleGroupListResponse,
    TitleGroupWithTitles,
    ChangeRepresentativeRequest,
    AddToGroupRequest,
    RemoveFromGroupRequest,
    MergeGroupsRequest,
)

router = APIRouter(prefix="/title-groups", tags=["title-groups"])
logger = get_logger("title_groups", "app.log")


async def _build_group_items(
    db: AsyncSession, groups: list
) -> List[TitleGroupResponse]:
    """그룹 ORM 목록을 응답 스키마로 변환.

    주의: TitleGroupResponse.model_validate(g)로 ORM을 직접 검증하면
    스키마 필드 representative_title 가 ORM 지연로딩 관계를 건드려
    async 컨텍스트에서 MissingGreenlet(500)이 발생한다. 대표 제목을
    배치 조회한 뒤 명시 dict로 구성한다.
    """
    rep_ids = [g.representative_title_id for g in groups if g.representative_title_id]
    reps: dict = {}
    if rep_ids:
        rep_rows = (await db.execute(
            select(MainTitle.id, MainTitle.title).where(MainTitle.id.in_(rep_ids))
        )).all()
        reps = {rid: title for rid, title in rep_rows}

    return [
        TitleGroupResponse.model_validate({
            "id": g.id,
            "group_uuid": g.group_uuid,
            "name": g.name,
            "description": g.description,
            "category_id": g.category_id,
            "location": g.location,
            "main_keyword": g.main_keyword,
            "is_active": g.is_active,
            "representative_title_id": g.representative_title_id,
            "representative_title": reps.get(g.representative_title_id),
            "member_count": g.member_count or 0,
            "created_at": g.created_at,
            "updated_at": g.updated_at,
        })
        for g in groups
    ]


async def _group_counts(db: AsyncSession, base) -> tuple:
    """전체 그룹(제목 1개 포함) / 매칭 그룹(제목 2개+) 카운트 계산."""
    all_count = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0
    matched_count = (await db.execute(
        select(func.count()).select_from(
            base.where(TitleGroup.member_count >= 2).subquery()
        )
    )).scalar() or 0
    return all_count, matched_count


@router.get("", response_model=TitleGroupListResponse)
async def list_title_groups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="그룹명 검색"),
    is_active: Optional[bool] = Query(None),
    min_members: Optional[int] = Query(
        None, ge=1, description="최소 멤버 수 필터(예: 2 = 매칭 그룹만)"
    ),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 그룹 목록 조회.

    min_members=2 지정 시 매칭 그룹(제목 2개+)만 반환. all_count/
    matched_count는 페이지네이션과 무관하게 동일 필터 기준으로 계산.
    """
    base = select(TitleGroup)
    if category_id:
        base = base.where(TitleGroup.category_id == category_id)
    if search:
        base = base.where(TitleGroup.name.ilike(f"%{search}%"))
    if is_active is not None:
        base = base.where(TitleGroup.is_active == is_active)

    all_count, matched_count = await _group_counts(db, base)

    # 목록 쿼리(min_members 반영)
    list_q = base
    if min_members is not None:
        list_q = list_q.where(TitleGroup.member_count >= min_members)
    total = (await db.execute(
        select(func.count()).select_from(list_q.subquery())
    )).scalar() or 0

    list_q = list_q.order_by(TitleGroup.created_at.desc())
    list_q = list_q.offset((page - 1) * size).limit(size)
    groups = (await db.execute(list_q)).scalars().all()

    items = await _build_group_items(db, groups)

    return TitleGroupListResponse(
        items=items, total=total, page=page, size=size,
        has_next=(page * size) < total,
        all_count=all_count, matched_count=matched_count,
    )


@router.get("/{group_id}", response_model=TitleGroupWithTitles)
async def get_title_group(
    group_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 그룹 상세 조회 (그룹 내 제목 포함)"""
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    # 대표 제목 조회
    representative_title = None
    if group.representative_title_id:
        rep = await db.get(MainTitle, group.representative_title_id)
        representative_title = rep.title if rep else None

    # 그룹 내 제목 목록 조회 (대표 제목이 항상 맨 위)
    titles_query = select(MainTitle).where(MainTitle.group_id == group_id).order_by(
        MainTitle.is_group_representative.desc(),  # 대표 제목 우선
        MainTitle.created_at.desc()  # 그 다음 최신순
    )
    titles_result = await db.execute(titles_query)
    titles = titles_result.scalars().all()
    title_responses = [MainTitleResponse.model_validate(t) for t in titles]

    # 수동으로 응답 구성 (비동기 문제 방지)
    response = TitleGroupWithTitles(
        id=group.id,
        group_uuid=group.group_uuid,
        name=group.name,
        description=group.description,
        category_id=group.category_id,
        location=group.location,
        main_keyword=group.main_keyword,
        is_active=group.is_active,
        representative_title_id=group.representative_title_id,
        representative_title=representative_title,
        member_count=group.member_count or 0,
        created_at=group.created_at,
        updated_at=group.updated_at,
        titles=title_responses,
    )

    return response


@router.post("", response_model=TitleGroupResponse)
async def create_title_group(
    data: TitleGroupCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 그룹 생성"""
    group = TitleGroup(
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        location=data.location,
        main_keyword=data.main_keyword,
        is_active=data.is_active,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)

    logger.info(f"[CREATE_GROUP] 그룹 생성: {group.id} - {group.name}")
    return TitleGroupResponse.model_validate(group)


@router.put("/{group_id}", response_model=TitleGroupResponse)
async def update_title_group(
    group_id: int,
    data: TitleGroupUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 그룹 수정"""
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    if data.name is not None:
        group.name = data.name
    if data.description is not None:
        group.description = data.description
    if data.category_id is not None:
        group.category_id = data.category_id
    if data.location is not None:
        group.location = data.location
    if data.main_keyword is not None:
        group.main_keyword = data.main_keyword
    if data.representative_title_id is not None:
        group.representative_title_id = data.representative_title_id
    if data.is_active is not None:
        group.is_active = data.is_active

    await db.commit()
    await db.refresh(group)

    return TitleGroupResponse.model_validate(group)


@router.delete("/{group_id}")
async def delete_title_group(
    group_id: int,
    ungroup_titles: bool = Query(True, description="제목들을 미그룹으로 변경"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """제목 그룹 삭제"""
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    if ungroup_titles:
        titles_query = select(MainTitle).where(MainTitle.group_id == group_id)
        result = await db.execute(titles_query)
        titles = result.scalars().all()
        for t in titles:
            t.group_id = None
            t.is_group_representative = False
            t.similarity_score = None
            t.grouped_at = None

    await db.delete(group)
    await db.commit()

    return {"message": "그룹이 삭제되었습니다"}


# ============ 그룹 관리 API ============

@router.put("/{group_id}/representative")
async def change_representative(
    group_id: int,
    data: ChangeRepresentativeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """그룹 대표 제목 변경 및 유사도 재계산"""
    import sys
    import os
    # shared 서비스 경로 추가
    _shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
    for _path in _shared_paths:
        if os.path.exists(_path) and _path not in sys.path:
            sys.path.insert(0, _path)
            break
    from services.similarity_service import SimilarityService

    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    new_rep = await db.get(MainTitle, data.new_representative_id)
    if not new_rep:
        raise HTTPException(status_code=404, detail="제목을 찾을 수 없습니다")

    if new_rep.group_id != group_id:
        raise HTTPException(status_code=400, detail="해당 제목은 이 그룹에 속하지 않습니다")

    # 기존 대표 해제
    if group.representative_title_id:
        old_rep = await db.get(MainTitle, group.representative_title_id)
        if old_rep:
            old_rep.is_group_representative = False

    # 새 대표 설정
    new_rep.is_group_representative = True
    new_rep.similarity_score = None  # 대표는 유사도 없음
    group.representative_title_id = new_rep.id

    # 그룹 내 모든 멤버의 유사도를 새 대표 기준으로 재계산
    titles_query = select(MainTitle).where(MainTitle.group_id == group_id)
    titles_result = await db.execute(titles_query)
    titles = titles_result.scalars().all()

    similarity_service = SimilarityService()
    for title in titles:
        if title.id == new_rep.id:
            continue  # 대표는 건너뜀
        # 새 대표와의 유사도 계산
        result = similarity_service.calculate_similarity_v3(title.title, new_rep.title)
        title.similarity_score = result["score"]

    await db.commit()

    logger.info(f"[CHANGE_REP] 그룹 {group_id} 대표 변경: {new_rep.id}, 유사도 재계산 완료")
    return {"message": "대표 제목이 변경되었습니다", "new_representative_id": new_rep.id}


@router.post("/{group_id}/add")
async def add_titles_to_group(
    group_id: int,
    data: AddToGroupRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """그룹에 제목 추가"""
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    added = 0
    for title_id in data.title_ids:
        title = await db.get(MainTitle, title_id)
        if not title:
            continue
        title.group_id = group_id
        title.grouped_at = datetime.utcnow()
        added += 1

    group.update_member_count()
    await db.commit()

    logger.info(f"[ADD_TO_GROUP] 그룹 {group_id}에 {added}개 제목 추가")
    return {"message": f"{added}개 제목이 그룹에 추가되었습니다", "added": added}


@router.post("/{group_id}/remove")
async def remove_titles_from_group(
    group_id: int,
    data: RemoveFromGroupRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """그룹에서 제목 제거"""
    group = await db.get(TitleGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    removed = 0
    for title_id in data.title_ids:
        title = await db.get(MainTitle, title_id)
        if not title or title.group_id != group_id:
            continue

        if title.is_group_representative:
            group.representative_title_id = None
            title.is_group_representative = False

        title.group_id = None
        title.similarity_score = None
        title.grouped_at = None
        removed += 1

    group.update_member_count()
    await db.commit()

    logger.info(f"[REMOVE_FROM_GROUP] 그룹 {group_id}에서 {removed}개 제목 제거")
    return {"message": f"{removed}개 제목이 그룹에서 제거되었습니다", "removed": removed}


@router.post("/merge")
async def merge_groups(
    data: MergeGroupsRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """여러 그룹을 하나로 병합"""
    target = await db.get(TitleGroup, data.target_group_id)
    if not target:
        raise HTTPException(status_code=404, detail="대상 그룹을 찾을 수 없습니다")

    merged_count = 0
    titles_moved = 0

    for source_id in data.source_group_ids:
        if source_id == data.target_group_id:
            continue

        source = await db.get(TitleGroup, source_id)
        if not source:
            continue

        titles_query = select(MainTitle).where(MainTitle.group_id == source_id)
        result = await db.execute(titles_query)
        titles = result.scalars().all()

        for t in titles:
            t.group_id = data.target_group_id
            t.is_group_representative = False
            titles_moved += 1

        await db.delete(source)
        merged_count += 1

    target.update_member_count()
    await db.commit()

    logger.info(f"[MERGE_GROUPS] {merged_count}개 그룹 병합 → {data.target_group_id}")
    return {
        "message": f"{merged_count}개 그룹이 병합되었습니다",
        "merged_groups": merged_count,
        "titles_moved": titles_moved
    }
