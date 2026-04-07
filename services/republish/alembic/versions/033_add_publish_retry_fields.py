"""add publish retry tracking fields to crawled_posts

Revision ID: 033
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade():
    """발행 재시도 추적 필드 추가"""
    op.add_column(
        'crawled_posts',
        sa.Column(
            'publish_attempts',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'crawled_posts',
        sa.Column(
            'last_publish_error',
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        'crawled_posts',
        sa.Column(
            'last_publish_attempted_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade():
    """발행 재시도 추적 필드 제거"""
    op.drop_column('crawled_posts', 'last_publish_attempted_at')
    op.drop_column('crawled_posts', 'last_publish_error')
    op.drop_column('crawled_posts', 'publish_attempts')
