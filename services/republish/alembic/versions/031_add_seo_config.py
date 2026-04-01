"""add seo_config column to blogs

Revision ID: 031
Revises: 030
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("blogs", sa.Column("seo_config", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("blogs", "seo_config")
