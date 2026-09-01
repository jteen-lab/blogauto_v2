"""키워드 성과 되먹임 컬럼

Revision ID: 061
Revises: 060

목적:
    글을 내보내고 끝이 아니라, **실제로 노출됐는지**를 회수해 다음 키워드
    선정에 반영한다. 지금은 이 고리가 없어 잘 되는 축과 안 되는 축을
    구분하지 못한다.

    perf_score: 관찰된 성과(구글 노출수 기반). 아직 안 재면 NULL.
    perf_checked_at: 마지막으로 확인한 시각.

계획서: docs/plans/keyword_module_redesign_plan.md §6-3
"""
import sqlalchemy as sa
from alembic import op

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None

TABLE = "keyword_candidates"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    columns = {c["name"] for c in inspector.get_columns(TABLE)}

    if "perf_score" not in columns:
        op.add_column(TABLE, sa.Column(
            "perf_score", sa.Float(), nullable=True,
            comment="관찰된 성과(노출 기반). 높을수록 잘 먹힌 축"))
        op.create_index(f"ix_{TABLE}_perf_score", TABLE, ["perf_score"])
    if "perf_checked_at" not in columns:
        op.add_column(TABLE, sa.Column(
            "perf_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    if f"ix_{TABLE}_perf_score" in indexes:
        op.drop_index(f"ix_{TABLE}_perf_score", table_name=TABLE)
    for name in ("perf_score", "perf_checked_at"):
        if name in columns:
            op.drop_column(TABLE, name)
