"""
모듈 타입 라우터

Features:
- 모듈 타입 마스터 데이터 조회
- 읽기 전용 API (마스터 데이터)
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..services.module_service import ModuleService
from ..schemas.module import ModuleTypeResponse
from ..core.logger import get_logger

logger = get_logger("module_types_router", "app.log")

router = APIRouter(prefix="/module-types", tags=["module-types"])


@router.get(
    "",
    response_model=List[ModuleTypeResponse],
    summary="모듈 타입 목록 조회",
    description="사용 가능한 모든 모듈 타입을 조회합니다."
)
async def get_module_types(
    db: AsyncSession = Depends(get_db_session)
) -> List[ModuleTypeResponse]:
    """모듈 타입 목록 조회"""
    service = ModuleService(db)
    return await service.get_module_types()


@router.get(
    "/{code}",
    response_model=ModuleTypeResponse,
    summary="모듈 타입 상세 조회",
    description="특정 모듈 타입의 상세 정보를 조회합니다."
)
async def get_module_type(
    code: str,
    db: AsyncSession = Depends(get_db_session)
) -> ModuleTypeResponse:
    """모듈 타입 상세 조회"""
    service = ModuleService(db)
    module_type = await service.get_module_type_by_code(code)

    if not module_type:
        raise HTTPException(
            status_code=404,
            detail=f"모듈 타입을 찾을 수 없습니다: {code}"
        )

    return ModuleTypeResponse.model_validate(module_type)