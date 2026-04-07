"""add concurrent execution guard fields to flow_execution_states

Revision ID: 034
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade():
    """동시 실행 가드 필드 + 연속 실패 카운터 추가"""
    op.add_column(
        'flow_execution_states',
        sa.Column(
            'is_running',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'flow_execution_states',
        sa.Column(
            'last_execution_started_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        'flow_execution_states',
        sa.Column(
            'consecutive_failures',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade():
    """동시 실행 가드 필드 + 연속 실패 카운터 제거"""
    op.drop_column('flow_execution_states', 'consecutive_failures')
    op.drop_column('flow_execution_states', 'last_execution_started_at')
    op.drop_column('flow_execution_states', 'is_running')
