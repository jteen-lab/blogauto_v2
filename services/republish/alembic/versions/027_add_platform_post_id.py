"""crawled_posts에 platform_post_id 컬럼 추가

Revision ID: 027
Revises: 026
Create Date: 2026-03-22

플랫폼 발행 후 반환되는 포스트 ID를 저장합니다.
(WordPress post ID, Blogger post ID)
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawled_posts",
        sa.Column(
            "platform_post_id",
            sa.String(100),
            nullable=True,
            comment="플랫폼 발행 후 반환된 포스트 ID",
        ),
    )


def downgrade() -> None:
    op.drop_column("crawled_posts", "platform_post_id")
