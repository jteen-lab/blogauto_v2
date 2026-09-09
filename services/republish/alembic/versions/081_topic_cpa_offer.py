"""주제(니치)에 CPA 오퍼 귀속

구분 축을 니치로 잡는다. 키워드·임시제목·정식제목이 이미 topic_id 를
들고 있어 컬럼을 더 만들지 않아도 된다.

Revision ID: 081
Revises: 080
"""
from alembic import op
import sqlalchemy as sa

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("topics")}
    if "cpa_offer_id" in have:
        return
    op.add_column("topics",
                  sa.Column("cpa_offer_id", sa.Integer(), nullable=True))
    op.create_index("ix_topics_cpa_offer_id", "topics", ["cpa_offer_id"])


def downgrade() -> None:
    op.drop_index("ix_topics_cpa_offer_id", table_name="topics")
    op.drop_column("topics", "cpa_offer_id")
