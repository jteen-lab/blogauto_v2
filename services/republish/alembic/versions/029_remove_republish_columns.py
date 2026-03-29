"""Module 레거시 컬럼 제거

Revision ID: 029
Revises: 028
Create Date: 2026-03-22

GP 통합: Module에서 republish 전용 스케줄/간격 컬럼을 제거합니다.
모든 스케줄 제어는 Growth Profile에서 담당합니다.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

# 제거 대상 컬럼 목록
COLUMNS_TO_DROP = [
    "schedule_matrix",
    "interval_mode",
    "manual_interval_minutes",
    "auto_daily_count",
    "jitter_enabled",
    "jitter_min_percent",
    "jitter_max_percent",
    "active_hours_start",
    "active_hours_end",
    "blackout_days",
    "cooldown_days",
    "priority",
    "platform_overrides",
    "min_post_count",
    # post_range_start, post_range_end는 021에서 이미 제거됨
]


def upgrade() -> None:
    """Module 테이블에서 레거시 republish 컬럼 제거"""
    for col in COLUMNS_TO_DROP:
        op.drop_column("modules", col)


def downgrade() -> None:
    """레거시 컬럼 복원 (역순)"""
    op.add_column("modules", sa.Column("min_post_count", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("modules", sa.Column("platform_overrides", JSONB(), nullable=True))
    op.add_column("modules", sa.Column("priority", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("modules", sa.Column("cooldown_days", sa.Integer(), nullable=True, server_default="7"))
    op.add_column("modules", sa.Column("blackout_days", JSONB(), nullable=True))
    op.add_column("modules", sa.Column("active_hours_end", sa.String(5), nullable=True, server_default="23:00"))
    op.add_column("modules", sa.Column("active_hours_start", sa.String(5), nullable=True, server_default="06:00"))
    op.add_column("modules", sa.Column("jitter_max_percent", sa.Integer(), nullable=True, server_default="25"))
    op.add_column("modules", sa.Column("jitter_min_percent", sa.Integer(), nullable=True, server_default="-15"))
    op.add_column("modules", sa.Column("jitter_enabled", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("modules", sa.Column("auto_daily_count", sa.Integer(), nullable=True, server_default="3"))
    op.add_column("modules", sa.Column("manual_interval_minutes", sa.Integer(), nullable=True, server_default="120"))
    op.add_column("modules", sa.Column("interval_mode", sa.String(20), nullable=True, server_default="auto"))
    op.add_column("modules", sa.Column("schedule_matrix", JSONB(), nullable=True))
