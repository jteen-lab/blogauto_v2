"""
모듈 타입 라우터

Features:
- 모듈 타입 마스터 데이터 조회
- 읽기 전용 API (마스터 데이터)
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db_session
from ..models.module_type import ModuleType
from ..schemas.module import ModuleTypeResponse
from ..core.logger import get_logger

logger = get_logger("module_types_router", "app.log")

router = APIRouter(prefix="/api/v1/module-types", tags=["module-types"])


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
    try:
        logger.info("[GET_MODULE_TYPES] 모듈 타입 목록 조회 시작")

        # 모듈 타입 목록 조회 (display_order 순)
        query = select(ModuleType).order_by(ModuleType.display_order, ModuleType.id)
        result = await db.execute(query)
        module_types = result.scalars().all()

        logger.info(f"[GET_MODULE_TYPES] {len(module_types)}개 모듈 타입 조회 완료")

        return [ModuleTypeResponse.model_validate(mt) for mt in module_types]

    except Exception as e:
        logger.error(f"[GET_MODULE_TYPES] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈 타입 목록을 조회하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(f"[GET_MODULE_TYPE] 모듈 타입 조회: {code}")

        # 모듈 타입 조회
        query = select(ModuleType).where(ModuleType.code == code)
        result = await db.execute(query)
        module_type = result.scalar_one_or_none()

        if not module_type:
            raise HTTPException(
                status_code=404,
                detail=f"모듈 타입을 찾을 수 없습니다: {code}"
            )

        logger.info(f"[GET_MODULE_TYPE] 모듈 타입 조회 완료: {code}")

        return ModuleTypeResponse.model_validate(module_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_MODULE_TYPE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈 타입을 조회하는 중 오류가 발생했습니다"
        )