"""Add last_success_at to flow_execution_states

Revision ID: 037
Create Date: 2026-04-23

목적:
    실행 실패 시에도 last_executed_at을 갱신하여 스케줄이 항상 전진하도록
    변경함에 따라, 마지막 성공 시점을 별도 컬럼으로 추적합니다.
"""
from alembic import op
import sqlalchemy as sa


revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """last_success_at 컬럼 추가 및 기존 데이터 초기화."""
    op.add_column(
        'flow_execution_states',
        sa.Column(
            'last_success_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='마지막 성공 시점'
        )
    )
    # 기존 last_executed_at 값으로 초기화 (기존 기록은 성공 시에만 갱신되었으므로)
    op.execute(
        "UPDATE flow_execution_states SET last_success_at = last_executed_at"
    )


def downgrade() -> None:
    """last_success_at 컬럼 제거."""
    op.drop_column('flow_execution_states', 'last_success_at')
