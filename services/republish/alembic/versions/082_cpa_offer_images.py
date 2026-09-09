"""오퍼 이미지

오퍼가 제공하는 스크린샷·심의 배너를 등록해 둔다. 심의 배너 외 이미지를
쓰면 위반인 오퍼가 있어, 쓸 수 있는 것을 미리 정해 두어야 한다.

Revision ID: 082
Revises: 081
"""
from alembic import op
import sqlalchemy as sa

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("cpa_offers")}
    if "images" in have:
        return
    op.add_column("cpa_offers", sa.Column("images", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cpa_offers", "images")
