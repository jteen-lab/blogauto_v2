"""
모듈 라우터

Features:
- 모듈 CRUD 작업
- 타입별 필터링
- 페이지네이션 지원
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models import User
from ..services.module_service import ModuleService
from ..schemas.module import (
    ModuleCreateRequest,
    ModuleUpdateRequest,
    ModuleDetailResponse,
    ModuleListResponse
)
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("modules_router", "app.log")

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get(
    "",
    response_model=ModuleListResponse,
    summary="모듈 목록 조회",
    description="사용자의 모듈 목록을 조회합니다. 타입별 필터링과 페이지네이션을 지원합니다."
)
async def get_modules(
    module_type_code: Optional[str] = Query(None, description="모듈 타입 코드 필터"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleListResponse:
    """모듈 목록 조회"""
    service = ModuleService(db)
    return await service.get_modules(current_user, module_type_code, page, size)


@router.post(
    "",
    response_model=ModuleDetailResponse,
    status_code=201,
    summary="모듈 생성",
    description="새로운 모듈을 생성합니다."
)
async def create_module(
    request: ModuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 생성"""
    service = ModuleService(db)
    module = await service.create_module(current_user, request)

    # 응답용 데이터 구성
    response_data = ModuleDetailResponse.model_validate(module)
    response_data.calculated_interval_minutes = module.calculated_interval_minutes

    return response_data


@router.get(
    "/{module_id}",
    response_model=ModuleDetailResponse,
    summary="모듈 상세 조회",
    description="특정 모듈의 상세 정보를 조회합니다."
)
async def get_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 상세 조회"""
    service = ModuleService(db)
    module = await service.get_module(current_user, module_id)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    response_data = ModuleDetailResponse.model_validate(module)
    response_data.calculated_interval_minutes = module.calculated_interval_minutes

    return response_data


@router.put(
    "/{module_id}",
    response_model=ModuleDetailResponse,
    summary="모듈 수정",
    description="기존 모듈의 정보를 수정합니다."
)
async def update_module(
    module_id: int,
    request: ModuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 수정"""
    service = ModuleService(db)
    module = await service.update_module(current_user, module_id, request)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    try:
        response_data = ModuleDetailResponse.model_validate(module)

        # calculated_interval_minutes 속성이 있는지 확인
        if hasattr(module, 'calculated_interval_minutes'):
            response_data.calculated_interval_minutes = module.calculated_interval_minutes
        else:
            logger.warning(f"Module {module_id} does not have calculated_interval_minutes attribute")
            response_data.calculated_interval_minutes = None

        return response_data

    except Exception as e:
        logger.error(f"Error constructing response for module {module_id}: {str(e)}")
        logger.error(f"Module data: {module}")
        logger.error(f"Module type: {type(module)}")

        # 기본 응답 반환 (calculated_interval_minutes 없이)
        response_data = ModuleDetailResponse.model_validate(module)
        response_data.calculated_interval_minutes = None
        return response_data


@router.post(
    "/{module_id}/copy",
    response_model=ModuleDetailResponse,
    status_code=201,
    summary="모듈 복사",
    description="기존 모듈을 복사하여 새로운 모듈을 생성합니다."
)
async def copy_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ModuleDetailResponse:
    """모듈 복사"""
    service = ModuleService(db)
    module = await service.copy_module(current_user, module_id)

    if not module:
        raise HTTPException(
            status_code=404,
            detail="복사할 모듈을 찾을 수 없습니다"
        )

    # 응답용 데이터 구성
    response_data = ModuleDetailResponse.model_validate(module)
    response_data.calculated_interval_minutes = module.calculated_interval_minutes

    return response_data


@router.delete(
    "/{module_id}",
    status_code=204,
    summary="모듈 삭제",
    description="모듈을 삭제합니다. 플로우에서 사용 중인 모듈은 삭제할 수 없습니다."
)
async def delete_module(
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """모듈 삭제"""
    service = ModuleService(db)
    success = await service.delete_module(current_user, module_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="모듈을 찾을 수 없습니다"
        )