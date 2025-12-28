"""
모듈 라우터

Features:
- 모듈 CRUD 작업
- 타입별 필터링
- 페이지네이션 지원
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..models import User
from ..models.module import Module
from ..models.module_type import ModuleType
from ..schemas.module import (
    ModuleCreateRequest,
    ModuleUpdateRequest,
    ModuleResponse,
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
    try:
        logger.info(
            f"[GET_MODULES] 사용자 {current_user.id} 모듈 목록 조회 "
            f"(타입: {module_type_code}, 페이지: {page}/{size})"
        )

        # 쿼리 조건 구성
        conditions = [Module.user_id == current_user.id]

        if module_type_code:
            # 모듈 타입 조회
            type_query = select(ModuleType.id).where(ModuleType.code == module_type_code)
            type_result = await db.execute(type_query)
            module_type_id = type_result.scalar_one_or_none()

            if not module_type_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"존재하지 않는 모듈 타입: {module_type_code}"
                )

            conditions.append(Module.module_type_id == module_type_id)

        # 전체 개수 조회
        count_query = select(func.count(Module.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # 모듈 목록 조회 (관계 포함)
        offset = (page - 1) * size
        query = (
            select(Module)
            .options(selectinload(Module.module_type))
            .where(and_(*conditions))
            .order_by(Module.updated_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await db.execute(query)
        modules = result.scalars().all()

        has_next = (offset + size) < total

        logger.info(f"[GET_MODULES] 총 {total}개 중 {len(modules)}개 조회 완료")

        return ModuleListResponse(
            modules=[ModuleResponse.model_validate(module) for module in modules],
            total=total,
            page=page,
            size=size,
            has_next=has_next
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_MODULES] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈 목록을 조회하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(f"[CREATE_MODULE] 사용자 {current_user.id} 모듈 생성: {request.name}")

        # 모듈 타입 조회
        type_query = select(ModuleType).where(ModuleType.code == request.module_type_code)
        type_result = await db.execute(type_query)
        module_type = type_result.scalar_one_or_none()

        if not module_type:
            raise HTTPException(
                status_code=400,
                detail=f"존재하지 않는 모듈 타입: {request.module_type_code}"
            )

        # 모듈 생성
        module = Module(
            user_id=current_user.id,
            module_type_id=module_type.id,
            name=request.name,
            description=request.description,
            schedule_matrix=request.schedule_matrix,
            manual_interval_minutes=request.manual_interval_minutes,
            min_post_count=request.min_post_count,
            post_range_start=request.post_range_start,
            post_range_end=request.post_range_end,
            interval_mode=request.interval_mode,
            auto_daily_count=request.auto_daily_count,
            jitter_enabled=request.jitter_enabled,
            jitter_min_percent=request.jitter_min_percent,
            jitter_max_percent=request.jitter_max_percent,
            active_hours_start=request.active_hours_start,
            active_hours_end=request.active_hours_end,
            blackout_days=request.blackout_days,
            cooldown_days=request.cooldown_days,
            priority=request.priority,
            platform_overrides=request.platform_overrides,
            settings=request.settings
        )

        db.add(module)
        await db.commit()
        await db.refresh(module, ["module_type"])

        logger.info(f"[CREATE_MODULE] 모듈 생성 완료: {module.id}")

        # 응답용 데이터 구성
        response_data = ModuleDetailResponse.model_validate(module)
        response_data.calculated_interval_minutes = module.calculated_interval_minutes

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CREATE_MODULE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 생성하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(f"[GET_MODULE] 사용자 {current_user.id} 모듈 조회: {module_id}")

        # 모듈 조회 (소유권 확인 포함)
        query = (
            select(Module)
            .options(selectinload(Module.module_type))
            .where(
                and_(
                    Module.id == module_id,
                    Module.user_id == current_user.id
                )
            )
        )
        result = await db.execute(query)
        module = result.scalar_one_or_none()

        if not module:
            raise HTTPException(
                status_code=404,
                detail="모듈을 찾을 수 없습니다"
            )

        logger.info(f"[GET_MODULE] 모듈 조회 완료: {module_id}")

        # 응답용 데이터 구성
        response_data = ModuleDetailResponse.model_validate(module)
        response_data.calculated_interval_minutes = module.calculated_interval_minutes

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_MODULE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 조회하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(f"[UPDATE_MODULE] 사용자 {current_user.id} 모듈 수정: {module_id}")

        # 모듈 조회 (소유권 확인 포함)
        query = (
            select(Module)
            .options(selectinload(Module.module_type))
            .where(
                and_(
                    Module.id == module_id,
                    Module.user_id == current_user.id
                )
            )
        )
        result = await db.execute(query)
        module = result.scalar_one_or_none()

        if not module:
            raise HTTPException(
                status_code=404,
                detail="모듈을 찾을 수 없습니다"
            )

        # 업데이트 필드 적용 (None이 아닌 값만)
        update_data = request.model_dump(exclude_none=True)

        for field, value in update_data.items():
            if hasattr(module, field):
                setattr(module, field, value)

        await db.commit()
        await db.refresh(module, ["module_type"])

        logger.info(f"[UPDATE_MODULE] 모듈 수정 완료: {module_id}")

        # 응답용 데이터 구성
        response_data = ModuleDetailResponse.model_validate(module)
        response_data.calculated_interval_minutes = module.calculated_interval_minutes

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPDATE_MODULE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 수정하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(f"[DELETE_MODULE] 사용자 {current_user.id} 모듈 삭제: {module_id}")

        # 모듈 조회 (소유권 확인 포함)
        query = select(Module).where(
            and_(
                Module.id == module_id,
                Module.user_id == current_user.id
            )
        )
        result = await db.execute(query)
        module = result.scalar_one_or_none()

        if not module:
            raise HTTPException(
                status_code=404,
                detail="모듈을 찾을 수 없습니다"
            )

        # 플로우에서 사용 중인지 확인 (flow_links 관계 확인)
        if module.flow_links:
            flow_names = [link.flow.name for link in module.flow_links[:3]]
            raise HTTPException(
                status_code=400,
                detail=f"플로우에서 사용 중인 모듈은 삭제할 수 없습니다. 사용 중인 플로우: {', '.join(flow_names)}"
            )

        await db.delete(module)
        await db.commit()

        logger.info(f"[DELETE_MODULE] 모듈 삭제 완료: {module_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DELETE_MODULE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 삭제하는 중 오류가 발생했습니다"
        )