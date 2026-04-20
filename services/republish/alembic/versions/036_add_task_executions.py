"""add task_executions table

Revision ID: 036
Create Date: 2026-04-06

목적:
    Celery 작업 실행 상태를 DB에 기록하여
    태스크 이력 조회 및 재시도 관리를 지원합니다.
"""
from alembic import op
import sqlalchemy as sa


revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """task_executions 테이블 생성.

    개발 환경에서 SQLAlchemy create_all로 이미 생성된 경우 스킵.
    """
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    if 'task_executions' in inspector.get_table_names():
        print("[migration 036] task_executions 이미 존재 - 스킵")
        return

    op.create_table(
        'task_executions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.String(255), unique=True, nullable=False),
        sa.Column('task_name', sa.String(100), nullable=False),
        sa.Column('queue', sa.String(50), nullable=False),
        sa.Column(
            'blog_id',
            sa.Integer(),
            sa.ForeignKey('blogs.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'module_id',
            sa.Integer(),
            sa.ForeignKey('modules.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'flow_id',
            sa.Integer(),
            sa.ForeignKey('flows.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'status',
            sa.String(20),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('priority', sa.Integer(), server_default='5'),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 인덱스 생성
    op.create_index(
        'ix_task_executions_task_id',
        'task_executions',
        ['task_id'],
        unique=True,
    )
    op.create_index(
        'ix_task_executions_status',
        'task_executions',
        ['status'],
    )
    op.create_index(
        'ix_task_executions_blog_id',
        'task_executions',
        ['blog_id'],
    )
    op.create_index(
        'ix_task_blog_status',
        'task_executions',
        ['blog_id', 'status'],
    )
    op.create_index(
        'ix_task_created',
        'task_executions',
        ['created_at'],
    )


def downgrade() -> None:
    """task_executions 테이블 삭제."""
    op.drop_table('task_executions')
