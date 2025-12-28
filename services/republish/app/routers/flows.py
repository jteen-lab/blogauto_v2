"""
플로우 라우터

Features:
- 플로우 CRUD 작업
- 모듈/블로그 독립적 추가/삭제
- 슬롯 검증 포함
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..models import User
from ..models.flow import Flow
from ..models.module import Module
from ..models.blog import Blog
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..schemas.flow import (
    FlowCreateRequest,
    FlowUpdateRequest,
    FlowModuleAddRequest,
    FlowBlogAddRequest,
    FlowResponse,
    FlowDetailResponse,
    FlowListResponse,
    FlowModuleAddResult,
    FlowBlogAddResult
)
from ..routers.auth import get_current_user
from ..services.group_service import GroupService  # 임시로 기존 서비스 사용
from ..core.logger import get_logger

logger = get_logger("flows_router", "app.log")

router = APIRouter(prefix="/api/v1/flows", tags=["flows"])


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
    try:
        logger.info(
            f"[GET_FLOWS] 사용자 {current_user.id} 플로우 목록 조회 "
            f"(상태: {status}, 페이지: {page}/{size})"
        )

        # 쿼리 조건 구성
        conditions = [Flow.user_id == current_user.id]

        if status:
            conditions.append(Flow.status == status)

        # 전체 개수 조회
        count_query = select(func.count(Flow.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # 플로우 목록 조회
        offset = (page - 1) * size
        query = (
            select(Flow)
            .where(and_(*conditions))
            .order_by(Flow.updated_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await db.execute(query)
        flows = result.scalars().all()

        # 개수 정보 계산
        for flow in flows:
            flow.module_count = len(flow.module_links) if flow.module_links else 0
            flow.blog_count = len(flow.blog_links) if flow.blog_links else 0

        has_next = (offset + size) < total

        logger.info(f"[GET_FLOWS] 총 {total}개 중 {len(flows)}개 조회 완료")

        return FlowListResponse(
            flows=[FlowResponse.model_validate(flow) for flow in flows],
            total=total,
            page=page,
            size=size,
            has_next=has_next
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_FLOWS] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="플로우 목록을 조회하는 중 오류가 발생했습니다"
        )


@router.post(
    "",
    response_model=FlowDetailResponse,
    status_code=201,
    summary="플로우 생성",
    description="새로운 플로우를 생성합니다. 초기 모듈과 블로그를 포함할 수 있습니다."
)
async def create_flow(
    request: FlowCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 생성"""
    try:
        logger.info(f"[CREATE_FLOW] 사용자 {current_user.id} 플로우 생성: {request.name}")

        # 플로우 생성
        flow = Flow(
            user_id=current_user.id,
            name=request.name,
            description=request.description,
            status=request.status
        )

        db.add(flow)
        await db.commit()
        await db.refresh(flow)

        # 초기 모듈 추가
        if request.module_ids:
            for i, module_id in enumerate(request.module_ids):
                # 모듈 소유권 확인
                module_query = select(Module).where(
                    and_(Module.id == module_id, Module.user_id == current_user.id)
                )
                module_result = await db.execute(module_query)
                if module_result.scalar_one_or_none():
                    flow_module = FlowModule(
                        flow_id=flow.id,
                        module_id=module_id,
                        execution_order=i
                    )
                    db.add(flow_module)

        # 초기 블로그 추가
        if request.blog_ids:
            for blog_id in request.blog_ids:
                # 블로그 소유권 확인
                blog_query = select(Blog).where(
                    and_(Blog.id == blog_id, Blog.user_id == current_user.id)
                )
                blog_result = await db.execute(blog_query)
                if blog_result.scalar_one_or_none():
                    flow_blog = FlowBlog(
                        flow_id=flow.id,
                        blog_id=blog_id
                    )
                    db.add(flow_blog)

        await db.commit()

        # 관계 데이터 로딩
        await db.refresh(flow, ['module_links', 'blog_links'])

        logger.info(f"[CREATE_FLOW] 플로우 생성 완료: {flow.id}")

        return await _get_flow_detail(flow.id, current_user.id, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CREATE_FLOW] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="플로우를 생성하는 중 오류가 발생했습니다"
        )


@router.get(
    "/{flow_id}",
    response_model=FlowDetailResponse,
    summary="플로우 상세 조회",
    description="특정 플로우의 상세 정보(모듈, 블로그 포함)를 조회합니다."
)
async def get_flow(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 상세 조회"""
    try:
        logger.info(f"[GET_FLOW] 사용자 {current_user.id} 플로우 조회: {flow_id}")

        return await _get_flow_detail(flow_id, current_user.id, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_FLOW] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="플로우를 조회하는 중 오류가 발생했습니다"
        )


@router.put(
    "/{flow_id}",
    response_model=FlowDetailResponse,
    summary="플로우 기본 정보 수정",
    description="플로우의 이름과 설명을 수정합니다. 상태는 오토런 API에서 관리합니다."
)
async def update_flow(
    flow_id: int,
    request: FlowUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowDetailResponse:
    """플로우 기본 정보 수정"""
    try:
        logger.info(f"[UPDATE_FLOW] 사용자 {current_user.id} 플로우 수정: {flow_id}")

        # 플로우 조회 (소유권 확인 포함)
        query = select(Flow).where(
            and_(Flow.id == flow_id, Flow.user_id == current_user.id)
        )
        result = await db.execute(query)
        flow = result.scalar_one_or_none()

        if not flow:
            raise HTTPException(
                status_code=404,
                detail="플로우를 찾을 수 없습니다"
            )

        # 업데이트 필드 적용
        update_data = request.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(flow, field, value)

        await db.commit()

        logger.info(f"[UPDATE_FLOW] 플로우 수정 완료: {flow_id}")

        return await _get_flow_detail(flow_id, current_user.id, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPDATE_FLOW] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="플로우를 수정하는 중 오류가 발생했습니다"
        )


@router.delete(
    "/{flow_id}",
    status_code=204,
    summary="플로우 삭제",
    description="플로우를 삭제합니다. 활성 상태의 플로우는 삭제할 수 없습니다."
)
async def delete_flow(
    flow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """플로우 삭제"""
    try:
        logger.info(f"[DELETE_FLOW] 사용자 {current_user.id} 플로우 삭제: {flow_id}")

        # 플로우 조회 (소유권 확인 포함)
        query = select(Flow).where(
            and_(Flow.id == flow_id, Flow.user_id == current_user.id)
        )
        result = await db.execute(query)
        flow = result.scalar_one_or_none()

        if not flow:
            raise HTTPException(
                status_code=404,
                detail="플로우를 찾을 수 없습니다"
            )

        # 활성 상태 확인
        if flow.status == "active":
            raise HTTPException(
                status_code=400,
                detail="활성 상태의 플로우는 삭제할 수 없습니다. 먼저 중지해주세요."
            )

        await db.delete(flow)
        await db.commit()

        logger.info(f"[DELETE_FLOW] 플로우 삭제 완료: {flow_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DELETE_FLOW] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="플로우를 삭제하는 중 오류가 발생했습니다"
        )


@router.post(
    "/{flow_id}/modules",
    response_model=FlowModuleAddResult,
    summary="플로우에 모듈 추가",
    description="플로우에 하나 이상의 모듈을 추가합니다."
)
async def add_modules_to_flow(
    flow_id: int,
    request: FlowModuleAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> FlowModuleAddResult:
    """플로우에 모듈 추가"""
    try:
        logger.info(
            f"[ADD_MODULES] 사용자 {current_user.id} 플로우 {flow_id}에 "
            f"{len(request.module_ids)}개 모듈 추가"
        )

        # 플로우 존재 및 소유권 확인
        flow_query = select(Flow).where(
            and_(Flow.id == flow_id, Flow.user_id == current_user.id)
        )
        flow_result = await db.execute(flow_query)
        flow = flow_result.scalar_one_or_none()

        if not flow:
            raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

        success_count = 0
        failed_modules = []
        warnings = []

        # 현재 최대 실행 순서 조회
        max_order_query = select(func.max(FlowModule.execution_order)).where(
            FlowModule.flow_id == flow_id
        )
        max_order_result = await db.execute(max_order_query)
        max_order = max_order_result.scalar() or -1

        for i, module_id in enumerate(request.module_ids):
            try:
                # 모듈 존재 및 소유권 확인
                module_query = select(Module).where(
                    and_(Module.id == module_id, Module.user_id == current_user.id)
                )
                module_result = await db.execute(module_query)
                module = module_result.scalar_one_or_none()

                if not module:
                    failed_modules.append({
                        "module_id": module_id,
                        "reason": "모듈을 찾을 수 없습니다"
                    })
                    continue

                # 중복 확인
                existing_query = select(FlowModule).where(
                    and_(
                        FlowModule.flow_id == flow_id,
                        FlowModule.module_id == module_id
                    )
                )
                existing_result = await db.execute(existing_query)
                if existing_result.scalar_one_or_none():
                    warnings.append(f"모듈 '{module.name}'은 이미 추가되어 있습니다")
                    continue

                # 실행 순서 결정
                if request.execution_orders and i < len(request.execution_orders):
                    execution_order = request.execution_orders[i]
                else:
                    execution_order = max_order + i + 1

                # 모듈 추가
                flow_module = FlowModule(
                    flow_id=flow_id,
                    module_id=module_id,
                    execution_order=execution_order
                )
                db.add(flow_module)
                success_count += 1

            except Exception as e:
                failed_modules.append({
                    "module_id": module_id,
                    "reason": str(e)
                })

        await db.commit()

        message = f"{success_count}개 모듈이 플로우에 추가되었습니다"
        if failed_modules:
            message += f" ({len(failed_modules)}개 실패)"

        logger.info(f"[ADD_MODULES] 완료: {success_count}개 성공, {len(failed_modules)}개 실패")

        return FlowModuleAddResult(
            success_count=success_count,
            failed_modules=failed_modules,
            warnings=warnings,
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADD_MODULES] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 추가하는 중 오류가 발생했습니다"
        )


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
    try:
        logger.info(
            f"[REMOVE_MODULE] 사용자 {current_user.id} 플로우 {flow_id}에서 "
            f"모듈 {module_id} 제거"
        )

        # 플로우 소유권 확인
        flow_query = select(Flow).where(
            and_(Flow.id == flow_id, Flow.user_id == current_user.id)
        )
        flow_result = await db.execute(flow_query)
        if not flow_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")

        # 플로우-모듈 링크 조회
        link_query = select(FlowModule).where(
            and_(
                FlowModule.flow_id == flow_id,
                FlowModule.module_id == module_id
            )
        )
        link_result = await db.execute(link_query)
        link = link_result.scalar_one_or_none()

        if not link:
            raise HTTPException(
                status_code=404,
                detail="플로우에서 해당 모듈을 찾을 수 없습니다"
            )

        await db.delete(link)
        await db.commit()

        logger.info(f"[REMOVE_MODULE] 모듈 제거 완료: {module_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REMOVE_MODULE] 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail="모듈을 제거하는 중 오류가 발생했습니다"
        )


async def _get_flow_detail(
    flow_id: int,
    user_id: int,
    db: AsyncSession
) -> FlowDetailResponse:
    """플로우 상세 정보 조회 헬퍼"""
    # 플로우 조회 (모든 관계 포함)
    query = (
        select(Flow)
        .options(
            selectinload(Flow.module_links).selectinload(FlowModule.module).selectinload(Module.module_type),
            selectinload(Flow.blog_links).selectinload(FlowBlog.blog)
        )
        .where(and_(Flow.id == flow_id, Flow.user_id == user_id))
    )
    result = await db.execute(query)
    flow = result.scalar_one_or_none()

    if not flow:
        raise HTTPException(
            status_code=404,
            detail="플로우를 찾을 수 없습니다"
        )

    return FlowDetailResponse.model_validate(flow)