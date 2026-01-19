"""네이버 데이터랩 및 구글 키워드 플래너 API 필드 추가

Revision ID: 008
Revises: 007
Create Date: 2025-01-17

Features:
- user_settings 테이블에 네이버 데이터랩 API 필드 추가
  - naver_datalab_client_id: 클라이언트 ID
  - naver_datalab_client_secret: 클라이언트 시크릿
- user_settings 테이블에 구글 키워드 플래너 API 필드 추가
  - google_ads_developer_token: 개발자 토큰
  - google_ads_client_id: OAuth 클라이언트 ID
  - google_ads_client_secret: OAuth 클라이언트 시크릿
  - google_ads_refresh_token: OAuth 리프레시 토큰
  - google_ads_customer_id: Google Ads 고객 ID
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 네이버 데이터랩 API 필드 추가
    op.add_column(
        'user_settings',
        sa.Column(
            'naver_datalab_client_id',
            sa.String(255),
            nullable=True,
            comment='네이버 데이터랩 클라이언트 ID'
        )
    )

    op.add_column(
        'user_settings',
        sa.Column(
            'naver_datalab_client_secret',
            sa.String(255),
            nullable=True,
            comment='네이버 데이터랩 클라이언트 시크릿'
        )
    )

    # 구글 키워드 플래너 API 필드 추가
    op.add_column(
        'user_settings',
        sa.Column(
            'google_ads_developer_token',
            sa.String(255),
            nullable=True,
            comment='Google Ads 개발자 토큰'
        )
    )

    op.add_column(
        'user_settings',
        sa.Column(
            'google_ads_client_id',
            sa.String(255),
            nullable=True,
            comment='Google Ads OAuth 클라이언트 ID'
        )
    )

    op.add_column(
        'user_settings',
        sa.Column(
            'google_ads_client_secret',
            sa.String(255),
            nullable=True,
            comment='Google Ads OAuth 클라이언트 시크릿'
        )
    )

    op.add_column(
        'user_settings',
        sa.Column(
            'google_ads_refresh_token',
            sa.String(512),
            nullable=True,
            comment='Google Ads OAuth 리프레시 토큰'
        )
    )

    op.add_column(
        'user_settings',
        sa.Column(
            'google_ads_customer_id',
            sa.String(50),
            nullable=True,
            comment='Google Ads 고객 ID'
        )
    )


def downgrade() -> None:
    # 구글 키워드 플래너 API 필드 삭제
    op.drop_column('user_settings', 'google_ads_customer_id')
    op.drop_column('user_settings', 'google_ads_refresh_token')
    op.drop_column('user_settings', 'google_ads_client_secret')
    op.drop_column('user_settings', 'google_ads_client_id')
    op.drop_column('user_settings', 'google_ads_developer_token')

    # 네이버 데이터랩 API 필드 삭제
    op.drop_column('user_settings', 'naver_datalab_client_secret')
    op.drop_column('user_settings', 'naver_datalab_client_id')
