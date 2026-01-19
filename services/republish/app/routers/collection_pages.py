"""
수집 모듈 페이지 라우터

Features:
- 데이터 관리 페이지 라우팅
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..routers.auth import get_current_user
from ..models.user import User

router = APIRouter(tags=["collection-pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/collection", response_class=HTMLResponse)
async def collection_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """데이터 관리 메인 페이지"""
    return templates.TemplateResponse(
        "collection/index.html",
        {"request": request}
    )
