"""제목에 CPA 오퍼 귀속

CPA 제목이 일반 재고에 섞이면 애드센스 블로그가 그것을 뽑아 쓸 수 있다.
니치가 겹치는 순간(예: 금융) 규정 위반 글이 엉뚱한 블로그에 나간다.

Revision ID: 079
Revises: 078
"""
from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("main_titles")}
    if "cpa_offer_id" in have:
        return
    op.add_column("main_titles",
                  sa.Column("cpa_offer_id", sa.Integer(), nullable=True))
    op.create_index("ix_main_titles_cpa_offer_id", "main_titles",
                    ["cpa_offer_id"])


def downgrade() -> None:
    op.drop_index("ix_main_titles_cpa_offer_id", table_name="main_titles")
    op.drop_column("main_titles", "cpa_offer_id")
