"""FES에 blog_id 컬럼 추가 (블로그별 간격 추적)

Revision ID: 022
Revises: 021
Create Date: 2026-02-22

Growth Profile Phase D: 블로그별 독립 간격 추적을 위해
FlowExecutionState에 blog_id FK 컬럼을 추가합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "flow_execution_states",
        sa.Column(
            "blog_id",
            sa.Integer(),
            sa.ForeignKey("blogs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_fes_flow_module_blog",
        "flow_execution_states",
        ["flow_id", "module_id", "blog_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_fes_flow_module_blog", "flow_execution_states")
    op.drop_column("flow_execution_states", "blog_id")
