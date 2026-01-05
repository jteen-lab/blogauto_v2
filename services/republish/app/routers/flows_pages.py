"""
플로우 페이지 라우터
HTML 페이지 제공
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..models import User
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("flows_pages", "app.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["flows-pages"])


@router.get("/flows", response_class=HTMLResponse, include_in_schema=False)
async def flows_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """플로우 관리 페이지"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("flows/list.html", {"request": request})


# 기존 그룹 경로들을 플로우로 리다이렉트
@router.get("/groups", response_class=RedirectResponse, include_in_schema=False)
async def groups_redirect():
    """기존 그룹 페이지를 플로우 페이지로 리다이렉트"""
    return RedirectResponse(url="/flows", status_code=301)


@router.get("/groups/", response_class=RedirectResponse, include_in_schema=False)
async def groups_slash_redirect():
    """기존 그룹 페이지를 플로우 페이지로 리다이렉트 (슬래시 포함)"""
    return RedirectResponse(url="/flows", status_code=301)


@router.get("/groups/{path:path}", response_class=RedirectResponse, include_in_schema=False)
async def groups_sub_redirect(path: str):
    """기존 그룹 하위 경로들을 플로우 페이지로 리다이렉트"""
    return RedirectResponse(url="/flows", status_code=301)