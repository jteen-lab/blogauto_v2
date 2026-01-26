"""add action_logs table

Revision ID: 014
Revises: 013
Create Date: 2025-01-26

Phase M-2: 동작 로그 테이블 추가
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # action_logs 테이블 생성
    op.create_table(
        'action_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('level', sa.String(20), nullable=False, server_default='INFO'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # 인덱스 추가
    op.create_index('ix_action_logs_timestamp', 'action_logs', ['timestamp'], unique=False)
    op.create_index('ix_action_logs_level', 'action_logs', ['level'], unique=False)
    op.create_index('ix_action_logs_category', 'action_logs', ['category'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_action_logs_category', 'action_logs')
    op.drop_index('ix_action_logs_level', 'action_logs')
    op.drop_index('ix_action_logs_timestamp', 'action_logs')
    op.drop_table('action_logs')
