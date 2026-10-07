"""건강형 글인데 인용할 공식 출처가 0건이면 만들지 않는다(보류).

레시피노트 '카무트 효능과 부작용'(10/5)은 건강형으로 판정됐지만 공식
출처 검색이 기관 첫 화면만 돌려줘 인용 후보가 0건이었다. 규칙대로
'참고 자료' 는 빠졌는데 글은 그대로 나갔고, 출처 없는 수치(셀레늄
20mcg·하루 90g)가 실렸다. 근거 없는 건강 글은 내보내지 않는다.

근거 등급 보류(evidence C)와 같은 방식이다 — 제목은 지우지 않고
hold_count 를 올린다. 3회면 보류 제목 검토 목록에 오른다.

순서도: docs/flowcharts/title_topic_gate.md (건강 글 보류)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ...core.logger import get_logger

logger = get_logger("health_hold", "app.log")

REASON = "건강형 주제인데 인용할 공식 출처(질병관리청·식약처 등) 0건"


def needs_hold(ref_result: Any) -> bool:
    """건강형이고 공식 출처가 없으면 True."""
    return bool(getattr(ref_result, "health", False)) and not getattr(
        ref_result, "official_refs", 0)


async def hold_if_unsourced(db, source_title, ref_result,
                            working_title: str) -> Optional[str]:
    """보류해야 하면 제목에 기록하고 사유를 돌려준다. 아니면 None."""
    if not needs_hold(ref_result):
        return None
    source_title.hold_count = (source_title.hold_count or 0) + 1
    source_title.last_held_at = datetime.now()
    source_title.hold_reason = REASON
    await db.commit()
    logger.warning("[HEALTH_HOLD] 보류 %d회 | '%s' | %s",
                   source_title.hold_count, (working_title or "")[:40], REASON)
    return REASON
