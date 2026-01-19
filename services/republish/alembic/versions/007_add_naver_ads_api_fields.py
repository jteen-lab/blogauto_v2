"""네이버 검색광고 API 필드 추가

Revision ID: 007
Revises: 006
Create Date: 2025-01-17

Features:
- user_settings 테이블에 네이버 검색광고 API 필드 추가
  - naver_ads_api_key: API 키
  - naver_ads_secret_key: Secret 키
  - naver_ads_customer_id: 고객 ID
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # naver_ads_api_key 컬럼 추가
    op.add_column(
        'user_settings',
        sa.Column(
            'naver_ads_api_key',
            sa.String(255),
            nullable=True,
            comment='네이버 검색광고 API 키'
        )
    )

    # naver_ads_secret_key 컬럼 추가
    op.add_column(
        'user_settings',
        sa.Column(
            'naver_ads_secret_key',
            sa.String(255),
            nullable=True,
            comment='네이버 검색광고 Secret 키'
        )
    )

    # naver_ads_customer_id 컬럼 추가
    op.add_column(
        'user_settings',
        sa.Column(
            'naver_ads_customer_id',
            sa.String(50),
            nullable=True,
            comment='네이버 검색광고 고객 ID'
        )
    )


def downgrade() -> None:
    # 컬럼 삭제
    op.drop_column('user_settings', 'naver_ads_customer_id')
    op.drop_column('user_settings', 'naver_ads_secret_key')
    op.drop_column('user_settings', 'naver_ads_api_key')
