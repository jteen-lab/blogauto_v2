"""워커 실행 결과를 플로우 실행 상태에 반영한다.

스케줄러는 **Celery 에 넘긴 순간** 성공으로 적는다. 큐에 넣는 데 성공했다는
뜻일 뿐이라, 워커에서 실제 작업이 실패해도 통계는 성공으로 남는다.

실측(2026-09-09 머니조아): 글 생성이 3회 연속 실패했는데 상태는
`성공 2 · 실패 0 · 연속실패 0` 이었다. 실패한 줄 아무도 몰랐고 다음 실행은
정상 주기대로 하루 뒤로 잡혀 **하루가 통째로 날아갔다.**

그래서 워커가 끝난 자리에서 실제 결과로 바로잡는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import pytz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .logger import get_logger

logger = get_logger("celery_flow_state", "app.log")

KST = pytz.timezone("Asia/Seoul")


def outcome_of(result: Dict[str, Any]) -> str:
    """워커 결과를 성공·스킵·실패 중 하나로 읽는다.

    **스킵은 실패가 아니다.** 재고 없음·일일 한도 도달처럼 정상 판단으로
    건너뛴 것이라, 실패로 세면 연속 실패 일시정지가 잘못 걸린다.
    """
    if (result or {}).get("skipped"):
        return "skipped"
    return "success" if (result or {}).get("success") else "failed"


async def sync_state(
    db: AsyncSession, blog_id: int, action_type: str,
    result: Dict[str, Any],
) -> None:
    """이 블로그가 속한 플로우의 실행 상태를 실제 결과로 맞춘다.

    Args:
        db: DB 세션
        blog_id: 블로그 ID
        action_type: 실행 상태의 액션 타입(generate/publish/republish)
        result: 워커 실행 결과 dict
    """
    from ..models.flow_blog import FlowBlog
    from ..models.flow_execution_state import FlowExecutionState

    outcome = outcome_of(result)
    if outcome == "skipped":
        return

    rows = (await db.execute(
        select(FlowBlog.flow_id).where(FlowBlog.blog_id == blog_id)
    )).fetchall()

    for (flow_id,) in rows:
        state = (await db.execute(
            select(FlowExecutionState).where(and_(
                FlowExecutionState.flow_id == flow_id,
                FlowExecutionState.action_type == action_type,
            ))
        )).scalar_one_or_none()
        if not state:
            continue

        if outcome == "success":
            state.last_success_at = datetime.now(KST)
            await db.commit()
            logger.info(
                "[FLOW_STATE] last_success_at 갱신 | flow=%s | action=%s",
                flow_id, action_type,
            )
        else:
            state.record_worker_failure()
            await db.commit()
            logger.warning(
                "[FLOW_STATE] 워커 실패 기록 | flow=%s | action=%s | 연속실패=%s",
                flow_id, action_type, state.consecutive_failures,
            )
