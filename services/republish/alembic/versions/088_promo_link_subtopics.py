"""홍보 링크에 하위 주제 연동

키워드를 손으로 적는 대신 카테고리의 하위 주제를 고르게 한다. 고른 주제는
그대로 두고(다시 펼칠 근거), 키워드는 저장할 때 펼쳐 keywords 에 넣는다.

Revision ID: 088
Revises: 087
"""
from alembic import op
import sqlalchemy as sa

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """promo_links 에 칸 하나. 고른 하위 주제 id 목록을 쉼표로 적는다."""
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("promo_links")]
    if "subtopic_ids" in cols:
        return
    op.add_column("promo_links",
                  sa.Column("subtopic_ids", sa.String(300), nullable=True))


def downgrade() -> None:
    """되돌리기."""
    op.drop_column("promo_links", "subtopic_ids")
