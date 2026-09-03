"""분류표 변경 이력 — plan → apply → rollback 의 근거.

분류표(주제>하위주제>키워드)를 잘못 바꾸면 재고 전체의 분류가 틀어진다.
대량 수정 도구는 **되돌릴 수 있어야만** 열 수 있다.

한 행이 변경 하나를 나타낸다. `plan` 단계에서 만들어지고(적용 안 함),
사람이 승인하면 `apply` 로 넘어간다. 적용 전 상태를 `snapshot` 에 담아
두므로 언제든 되돌릴 수 있다.

`actor` 는 누가 요청했는지다 — 화면(ui) / 에이전트(agent) / 스크립트.
클로드 코드가 밖에서 호출해도 같은 통로를 지나므로 여기 남는다.

계획서: docs/plans/title_tab_workplan.md §9-4
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..core.database import Base

# 상태
STATUS_PLANNED = "planned"
STATUS_APPLIED = "applied"
STATUS_ROLLED_BACK = "rolled_back"
STATUS_FAILED = "failed"

# 요청 주체
ACTOR_UI = "ui"
ACTOR_AGENT = "agent"
ACTOR_SCRIPT = "script"
ACTORS = (ACTOR_UI, ACTOR_AGENT, ACTOR_SCRIPT)


class TaxonomyChange(Base):
    """분류표 변경 한 건."""

    __tablename__ = "taxonomy_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PLANNED,
        server_default=STATUS_PLANNED, index=True)
    actor: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ACTOR_UI, server_default=ACTOR_UI,
        comment="ui|agent|script — 누가 요청했나")
    summary: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="사람이 읽을 요약")

    payload: Mapped[str] = mapped_column(
        Text, nullable=False, comment="요청한 변경(JSON)")
    snapshot: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="적용 전 상태(JSON) — 롤백 근거")
    impact: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="plan 단계에서 계산한 영향(JSON)")
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    def payload_dict(self) -> Dict[str, Any]:
        """요청 내용. 깨진 JSON 은 빈 dict 로 — 이력 조회가 죽지 않게."""
        return _loads(self.payload)

    def snapshot_dict(self) -> Dict[str, Any]:
        return _loads(self.snapshot)

    def impact_dict(self) -> Dict[str, Any]:
        return _loads(self.impact)


def _loads(raw: Optional[str]) -> Dict[str, Any]:
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
