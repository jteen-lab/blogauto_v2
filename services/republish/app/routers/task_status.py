"""
Celery task 상태 조회 라우터 (Phase 3: 비동기화 공통).

비동기화된 매칭/필터/전환 엔드포인트가 반환한 task_id 로 진행/완료 상태와
결과를 폴링할 수 있도록 한다.
"""
from fastapi import APIRouter, Depends
from celery.result import AsyncResult

from ..core.celery_config import celery_app
from ..models.user import User
from ..routers.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["task-status"])


@router.get("/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Celery task 진행 상태·결과 조회.

    상태값(state):
        - PENDING : 큐 대기 또는 알 수 없는 task_id
        - STARTED : 워커가 실행 중
        - SUCCESS : 정상 완료 (result 포함)
        - FAILURE : 실패 (error 포함)
        - RETRY   : 재시도 대기
    """
    r = AsyncResult(task_id, app=celery_app)
    ready = r.ready()
    state = r.state
    payload: dict = {
        "task_id": task_id,
        "state": state,
        "ready": ready,
    }
    if ready:
        if r.successful():
            payload["successful"] = True
            payload["result"] = r.result
        else:
            payload["successful"] = False
            payload["error"] = str(r.result) if r.result is not None else None
    return payload
