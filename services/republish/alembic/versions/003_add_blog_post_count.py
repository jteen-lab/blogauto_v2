"""Add total_post_count and post_count_updated_at to blogs table

Revision ID: 003_add_blog_post_count
Revises: 002_add_flow_execution_state
Create Date: 2026-01-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_blog_post_count'
down_revision: Union[str, None] = '002_add_flow_execution_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add total_post_count and post_count_updated_at columns to blogs table"""
    op.add_column(
        'blogs',
        sa.Column(
            'total_post_count',
            sa.Integer(),
            nullable=True,
            comment='누적 포스트 수'
        )
    )
    op.add_column(
        'blogs',
        sa.Column(
            'post_count_updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='포스트 수 업데이트 시점'
        )
    )


def downgrade() -> None:
    """Remove total_post_count and post_count_updated_at columns from blogs table"""
    op.drop_column('blogs', 'post_count_updated_at')
    op.drop_column('blogs', 'total_post_count')
