"""문의 수신함 페이지 라우터 (F10 대시보드)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..models.user import User
from ..routers.auth import get_current_user

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["문의 수신함 페이지"])


@router.get("/contact-inbox", response_class=HTMLResponse)
async def contact_inbox_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """문의 수신함 페이지."""
    return templates.TemplateResponse("contact_inbox.html", {"request": request})
