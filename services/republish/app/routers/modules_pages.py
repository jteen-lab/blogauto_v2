"""
모듈 관리 페이지 라우터
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.user import User
from ..services.module_service import ModuleService
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("modules_pages", "app.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["모듈 페이지"])


@router.get("/modules", response_class=HTMLResponse)
async def modules_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """모듈 목록 페이지"""
    try:
        service = ModuleService(db)

        # 모듈 타입 목록과 모듈 목록을 병렬로 가져오기
        module_types = await service.get_module_types()
        modules_response = await service.get_modules(current_user)
        modules = modules_response.modules

        # 모듈별 통계 계산
        stats = {
            'total_modules': len(modules),
        }

        return templates.TemplateResponse(
            "modules/list.html",
            {
                "request": request,
                "user": current_user,
                "modules": modules,
                "module_types": module_types,
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"모듈 목록 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "모듈 목록을 불러올 수 없습니다"
            }
        )


@router.get("/modules/new", response_class=HTMLResponse)
async def module_create_page(
    request: Request,
    type_code: str = "collect",
    current_user: User = Depends(get_current_user)
):
    """모듈 생성 페이지 (독립 페이지로 접근시)"""
    return templates.TemplateResponse(
        "modules/form.html",
        {
            "request": request,
            "user": current_user,
            "module": None,
            "type_code": type_code
        }
    )


@router.get("/modules/{module_id}/edit", response_class=HTMLResponse)
async def module_edit_page(
    module_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """모듈 수정 페이지 (독립 페이지로 접근시)"""
    try:
        service = ModuleService(db)
        module = await service.get_module(current_user, module_id)

        if not module:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "user": current_user,
                    "error_message": "모듈을 찾을 수 없습니다"
                }
            )

        return templates.TemplateResponse(
            "modules/form.html",
            {
                "request": request,
                "user": current_user,
                "module": module
            }
        )
    except Exception as e:
        logger.error(f"모듈 수정 페이지 오류 | 모듈ID={module_id} | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "모듈 정보를 불러올 수 없습니다"
            }
        )


# 기존 프로파일 URL들을 모듈로 리다이렉트
@router.get("/profiles", response_class=RedirectResponse)
async def redirect_profiles_to_modules():
    """기존 프로파일 목록을 모듈 목록으로 리다이렉트"""
    return RedirectResponse(url="/modules", status_code=301)


@router.get("/profiles/new", response_class=RedirectResponse)
async def redirect_profile_new_to_modules():
    """기존 프로파일 생성을 모듈 생성으로 리다이렉트"""
    return RedirectResponse(url="/modules/new?type_code=collect", status_code=301)


@router.get("/profiles/{profile_id}/edit", response_class=RedirectResponse)
async def redirect_profile_edit_to_modules(profile_id: int):
    """기존 프로파일 수정을 모듈 수정으로 리다이렉트"""
    # 실제로는 프로파일 ID를 모듈 ID로 변환하는 로직이 필요할 수 있음
    # 여기서는 단순히 모듈 목록으로 리다이렉트
    return RedirectResponse(url="/modules", status_code=301)


@router.get("/profiles/{profile_id}/stats", response_class=RedirectResponse)
async def redirect_profile_stats_to_modules(profile_id: int):
    """기존 프로파일 통계를 모듈로 리다이렉트"""
    return RedirectResponse(url="/modules", status_code=301)