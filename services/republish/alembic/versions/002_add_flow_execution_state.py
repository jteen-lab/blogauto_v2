"""Add flow_execution_states table

Revision ID: 002_add_flow_execution_state
Revises: 001_refactor_to_module_flow
Create Date: 2026-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_flow_execution_state'
down_revision: Union[str, None] = '001_refactor_to_module_flow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create flow_execution_states table"""
    op.create_table(
        'flow_execution_states',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('flow_id', sa.Integer(), sa.ForeignKey('flows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module_id', sa.Integer(), sa.ForeignKey('modules.id', ondelete='CASCADE'), nullable=False),

        # 실행 상태 추적
        sa.Column('last_executed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='마지막 실행 시간'),
        sa.Column('next_execution_at', sa.DateTime(timezone=True), nullable=True,
                  comment='다음 예정 실행 시간'),

        # 일시정지 관련
        sa.Column('is_paused', sa.Boolean(), default=False, nullable=False,
                  comment='일시정지 상태'),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True,
                  comment='일시정지 시작 시간'),
        sa.Column('remaining_seconds', sa.Integer(), nullable=True,
                  comment='일시정지 시 남은 시간(초)'),

        # 실행 통계
        sa.Column('total_executions', sa.Integer(), default=0, nullable=False,
                  comment='총 실행 횟수'),
        sa.Column('successful_executions', sa.Integer(), default=0, nullable=False,
                  comment='성공 횟수'),
        sa.Column('failed_executions', sa.Integer(), default=0, nullable=False,
                  comment='실패 횟수'),

        # 메타
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 인덱스 생성
    op.create_index('ix_flow_execution_states_flow_id', 'flow_execution_states', ['flow_id'])
    op.create_index('ix_flow_execution_states_module_id', 'flow_execution_states', ['module_id'])

    # 복합 유니크 인덱스 (flow_id, module_id)
    op.create_unique_constraint(
        'uq_flow_execution_states_flow_module',
        'flow_execution_states',
        ['flow_id', 'module_id']
    )


def downgrade() -> None:
    """Drop flow_execution_states table"""
    op.drop_constraint('uq_flow_execution_states_flow_module', 'flow_execution_states', type_='unique')
    op.drop_index('ix_flow_execution_states_module_id', 'flow_execution_states')
    op.drop_index('ix_flow_execution_states_flow_id', 'flow_execution_states')
    op.drop_table('flow_execution_states')
