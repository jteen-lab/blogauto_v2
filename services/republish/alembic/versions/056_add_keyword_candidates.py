"""키워드 후보 테이블 — 수요를 먼저 재는 수집 실험

기존 seed_keywords 를 건드리지 않는다. 운영 중인 파이프라인과 섞이면
무엇이 원인인지 가릴 수 없다.

Revision ID: 056
Revises: 055
"""
import sqlalchemy as sa
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "keyword_candidates"):
        return

    op.create_table(
        "keyword_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=200), nullable=False),
        sa.Column("seed", sa.String(length=200), nullable=True),
        sa.Column("blog_id", sa.Integer(), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("subtopic_id", sa.Integer(), nullable=True),
        sa.Column("search_volume_pc", sa.Integer(), nullable=True),
        sa.Column("search_volume_mobile", sa.Integer(), nullable=True),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("competition", sa.String(length=10), nullable=True),
        sa.Column("doc_count", sa.Integer(), nullable=True),
        sa.Column("saturation", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(length=10), nullable=False,
                  server_default="pending"),
        sa.Column("verdict_reason", sa.String(length=120), nullable=True),
        sa.Column("risk_label", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False,
                  server_default="naver_ads"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "keyword", name="uq_keyword_candidate"),
    )
    for col in ("user_id", "keyword", "blog_id", "topic_id", "subtopic_id",
                "search_volume", "saturation", "verdict"):
        op.create_index(f"ix_keyword_candidates_{col}", "keyword_candidates",
                        [col])


def downgrade() -> None:
    op.drop_table("keyword_candidates")
