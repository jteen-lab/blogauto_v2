"""
모듈 템플릿 API 라우터

Features:
- 템플릿 목록 조회
- 템플릿 상세 조회
- 템플릿으로 모듈 일괄 생성
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.services.module_template_service import ModuleTemplateService


router = APIRouter(prefix="/module-templates", tags=["module-templates"])


# ============================================================
# Pydantic Schemas
# ============================================================

class TemplateModuleSchema(BaseModel):
    """템플릿 모듈 스키마"""
    code: str
    order: int
    default_params: dict = {}


class TemplateListResponse(BaseModel):
    """템플릿 목록 응답"""
    code: str
    name: str
    description: str
    icon: str
    module_codes: List[str]
    module_count: int


class TemplateDetailResponse(BaseModel):
    """템플릿 상세 응답"""
    code: str
    name: str
    description: str
    icon: str
    modules: List[TemplateModuleSchema]


class TemplateValidationResponse(BaseModel):
    """템플릿 검증 응답"""
    valid: bool
    missing_modules: List[str] = []
    inactive_modules: List[str] = []
    error: str = None


class ApplyTemplateRequest(BaseModel):
    """템플릿 적용 요청"""
    flow_id: int
    template_code: str


class ApplyTemplateResponse(BaseModel):
    """템플릿 적용 응답"""
    success: bool
    created_count: int
    message: str


# ============================================================
# API Endpoints
# ============================================================

@router.get(
    "",
    response_model=List[TemplateListResponse],
    summary="모듈 템플릿 목록 조회",
    description="사용 가능한 모든 모듈 템플릿 목록을 반환합니다"
)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """모듈 템플릿 목록 조회"""
    service = ModuleTemplateService(db)
    return service.get_all_templates()


@router.get(
    "/{template_code}",
    response_model=TemplateDetailResponse,
    summary="모듈 템플릿 상세 조회",
    description="특정 템플릿의 상세 정보를 반환합니다"
)
async def get_template(
    template_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """특정 템플릿 상세 조회"""
    service = ModuleTemplateService(db)
    template = service.get_template(template_code)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"템플릿을 찾을 수 없습니다: {template_code}"
        )

    return template


@router.get(
    "/{template_code}/validate",
    response_model=TemplateValidationResponse,
    summary="템플릿 검증",
    description="템플릿의 모듈들이 모두 활성화되어 있는지 검증합니다"
)
async def validate_template(
    template_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """템플릿 검증"""
    service = ModuleTemplateService(db)
    return await service.validate_template(template_code)


@router.post(
    "/apply",
    response_model=ApplyTemplateResponse,
    summary="템플릿으로 모듈 생성",
    description="템플릿을 적용하여 Flow에 모듈들을 일괄 생성합니다"
)
async def apply_template(
    request: ApplyTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """템플릿으로 모듈 일괄 생성"""
    service = ModuleTemplateService(db)

    # 템플릿 검증
    validation = await service.validate_template(request.template_code)
    if not validation["valid"]:
        if validation.get("error"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation["error"]
            )
        if validation["missing_modules"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"누락된 모듈: {', '.join(validation['missing_modules'])}"
            )
        if validation["inactive_modules"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"비활성화된 모듈: {', '.join(validation['inactive_modules'])}"
            )

    try:
        created_modules = await service.create_modules_from_template(
            flow_id=request.flow_id,
            template_code=request.template_code,
            user_id=current_user.id
        )
        await db.commit()

        template = service.get_template(request.template_code)

        return ApplyTemplateResponse(
            success=True,
            created_count=len(created_modules),
            message=f"'{template['name']}' 템플릿이 적용되었습니다"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"템플릿 적용 중 오류가 발생했습니다: {str(e)}"
        )
