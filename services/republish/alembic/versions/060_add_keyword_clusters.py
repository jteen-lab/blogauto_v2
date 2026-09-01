"""키워드 클러스터 + 검색 의도

Revision ID: 060
Revises: 059

목적:
    생산 단위를 키워드 1개 → **클러스터 1개(필러 1편 + 서브 N편)** 로 올린다.
    키워드 1개 = 제목 1개로는 대량 발행 수요를 못 받친다.

    의도(intent)를 후보에 남긴다. 같은 주제라도 묻는 것이 다르면 다른 글이다.

계획서: docs/plans/keyword_module_redesign_plan.md §2 B4
"""
import sqlalchemy as sa
from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None

TABLE = "keyword_clusters"
CANDIDATES = "keyword_candidates"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(CANDIDATES):
        return

    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("blog_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("topic_id", sa.Integer(), nullable=True),
            sa.Column("subtopic_id", sa.Integer(), nullable=True),
            sa.Column("intent", sa.String(length=20), nullable=True),
            sa.Column("size", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("total_volume", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False,
                      server_default="new"),
            sa.Column("titles_made", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "blog_id", "name",
                                name="uq_keyword_cluster"),
        )
        for col in ("user_id", "blog_id", "topic_id", "subtopic_id",
                    "intent", "status"):
            op.create_index(f"ix_{TABLE}_{col}", TABLE, [col])

    columns = {c["name"] for c in inspector.get_columns(CANDIDATES)}
    if "cluster_id" not in columns:
        op.add_column(CANDIDATES, sa.Column(
            "cluster_id", sa.Integer(), nullable=True,
            comment="소속 클러스터"))
        op.create_index(f"ix_{CANDIDATES}_cluster_id", CANDIDATES,
                        ["cluster_id"])
    if "intent" not in columns:
        op.add_column(CANDIDATES, sa.Column(
            "intent", sa.String(length=20), nullable=True,
            comment="검색 의도"))
        op.create_index(f"ix_{CANDIDATES}_intent", CANDIDATES, ["intent"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table(CANDIDATES):
        columns = {c["name"] for c in inspector.get_columns(CANDIDATES)}
        indexes = {i["name"] for i in inspector.get_indexes(CANDIDATES)}
        for name in ("cluster_id", "intent"):
            index = f"ix_{CANDIDATES}_{name}"
            if index in indexes:
                op.drop_index(index, table_name=CANDIDATES)
            if name in columns:
                op.drop_column(CANDIDATES, name)
    if inspector.has_table(TABLE):
        op.drop_table(TABLE)
