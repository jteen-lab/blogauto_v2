"""Brave 검색 토큰 보관

클로드가 자료를 찾을 때 쓰는 검색과 같은 곳을 쓴다. 일반 자료 갈래에서
네이버와 함께 던진다.

Revision ID: 086
Revises: 085
"""
from alembic import op
import sqlalchemy as sa

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """user_settings 에 칸 하나."""
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("user_settings")]
    if "brave_api_key" in cols:
        return
    op.add_column("user_settings",
                  sa.Column("brave_api_key", sa.String(255), nullable=True))


def downgrade() -> None:
    """되돌리기."""
    op.drop_column("user_settings", "brave_api_key")
