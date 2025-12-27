"""Phase A-1: Refactor to Module/Flow System

Revision ID: 001_refactor_to_module_flow
Revises:
Create Date: 2025-12-28 12:00:00.000000

Changes:
1. Create new module_types table (master data)
2. Create modules table (replace publish_profiles)
3. Create flows table (replace profile_groups)
4. Create flow_modules table (replace group_profile_links)
5. Create flow_blogs table (replace blog_group_links)
6. Remove is_active fields from profiles/groups (managed by flows.status)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '001_refactor_to_module_flow'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create new module/flow schema"""

    # 1. Create module_types table (master data)
    op.create_table(
        'module_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        comment='모듈 타입 마스터 테이블'
    )
    op.create_index(op.f('ix_module_types_id'), 'module_types', ['id'], unique=False)
    op.create_unique_constraint('uq_module_types_code', 'module_types', ['code'])

    # 2. Create modules table (replace publish_profiles)
    op.create_table(
        'modules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('module_type_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Schedule settings (from publish_profiles)
        sa.Column('schedule_matrix', JSONB(), nullable=True),
        sa.Column('manual_interval_minutes', sa.Integer(), nullable=True),

        # Republish settings (from publish_profiles)
        sa.Column('min_post_count', sa.Integer(), server_default='10'),
        sa.Column('post_range_start', sa.Integer(), server_default='1'),
        sa.Column('post_range_end', sa.Integer(), nullable=True),
        sa.Column('interval_mode', sa.String(length=10), server_default='manual'),
        sa.Column('auto_daily_count', sa.Integer(), nullable=True),
        sa.Column('jitter_enabled', sa.Boolean(), server_default='true'),
        sa.Column('jitter_min_percent', sa.Integer(), server_default='-20'),
        sa.Column('jitter_max_percent', sa.Integer(), server_default='30'),
        sa.Column('active_hours_start', sa.String(length=5), server_default='09:00'),
        sa.Column('active_hours_end', sa.String(length=5), server_default='22:00'),
        sa.Column('blackout_days', JSONB(), server_default='[]'),
        sa.Column('cooldown_days', sa.Integer(), server_default='7'),
        sa.Column('priority', sa.Integer(), server_default='1'),
        sa.Column('platform_overrides', JSONB(), server_default='{}'),

        # Type-specific settings
        sa.Column('settings', JSONB(), server_default='{}'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['module_type_id'], ['module_types.id'], ),
        comment='모듈 테이블 - 기존 publish_profiles 대체'
    )
    op.create_index(op.f('ix_modules_id'), 'modules', ['id'], unique=False)
    op.create_index(op.f('ix_modules_user_id'), 'modules', ['user_id'], unique=False)

    # 3. Create flows table (replace profile_groups)
    op.create_table(
        'flows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='inactive', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        comment='플로우 테이블 - 기존 profile_groups 대체'
    )
    op.create_index(op.f('ix_flows_id'), 'flows', ['id'], unique=False)
    op.create_index(op.f('ix_flows_user_id'), 'flows', ['user_id'], unique=False)

    # 4. Create flow_modules table (replace group_profile_links)
    op.create_table(
        'flow_modules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('flow_id', sa.Integer(), nullable=False),
        sa.Column('module_id', sa.Integer(), nullable=False),
        sa.Column('execution_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['module_id'], ['modules.id'], ondelete='CASCADE'),
        comment='플로우-모듈 연결 테이블'
    )
    op.create_index(op.f('ix_flow_modules_id'), 'flow_modules', ['id'], unique=False)
    op.create_unique_constraint('uq_flow_module', 'flow_modules', ['flow_id', 'module_id'])

    # 5. Create flow_blogs table (replace blog_group_links)
    op.create_table(
        'flow_blogs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('flow_id', sa.Integer(), nullable=False),
        sa.Column('blog_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blog_id'], ['blogs.id'], ondelete='CASCADE'),
        comment='플로우-블로그 연결 테이블'
    )
    op.create_index(op.f('ix_flow_blogs_id'), 'flow_blogs', ['id'], unique=False)
    op.create_unique_constraint('uq_flow_blog', 'flow_blogs', ['flow_id', 'blog_id'])

    # 6. Insert default module types
    module_types_table = sa.table('module_types',
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('icon', sa.String),
        sa.column('display_order', sa.Integer)
    )

    op.bulk_insert(module_types_table, [
        {'code': 'prompt', 'name': '프롬프트', 'icon': '💭', 'display_order': 1},
        {'code': 'generate', 'name': '생성', 'icon': '🤖', 'display_order': 2},
        {'code': 'publish', 'name': '발행', 'icon': '📤', 'display_order': 3},
        {'code': 'republish', 'name': '재발행', 'icon': '🔄', 'display_order': 4}
    ])


def downgrade():
    """Drop new module/flow schema"""

    # Drop in reverse order to handle foreign key constraints
    op.drop_table('flow_blogs')
    op.drop_table('flow_modules')
    op.drop_table('flows')
    op.drop_table('modules')
    op.drop_table('module_types')