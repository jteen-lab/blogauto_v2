"""법제처 인증값 보관

법 근거가 필요한 글에서 네이버 전문자료 대신 원문을 쓴다. 인증값은
사용자가 정한 아이디 문자열이고 주소에 그대로 실린다 — 비밀값이
아니라 마스킹하지 않는다.

Revision ID: 085
Revises: 084
"""
from alembic import op
import sqlalchemy as sa

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """user_settings 에 칸 하나."""
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("user_settings")]
    if "law_api_oc" in cols:
        return
    op.add_column("user_settings",
                  sa.Column("law_api_oc", sa.String(100), nullable=True))


def downgrade() -> None:
    """되돌리기."""
    op.drop_column("user_settings", "law_api_oc")
