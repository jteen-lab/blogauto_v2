"""임시제목 정리 API — 미분류·니치 무관을 걷어낸다.

`data_titles.py` 가 이미 900줄을 넘어 여기로 분리한다. prefix 는 같으므로
화면에서는 같은 묶음으로 보인다.

경로를 `/temp/cleanup` 이 아니라 `/cleanup` 으로 둔 이유: `data_titles`
에 `/temp/{title_id}` 가 있어 경로 변수와 겹친다.

계획서: docs/plans/title_pipeline_redesign_plan.md §5 (B안)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services import title_cleanup

router = APIRouter(prefix="/data/titles", tags=["data-titles"])
logger = get_logger("data_title_cleanup", "app.log")


class CleanupRequest(BaseModel):
    """지울 사유. 비우면 둘 다."""

    reasons: Optional[List[str]] = None


@router.get("/cleanup/preview")
async def preview_cleanup(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """무엇이 얼마나 지워지는지 먼저 본다. 삭제하지 않는다.

    삭제는 되돌릴 수 없으므로 화면이 건수를 보여 준 뒤에 확인을 받는다.
    """
    return await title_cleanup.preview(db)


@router.post("/cleanup")
async def run_cleanup(
    payload: CleanupRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """선택한 사유의 임시제목을 삭제한다.

    ⚠️ 되돌릴 수 없다. 재분류를 먼저 돌린 뒤 실행하는 것을 전제한다 —
    분류표가 자라면 지금 미분류인 것도 나중에 붙기 때문이다.
    """
    result = await title_cleanup.cleanup(db, payload.reasons)
    logger.info("[TITLE_CLEANUP] user=%s | %s", current_user.id, result)
    return result
