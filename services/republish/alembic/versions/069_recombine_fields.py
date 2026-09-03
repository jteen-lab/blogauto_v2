"""정식제목에 재조합·최신성 필드 추가

Revision ID: 069
Revises: 068

배경:
    재조합이 발행 직전에만 일어나 결과가 휘발됐다. 정식제목 탭에서
    수작업으로 재조합하고 **결과를 재고로 남긴다.**

    같은 그룹 안에 넣되(원본 group_id 승계) 재조합 제목임을 표시해,
    생성 모듈이 그 제목을 고르면 이중 재조합을 건너뛴다.

계획서: docs/plans/title_tab_workplan.md §4-2 · §4-3 · §4-6
"""
import sqlalchemy as sa
from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None

TABLE = "main_titles"
COLUMNS = (
    # 원본 정식제목 ID. 값이 있으면 재조합 결과다.
    ("recombined_from_id", sa.Integer(), True),
    ("recombine_style", sa.String(length=30), True),
    # 최신성 점검 시각. 연도가 박힌 낡은 제목을 골라내는 데 쓴다.
    ("freshness_checked_at", sa.DateTime(timezone=True), True),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_, nullable in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=nullable))
    if "recombined_from_id" not in existing:
        op.create_index(f"ix_{TABLE}_recombined_from_id", TABLE,
                        ["recombined_from_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, _t, _n in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
