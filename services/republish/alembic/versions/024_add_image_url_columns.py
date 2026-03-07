"""generation_histories, crawled_posts에 image_url 컬럼 추가

Revision ID: 024
Revises: 023
Create Date: 2026-03-03

Phase C 이미지 생성 서비스를 위해
생성 이력과 크롤링 포스트에 이미지 URL 저장 컬럼을 추가합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generation_histories",
        sa.Column("image_url", sa.String(1000), nullable=True),
    )
    op.add_column(
        "crawled_posts",
        sa.Column("image_url", sa.String(1000), nullable=True),
    )


def downgrade():
    op.drop_column("crawled_posts", "image_url")
    op.drop_column("generation_histories", "image_url")
