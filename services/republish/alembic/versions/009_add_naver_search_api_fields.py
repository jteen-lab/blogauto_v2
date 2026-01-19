"""네이버 검색 API 필드 추가

Revision ID: 009
Revises: 008
Create Date: 2026-01-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """네이버 검색 API 필드 추가"""
    # 네이버 검색 API (블로그 검색 결과 수집용)
    op.add_column('user_settings', sa.Column('naver_search_client_id', sa.String(255), nullable=True))
    op.add_column('user_settings', sa.Column('naver_search_client_secret', sa.String(255), nullable=True))


def downgrade() -> None:
    """네이버 검색 API 필드 삭제"""
    op.drop_column('user_settings', 'naver_search_client_secret')
    op.drop_column('user_settings', 'naver_search_client_id')
