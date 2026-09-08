"""CPA 오퍼 테이블

프로모션 하나의 원문·규칙·상태를 담는다. 원문을 보존하는 것이 핵심 —
구조화 결과는 파생물이고 광고주와 다툼이 생기면 원문이 근거다.

Revision ID: 078
Revises: 077
"""
from alembic import op
import sqlalchemy as sa

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """cpa_offers 생성. 이미 있으면(create_all 선행) 건너뛴다."""
    bind = op.get_bind()
    if sa.inspect(bind).has_table("cpa_offers"):
        return

    op.create_table(
        "cpa_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("network", sa.String(50), nullable=False,
                  server_default="adlix"),
        sa.Column("offer_code", sa.String(50), nullable=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("advertiser", sa.String(200), nullable=True),
        sa.Column("vertical", sa.String(100), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("conversion", sa.JSON(), nullable=True),
        sa.Column("ftc_notice", sa.Text(), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=True),
        sa.Column("unmatched", sa.JSON(), nullable=True),
        sa.Column("conflicts", sa.JSON(), nullable=True),
        sa.Column("landing_url", sa.String(500), nullable=True),
        sa.Column("subid_param", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="draft"),
        sa.Column("recheck_due", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_cpa_offers_offer_code", "cpa_offers", ["offer_code"])
    op.create_index("ix_cpa_offers_status", "cpa_offers", ["status"])
    op.create_index("ix_cpa_offers_recheck_due", "cpa_offers", ["recheck_due"])
    op.create_index("ix_cpa_offers_is_deleted", "cpa_offers", ["is_deleted"])


def downgrade() -> None:
    op.drop_table("cpa_offers")
