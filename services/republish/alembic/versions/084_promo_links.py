"""홍보 링크 목록

수작업으로 글마다 손으로 붙이던 고지문·버튼을 목록에서 고르게 한다.
CPA 오퍼는 광고 심의 규칙을 관리하는 무거운 체계라, 버튼 주소 하나
쓰자고 그 절차를 밟게 하지 않는다.

Revision ID: 084
Revises: 083
"""
from alembic import op
import sqlalchemy as sa

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """promo_links 생성."""
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "promo_links"):
        return

    op.create_table(
        "promo_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("button_text", sa.String(200), nullable=False),
        sa.Column("notice", sa.String(300), nullable=True),
        sa.Column("blog_id", sa.Integer(), nullable=True),
        sa.Column("cpa_offer_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cpa_offer_id"], ["cpa_offers.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_promo_links_blog_id", "promo_links", ["blog_id"])
    op.create_index("ix_promo_links_is_active", "promo_links", ["is_active"])


def downgrade() -> None:
    """되돌리기 — 목록이 사라진다."""
    op.drop_table("promo_links")
