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

# 진행 상태. 앱 단일 프로세스 전제(스케줄러 인프로세스)다.
#
# 키를 사용자 하나로 두면 니치 요약탭에서 두 번째 카드를 눌렀을 때
# "이미 실행 중" 만 뜬다. 카드를 눌러 가며 채우는 화면이라 니치별로 나눈다.
# 니치 지정이 없는 전역 실행(임시제목 탭 작업대)은 예전 그대로 하나다.
_runs: Dict[str, Dict[str, Any]] = {}
_tasks: set = set()

# 동시에 도는 회차 상한. AI·검색 API 를 쓰므로 무제한은 곧 비용이다.
MAX_CONCURRENT = 4


def _key(user_id: int, subtopic_id: Optional[int]) -> str:
    """실행 슬롯 키. 니치가 없으면 전역 슬롯."""
    return f"{user_id}:{subtopic_id}" if subtopic_id else f"{user_id}:-"


class RunRequest(BaseModel):
    """화면이 보낸 설정 그대로."""

    collect: Optional[dict] = None
    gen: Optional[dict] = None
    # 니치 하나만 채울 때(요약탭 카드). 수집·생성 양쪽에 같이 꽂는다.
    subtopic_id: Optional[int] = None


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
    key = _key(current_user.id, payload.subtopic_id)
    state = _runs.get(key)
    if state and state.get("running"):
        return {"success": True, "running": True,
                "message": "이미 실행 중입니다"}

    busy = sum(1 for s in _runs.values() if s.get("running"))
    if busy >= MAX_CONCURRENT:
        return {"success": False, "running": False,
                "message": f"동시에 {MAX_CONCURRENT}개까지만 돌릴 수 있습니다 — "
                           "끝나면 다시 눌러 주세요"}

    _runs[key] = {"running": True, "done": False,
                  "result": None, "error": None}
    task = asyncio.create_task(
        _run_background(key, current_user.id, _scoped(payload)))
    # 참조를 붙들지 않으면 GC 가 태스크를 거둬 간다
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"success": True, "running": True}


@router.get("/status")
async def run_status(
    subtopic_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
) -> dict:
    """진행 상태. 화면이 2초마다 부른다."""
    state = _runs.get(_key(current_user.id, subtopic_id))
    if not state:
        return {"running": False, "done": False, "result": None}
    return {"running": state["running"], "done": state["done"],
            "result": state["result"], "error": state["error"]}


def _scoped(payload: RunRequest) -> dict:
    """니치 지정을 수집·생성 양쪽 설정에 꽂는다.

    화면이 두 곳에 따로 넣게 하면 한쪽을 빠뜨린다 — 수집만 좁혀지고
    생성은 다른 니치를 채우는 일이 생긴다.
    """
    raw = payload.model_dump()
    sub = raw.pop("subtopic_id", None)
    if not sub:
        return raw
    for section in ("collect", "gen"):
        raw[section] = dict(raw.get(section) or {})
        raw[section]["subtopic_ids"] = [sub]
    return raw


async def _run_background(key: str, user_id: int, payload: dict) -> None:
    """자체 세션으로 회차를 돈다. 요청 세션은 이미 닫혔다."""
    from ..core.database import db_manager

    state = _runs[key]
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
