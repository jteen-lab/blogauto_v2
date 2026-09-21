"""블로그에 걸린 생성 프롬프트 템플릿 목록.

이미지 탭에서 배경마다 "어느 템플릿 것인지" 고르게 하려면 목록이
있어야 한다. 사용자가 주제 ID 를 외워 적는 대신 이름을 고른다.

순서도: docs/flowcharts/template_image_prompt_pick.md
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.module import Module
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/blogs", tags=["블로그 프롬프트 템플릿"])
logger = get_logger("blog_prompt_templates", "app.log")

PROMPT_CODE = "prompt"


def _label_of(row: Dict[str, Any], at: int) -> str:
    """드롭다운에 적을 말. 이름이 없으면 프리셋, 그것도 없으면 번호."""
    for key in ("label", "preset_label"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return f"템플릿 {at + 1}"


def _templates_of(settings: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """모듈 설정에서 템플릿 목록을 자리 순서대로 꺼낸다."""
    rot = (settings or {}).get("prompt_rotation") or {}
    rows = rot.get("variants")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for at, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        out.append({
            "index": at,
            "no": at + 1,
            "label": _label_of(row, at),
            "preset_label": row.get("preset_label") or "",
            "is_base": bool(row.get("is_base")),
        })
    return out


async def _prompt_module(db: AsyncSession, user: User,
                         blog_id: int) -> Optional[Module]:
    """이 블로그를 맡은 생성 프롬프트 모듈. 여럿이면 가장 최근 것."""
    rows = (await db.execute(
        select(Module)
        .options(selectinload(Module.module_type))
        .where(Module.user_id == user.id)
        .order_by(Module.updated_at.desc().nullslast())
    )).scalars().all()
    for mod in rows:
        code = getattr(getattr(mod, "module_type", None), "code", "")
        if code != PROMPT_CODE:
            continue
        blogs = (mod.settings or {}).get("blogs") or []
        if blog_id in [int(b) for b in blogs if str(b).isdigit()]:
            return mod
    return None


@router.get(
    "/{blog_id}/prompt-templates",
    summary="이 블로그의 생성 프롬프트 템플릿 목록",
)
async def list_prompt_templates(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """배경 슬롯에 짝지을 템플릿 목록.

    로테이션을 쓰지 않으면 빈 목록이 간다. 화면은 그때 드롭다운을
    감춘다 — 고를 것이 없는 칸을 보여 줄 이유가 없다.
    """
    blog = (await db.execute(
        select(Blog).where(Blog.id == blog_id,
                           Blog.user_id == current_user.id,
                           Blog.is_deleted == False)  # noqa: E712
    )).scalar_one_or_none()
    if not blog:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")

    mod = await _prompt_module(db, current_user, blog_id)
    if not mod:
        return {"module_id": None, "module_name": "", "templates": []}

    rows = _templates_of(mod.settings)
    logger.info("[PROMPT_TEMPLATES] blog=%s | module=%s | %d개",
                blog_id, mod.id, len(rows))
    return {"module_id": mod.id, "module_name": mod.name, "templates": rows}
