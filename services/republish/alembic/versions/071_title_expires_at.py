"""제목에 시의성 만료일 추가 (L3 뉴스)

Revision ID: 071
Revises: 070

배경:
    뉴스 소재로 만든 제목은 2주 뒤에 쓰면 이미 낡았다. L1(키워드 기반)
    제목에는 없는 성질이라 만료일을 따로 둔다.

    만료된 제목은 재고 선택에서 제외한다. 삭제하지는 않는다 — 무엇이
    얼마나 만료됐는지 보이는 편이 낫다.

계획서: docs/plans/title_tab_workplan.md §3-2
"""
import sqlalchemy as sa
from alembic import op

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None

TARGETS = ("temp_titles", "main_titles")
COLUMN = "expires_at"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in TARGETS:
        if not inspector.has_table(table):
            continue
        if COLUMN in {c["name"] for c in inspector.get_columns(table)}:
            continue
        op.add_column(table, sa.Column(
            COLUMN, sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_{COLUMN}", table, [COLUMN])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in TARGETS:
        if not inspector.has_table(table):
            continue
        if COLUMN in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, COLUMN)
