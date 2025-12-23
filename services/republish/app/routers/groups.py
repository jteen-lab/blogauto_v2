"""
그룹 라우터
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from .auth import get_current_user
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
from ..models import User
from ..schemas.group import (
    GroupCreateRequest, GroupUpdateRequest, 
    GroupResponse, GroupDetailResponse, GroupBlogAssignRequest
)
from ..services.group_service import GroupService
from ..core.logger import get_logger

logger = get_logger("groups_router", "app.log")

# API 라우터
router = APIRouter(prefix="/groups", tags=["groups"])

# 페이지 라우터
page_router = APIRouter(tags=["groups-pages"])


# ========== API 엔드포인트 ==========

@router.get("", response_model=List[GroupResponse])
async def get_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 목록 조회"""
    service = GroupService(db)
    groups = await service.get_user_groups(current_user)
    
    return [
        GroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            is_active=g.is_active,
            profile_count=len(g.profile_links),
            blog_count=len(g.blog_links),
            created_at=g.created_at,
            updated_at=g.updated_at
        )
        for g in groups
    ]


@router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 상세 조회"""
    service = GroupService(db)
    group = await service.get_group_by_id(current_user, group_id)
    
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
    
    return GroupDetailResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        profile_count=len(group.profile_links),
        blog_count=len(group.blog_links),
        created_at=group.created_at,
        updated_at=group.updated_at,
        profiles=[
            {"id": link.profile.id, "name": link.profile.name}
            for link in group.profile_links
        ],
        blogs=[
            {"id": link.blog.id, "name": link.blog.name}
            for link in group.blog_links
        ]
    )


@router.post("", response_model=GroupResponse)
async def create_group(
    data: GroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 생성"""
    service = GroupService(db)
    group = await service.create_group(current_user, data.model_dump())
    
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        profile_count=len(group.profile_links) if group.profile_links else 0,
        blog_count=len(group.blog_links) if group.blog_links else 0,
        created_at=group.created_at,
        updated_at=group.updated_at
    )


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    data: GroupUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 수정"""
    service = GroupService(db)
    try:
        group = await service.update_group(
            current_user, group_id, 
            data.model_dump(exclude_unset=True)
        )
        return GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            is_active=group.is_active,
            profile_count=len(group.profile_links) if group.profile_links else 0,
            blog_count=len(group.blog_links) if group.blog_links else 0,
            created_at=group.created_at,
            updated_at=group.updated_at
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 삭제"""
    service = GroupService(db)
    try:
        await service.delete_group(current_user, group_id)
        return {"success": True, "message": "그룹이 삭제되었습니다"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{group_id}/blogs")
async def assign_blogs(
    group_id: int,
    data: GroupBlogAssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹에 블로그 할당"""
    service = GroupService(db)
    try:
        group = await service.assign_blogs(current_user, group_id, data.blog_ids)
        return {"success": True, "blog_count": len(group.blog_links)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{group_id}/copy")
async def copy_group(
    group_id: int,
    new_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 복사"""
    service = GroupService(db)
    try:
        new_group = await service.copy_group(current_user, group_id, new_name)
        return {"success": True, "new_group_id": new_group.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== 페이지 엔드포인트 ==========

@page_router.get("/groups", response_class=HTMLResponse)
async def groups_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 목록 페이지"""
    service = GroupService(db)
    groups_raw = await service.get_user_groups(current_user)
    
    groups = [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "is_active": g.is_active,
            "profile_count": len(g.profile_links),
            "blog_count": len(g.blog_links),
            "created_at": g.created_at
        }
        for g in groups_raw
    ]
    
    return templates.TemplateResponse(
        "groups/list.html",
        {"request": request, "user": current_user, "groups": groups}
    )


@page_router.get("/groups/new", response_class=HTMLResponse)
async def new_group_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 생성 페이지"""
    from ..services.profile_service import ProfileService
    from ..services.blog_service import BlogService

    profile_service = ProfileService(db)
    blog_service = BlogService(db)

    profiles = await profile_service.get_user_profiles(current_user)
    blogs = await blog_service.get_user_blogs(current_user)

    return templates.TemplateResponse(
        "groups/form.html",
        {"request": request, "user": current_user, "group": None, "profiles": profiles, "blogs": blogs}
    )


@page_router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_page(
    request: Request,
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """그룹 수정 페이지"""
    from ..services.profile_service import ProfileService
    from ..services.blog_service import BlogService

    service = GroupService(db)
    group = await service.get_group_by_id(current_user, group_id)

    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

    profile_service = ProfileService(db)
    blog_service = BlogService(db)

    profiles = await profile_service.get_user_profiles(current_user)
    blogs = await blog_service.get_user_blogs(current_user)

    return templates.TemplateResponse(
        "groups/form.html",
        {"request": request, "user": current_user, "group": group, "profiles": profiles, "blogs": blogs}
    )
