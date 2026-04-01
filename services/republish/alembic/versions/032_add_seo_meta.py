"""add seo_meta column to crawled_posts

Revision ID: 032
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crawled_posts', sa.Column('seo_meta', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('crawled_posts', 'seo_meta')
