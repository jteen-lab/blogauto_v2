"""키워드 엔진별 지표 테이블 + 월간 발행량

Revision ID: 059
Revises: 058

목적:
    1) 지표를 엔진별로 뗀다. 후보 테이블이 검색량·문서수를 한 벌만 갖고
       있어 구글 지표를 더할 자리가 없었다.
    2) 공급 지표를 누적 문서수 → **최근 30일 발행량**으로 옮긴다.
       누적은 10년치 총합이라 지금 경쟁이 붙는지 말해 주지 않는다.

기존 `keyword_candidates` 컬럼은 그대로 둔다(화면이 그 값을 읽는다).
네이버 지표는 후보 행에도 미러링해 화면을 바꾸지 않고 넘어간다.

계획서: docs/plans/keyword_module_redesign_plan.md
"""
import sqlalchemy as sa
from alembic import op

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None

TABLE = "keyword_metrics"
CANDIDATES = "keyword_candidates"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table(CANDIDATES):
        return

    columns = {c["name"] for c in inspector.get_columns(CANDIDATES)}
    if "monthly_pub_count" not in columns:
        op.add_column(CANDIDATES, sa.Column(
            "monthly_pub_count", sa.Integer(), nullable=True,
            comment="최근 30일 발행량(기본 엔진 미러)"))

    if inspector.has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=False),
        sa.Column("search_volume_pc", sa.Integer(), nullable=True),
        sa.Column("search_volume_mobile", sa.Integer(), nullable=True),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("volume_is_range", sa.Integer(), nullable=True),
        sa.Column("competition", sa.String(length=10), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=True),
        sa.Column("monthly_pub_count", sa.Integer(), nullable=True),
        sa.Column("pub_count_capped", sa.Integer(), nullable=True),
        sa.Column("saturation", sa.Float(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], [f"{CANDIDATES}.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "engine",
                            name="uq_keyword_metric"),
    )
    for col in ("candidate_id", "engine", "search_volume", "saturation"):
        op.create_index(f"ix_{TABLE}_{col}", TABLE, [col])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table(TABLE):
        op.drop_table(TABLE)
    if inspector.has_table(CANDIDATES):
        columns = {c["name"] for c in inspector.get_columns(CANDIDATES)}
        if "monthly_pub_count" in columns:
            op.drop_column(CANDIDATES, "monthly_pub_count")
