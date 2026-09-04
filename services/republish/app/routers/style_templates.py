"""제목 스타일 템플릿 API.

모듈마다 다섯 칸을 손으로 채우면 블로그 12개에 60번을 입력해야 한다.
템플릿을 골라 한 번에 채우고, 필요하면 개별로 고친다.

**추천은 모듈이 고른 블로그의 니치로 정한다.** 금융 블로그에 맛집용
지시가 들어가면 제목이 어긋난다.

계획서: docs/plans/title_tab_workplan.md §4-5
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.category import BlogCategory, Topic
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.generation import style_templates as st

router = APIRouter(prefix="/recombine-templates", tags=["modules"])
logger = get_logger("style_templates", "app.log")


@router.get("")
async def list_templates(
    current_user: User = Depends(get_current_user),
) -> dict:
    """템플릿 목록. 화면이 드롭다운을 만든다."""
    return {"templates": [
        {"code": t["code"], "label": t["label"], "hint": t["hint"],
         "prompts": t["prompts"]}
        for t in st.TEMPLATES
    ]}


@router.get("/recommend")
async def recommend_template(
    blog_ids: Optional[str] = Query(
        None, description="쉼표로 구분한 블로그 ID — 모듈이 고른 블로그"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """이 블로그들의 니치에 맞는 템플릿.

    맞는 것이 없으면 `code` 가 null 이다 — 짐작해서 고르면 엉뚱한 지시가
    들어간다.
    """
    ids = _parse_ids(blog_ids)
    if not ids:
        return {"code": None, "topics": [], "reason": "블로그를 먼저 고르세요"}

    names = list((await db.execute(
        select(Topic.name)
        .join(BlogCategory, BlogCategory.topic_id == Topic.id)
        .where(BlogCategory.blog_id.in_(ids),
               BlogCategory.is_active.is_(True),
               Topic.is_deleted.is_(False))
        .distinct()
    )).scalars().all())

    code = st.recommend(names)
    template = st.BY_CODE.get(code) if code else None
    return {
        "code": code,
        "label": template["label"] if template else None,
        "prompts": template["prompts"] if template else {},
        "topics": names,
        "reason": (f"{', '.join(names[:4])} 니치에 맞춰 골랐습니다"
                   if code else "니치와 맞는 템플릿이 없습니다 — 직접 고르세요"),
    }


def _parse_ids(raw: Optional[str]) -> List[int]:
    """쉼표 구분 문자열을 id 목록으로. 잘못된 값은 버린다."""
    out: List[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out
