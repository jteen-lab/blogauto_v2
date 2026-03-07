"""user_settings에 gemini_api_key 컬럼 추가

Revision ID: 023
Revises: 022
Create Date: 2026-02-24

UserSettings 모델에 gemini_api_key 컬럼이 코드에 추가되었으나
대응하는 마이그레이션이 누락되어 API 키 조회 시
UndefinedColumnError가 발생하던 문제를 수정합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_settings",
        sa.Column("gemini_api_key", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_column("user_settings", "gemini_api_key")
