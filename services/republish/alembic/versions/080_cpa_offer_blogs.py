"""오퍼에 담당 블로그

제목을 만들어도 아무 블로그가 뽑지 못했다. 오퍼가 어느 블로그의 것인지
정하는 자리가 없었기 때문이다.

Revision ID: 080
Revises: 079
"""
from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("cpa_offers")}
    if "blog_ids" in have:
        return
    op.add_column("cpa_offers", sa.Column("blog_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cpa_offers", "blog_ids")
