"""Add params column to modules table

Revision ID: 005
Revises: 003
Create Date: 2026-01-14

Changes:
1. modules: Add params JSONB column for schema-based dynamic form parameters
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '003_add_blog_post_count'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add params column to modules table"""

    # modules 테이블에 params 컬럼 추가
    op.add_column('modules', sa.Column(
        'params', postgresql.JSONB(), nullable=True, server_default='{}',
        comment='param_schema 기반 파라미터'
    ))


def downgrade() -> None:
    """Remove params column from modules table"""

    op.drop_column('modules', 'params')
