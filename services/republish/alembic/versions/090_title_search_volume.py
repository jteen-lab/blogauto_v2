"""제목 검색량 기억 칸 — N2 검색량 바닥선(2026-10-23, 마케팅 지시·형 승인)

제목의 맨 앞 검색어 후보를 네이버 검색광고로 재서 가장 큰 검색량과 잰 날을
남긴다. 바닥선(기본 50) 아래면 그 회차는 건너뛰고 다음 제목을 쓴다.
제목은 보관하지 않는다 — 나중에 바닥선을 바꾸면 남겨 둔 검색량으로 다시 판정한다.
같은 제목을 매 회차 다시 재지 않도록 잰 날을 30일 기억한다.

Revision ID: 090
Revises: 089

순서도: docs/flowcharts/title_lead_keyword.md
"""
import sqlalchemy as sa
from alembic import op

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None

COLUMNS = (
    ("search_volume", sa.Integer()),
    ("search_volume_at", sa.DateTime(timezone=True)),
)


def _existing() -> set:
    """main_titles 에 이미 있는 컬럼 이름."""
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("main_titles")}


def upgrade() -> None:
    """검색량·잰 날 컬럼을 더한다(둘 다 비워 둘 수 있음)."""
    have = _existing()
    for name, type_ in COLUMNS:
        if name not in have:
            op.add_column("main_titles", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """두 컬럼을 뺀다."""
    have = _existing()
    for name, _ in COLUMNS:
        if name in have:
            op.drop_column("main_titles", name)
