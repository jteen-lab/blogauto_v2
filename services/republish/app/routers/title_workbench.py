"""제목 작업대 API — 임시제목 탭의 수집·생성 실행.

오래 걸리는 회차가 있어 **배경 작업 + 폴링**으로 돈다. Caddy 의
`response_header_timeout` 이 60초라 그보다 긴 요청은 응답 헤더를 못 받고
끊긴다(과거 80초 요청이 "Unexpected end of JSON input" 으로 죽었다).

계획서: docs/plans/title_tab_workplan.md §1
"""
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.niche_domain import EXTRACT_PARTIAL, EXTRACT_PENDING, NicheDomain
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.title_collect.workbench import TitleWorkbench

router = APIRouter(prefix="/title-workbench", tags=["title-workbench"])
logger = get_logger("title_workbench_api", "app.log")

# 사용자별 진행 상태. 앱 단일 프로세스 전제(스케줄러 인프로세스)다.
_runs: Dict[int, Dict[str, Any]] = {}
_tasks: set = set()


class RunRequest(BaseModel):
    """화면이 보낸 설정 그대로."""

    collect: Optional[dict] = None
    gen: Optional[dict] = None


@router.get("/stats")
async def workbench_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """작업대 상단에 띄울 숫자."""
    mine = NicheDomain.user_id == current_user.id
    partial = (await db.execute(
        select(func.count()).select_from(NicheDomain).where(
            mine, NicheDomain.is_blocked.is_(False),
            NicheDomain.extract_status.in_([EXTRACT_PARTIAL, EXTRACT_PENDING]))
    )).scalar() or 0
    blocked = (await db.execute(
        select(func.count()).select_from(NicheDomain).where(
            mine, NicheDomain.is_blocked.is_(True))
    )).scalar() or 0
    return {"partial_domains": int(partial), "blocked_domains": int(blocked)}


@router.post("/run")
async def start_run(
    payload: RunRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """회차를 시작한다. 결과는 `/status` 로 받는다."""
    state = _runs.get(current_user.id)
    if state and state.get("running"):
        return {"success": True, "running": True,
                "message": "이미 실행 중입니다"}

    _runs[current_user.id] = {"running": True, "done": False,
                              "result": None, "error": None}
    task = asyncio.create_task(
        _run_background(current_user.id, payload.model_dump()))
    # 참조를 붙들지 않으면 GC 가 태스크를 거둬 간다
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"success": True, "running": True}


@router.get("/status")
async def run_status(current_user: User = Depends(get_current_user)) -> dict:
    """진행 상태. 화면이 2초마다 부른다."""
    state = _runs.get(current_user.id)
    if not state:
        return {"running": False, "done": False, "result": None}
    return {"running": state["running"], "done": state["done"],
            "result": state["result"], "error": state["error"]}


async def _run_background(user_id: int, payload: dict) -> None:
    """자체 세션으로 회차를 돈다. 요청 세션은 이미 닫혔다."""
    from ..core.database import db_manager

    state = _runs[user_id]
    try:
        async with db_manager.get_session() as db:
            state["result"] = await TitleWorkbench(db, user_id).run(payload)
    except Exception as e:  # noqa: BLE001
        logger.error("[TITLE_WORKBENCH] 실패 | user=%s | %s", user_id, e,
                     exc_info=True)
        state["error"] = str(e)[:300]
    finally:
        state["running"] = False
        state["done"] = True
