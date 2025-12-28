"""
플로우 라우터

Features:
- 플로우 CRUD 작업
- 모듈/블로그 독립적 추가/삭제
- 슬롯 검증 포함
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models import User
from ..services.flow_service import FlowService
from ..schemas.flow import (
    FlowCreateRequest,
    FlowUpdateRequest,
    FlowModuleAddRequest,
    FlowBlogAddRequest,
    FlowDetailResponse,
    FlowListResponse,
    BlogAddResult
)
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("flows_router", "app.log")

router = APIRouter(prefix="/flows", tags=["flows"])


@router.get(
    "",
    response_model=FlowListResponse,
    summary="플로우 목록 조회",
    description="사용자의 플로우 목록을 조회합니다. 상태별 필터링과 페이지네이션을 지원합니다."
)
async def get_flows(
    status: Optional[str] = Query(None, description="플로우 상태 필터 (active/inactive/paused)"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowListResponse:
    """플로우 목록 조회"""
    service = FlowService(db)
    return await service.get_flows(current_user, page, size)


@router.post(
    "",
    response_model=FlowDetailResponse,
    status_code=201,
    summary="플로우 생성",
    description="새로운 플로우를 생성합니다."
)
async def create_flow(
    request: FlowCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 생성"""
    service = FlowService(db)
    flow = await service.create_flow(current_user, request)

    # 응답용 데이터 구성
    response_data = FlowDetailResponse.model_validate(flow)
    response_data.module_count = len(flow.flow_modules) if flow.flow_modules else 0
    response_data.blog_count = len(flow.flow_blogs) if flow.flow_blogs else 0

    return response_data


@router.get(
    "/{flow_id}",
    response_model=FlowDetailResponse,
    summary="플로우 상세 조회",
    description="특정 플로우의 상세 정보를 조회합니다."
)
async def get_flow(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 상세 조회"""
    service = FlowService(db)
    flow = await service.get_flow(current_user, flow_id)

    if not flow:
        raise HTTPException(
            status_code=404,
            detail="플로우를 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    response_data = FlowDetailResponse.model_validate(flow)
    response_data.module_count = len(flow.flow_modules) if flow.flow_modules else 0
    response_data.blog_count = len(flow.flow_blogs) if flow.flow_blogs else 0

    return response_data


@router.put(
    "/{flow_id}",
    response_model=FlowDetailResponse,
    summary="플로우 수정",
    description="기존 플로우의 정보를 수정합니다."
)
async def update_flow(
    flow_id: int,
    request: FlowUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 수정"""
    service = FlowService(db)
    flow = await service.update_flow(current_user, flow_id, request)

    if not flow:
        raise HTTPException(
            status_code=404,
            detail="플로우를 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    response_data = FlowDetailResponse.model_validate(flow)
    response_data.module_count = len(flow.flow_modules) if flow.flow_modules else 0
    response_data.blog_count = len(flow.flow_blogs) if flow.flow_blogs else 0

    return response_data


@router.delete(
    "/{flow_id}",
    status_code=204,
    summary="플로우 삭제",
    description="플로우를 삭제합니다. 연결된 모든 모듈과 블로그 관계도 해제됩니다."
)
async def delete_flow(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우 삭제"""
    service = FlowService(db)
    success = await service.delete_flow(current_user, flow_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="플로우를 찾을 수 없습니다"
        )


# ===========================================
# 모듈 관리 (독립적)
# ===========================================

@router.post(
    "/{flow_id}/modules",
    response_model=FlowDetailResponse,
    summary="플로우에 모듈 추가",
    description="기존 플로우에 모듈을 추가합니다. 이미 추가된 모듈은 무시됩니다."
)
async def add_modules_to_flow(
    flow_id: int,
    request: FlowModuleAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우에 모듈 추가"""
    service = FlowService(db)
    flow = await service.add_modules(current_user, flow_id, request)

    if not flow:
        raise HTTPException(
            status_code=404,
            detail="플로우를 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    response_data = FlowDetailResponse.model_validate(flow)
    response_data.module_count = len(flow.flow_modules) if flow.flow_modules else 0
    response_data.blog_count = len(flow.flow_blogs) if flow.flow_blogs else 0

    return response_data


@router.delete(
    "/{flow_id}/modules/{module_id}",
    status_code=204,
    summary="플로우에서 모듈 제거",
    description="플로우에서 특정 모듈을 제거합니다."
)
async def remove_module_from_flow(
    flow_id: int,
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우에서 모듈 제거"""
    service = FlowService(db)
    success = await service.remove_module(current_user, flow_id, module_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="모듈 연결을 찾을 수 없습니다"
        )


# ===========================================
# 블로그 관리 (독립적, 슬롯 검증 포함)
# ===========================================

@router.post(
    "/{flow_id}/blogs",
    response_model=BlogAddResult,
    summary="플로우에 블로그 추가",
    description="기존 플로우에 블로그를 추가합니다. Blogger 플랫폼의 경우 슬롯 검증을 수행합니다."
)
async def add_blogs_to_flow(
    flow_id: int,
    request: FlowBlogAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> BlogAddResult:
    """플로우에 블로그 추가 (슬롯 검증 포함)"""
    service = FlowService(db)
    return await service.add_blogs(current_user, flow_id, request)


@router.delete(
    "/{flow_id}/blogs/{blog_id}",
    status_code=204,
    summary="플로우에서 블로그 제거",
    description="플로우에서 특정 블로그를 제거합니다. Blogger의 경우 예약된 슬롯도 함께 해제됩니다."
)
async def remove_blog_from_flow(
    flow_id: int,
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우에서 블로그 제거 (슬롯 해제 포함)"""
    service = FlowService(db)
    success = await service.remove_blog(current_user, flow_id, blog_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="블로그 연결을 찾을 수 없습니다"
        )