"""
오토런 페이지 라우터
HTML 페이지 제공
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..models import User
from ..routers.auth import get_current_user
from ..core.logger import get_logger

logger = get_logger("autorun_pages", "app.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["autorun-pages"])


@router.get("/autorun", response_class=HTMLResponse, include_in_schema=False)
async def autorun_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """오토런 메인 페이지"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("autorun/index.html", {"request": request})
