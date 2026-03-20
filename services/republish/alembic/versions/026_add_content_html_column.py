"""crawled_posts, generation_histories에 content_html 컬럼 추가

Revision ID: 026
Revises: 025
Create Date: 2026-03-19

생성된 HTML 콘텐츠를 DB에 저장하기 위해
두 테이블에 content_html 컬럼을 추가합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "crawled_posts",
        sa.Column("content_html", sa.Text(), nullable=True),
    )
    op.add_column(
        "generation_histories",
        sa.Column("content_html", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("crawled_posts", "content_html")
    op.drop_column("generation_histories", "content_html")
