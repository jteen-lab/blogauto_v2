"""CPA 페이지 라우터."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(tags=["cpa-pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/cpa", response_class=HTMLResponse)
async def cpa_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """CPA 오퍼 관리 페이지."""
    return templates.TemplateResponse("cpa/index.html", {"request": request})
