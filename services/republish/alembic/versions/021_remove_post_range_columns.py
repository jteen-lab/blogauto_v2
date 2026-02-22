"""Remove post_range_start/end columns from modules

Revision ID: 021
Revises: 020
Create Date: 2026-02-21

Growth Profile의 stages.post_count_min/max로 완전 대체.
Phase M(migrate_post_range_to_gp.py)에서 기존 데이터 마이그레이션 완료 후 실행.
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("modules", "post_range_start")
    op.drop_column("modules", "post_range_end")


def downgrade():
    op.add_column(
        "modules",
        sa.Column("post_range_start", sa.Integer(), server_default="1", nullable=True),
    )
    op.add_column(
        "modules",
        sa.Column("post_range_end", sa.Integer(), nullable=True),
    )
