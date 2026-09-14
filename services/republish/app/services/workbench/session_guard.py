"""리허설 세션 — 실제 경로를 그대로 돌리되 아무것도 남기지 않는다.

**왜 이 방식인가**: 실행기마다 dry_run 을 심으면 분기가 늘고, 분기가 늘면
"테스트는 됐는데 실제는 다르다"가 다시 생긴다. 대신 **저장의 문 자체를
잠근다** — 실행 코드는 한 줄도 다르게 돌지 않는다.

    실행기가 commit() 을 불러도  →  flush() 로 바꿔 처리한다
    (같은 세션 안에서는 저장된 것처럼 보이고, id 도 발급된다)
    회차가 끝나면               →  rollback() 으로 전부 되돌린다

이렇게 하면 생성기의 "제목 소진", 키워드의 "풀 채택" 같은 저장이 **화면에는
보이지만 데이터에는 남지 않는다.**

**한계 — 알고 써야 한다**:
- 실행 도중 **자기 세션을 새로 여는 코드**는 잠기지 않는다(예: AI 키 사용량
  카운터). 그런 기록은 실제로 남는다 — API 를 실제로 썼으니 남는 게 맞다.
- 디스크에 쓰는 파일(생성 이미지)은 남는다. 무해한 임시 산출물이다.
- 외부 서비스 호출(발행·Tally)은 되돌릴 수 없으므로 작업대가 아예 부르지
  않는다(계획서 §9-2).

계획서: docs/plans/test_workbench_plan.md §9-1
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("workbench_session", "app.log")


class RehearsalSession:
    """commit 을 flush 로 바꿔 받는 세션 대리인.

    실행기는 평소처럼 db.commit() 을 부르지만 트랜잭션은 닫히지 않는다.
    그 외 모든 동작(add·get·execute·flush…)은 원본 세션에 그대로 위임한다.
    """

    def __init__(self, inner: AsyncSession):
        # __setattr__ 를 거치지 않도록 직접 넣는다
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "commit_calls", 0)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_inner"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("commit_calls",):
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_inner"), name, value)

    async def commit(self) -> None:
        """저장 요청을 flush 로 받는다. 몇 번 왔는지 세어 화면이 말한다."""
        object.__setattr__(self, "commit_calls",
                           object.__getattribute__(self, "commit_calls") + 1)
        await object.__getattribute__(self, "_inner").flush()

    async def discard(self) -> None:
        """회차 종료 — 전부 되돌린다."""
        inner = object.__getattribute__(self, "_inner")
        await inner.rollback()
        logger.info("[WORKBENCH] 리허설 종료 | 보류된 저장 %d건 폐기",
                    object.__getattribute__(self, "commit_calls"))


def rehearse(db: AsyncSession) -> RehearsalSession:
    """세션을 리허설 모드로 감싼다."""
    return RehearsalSession(db)
