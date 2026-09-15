"""홍보 링크에 키워드 조합

프롬프트 템플릿은 제목의 키워드로 저절로 갈리는데 링크는 사람이 고른
하나가 모든 글에 붙었다. 같은 규칙으로 링크도 갈리게 한다.

Revision ID: 087
Revises: 086
"""
from alembic import op
import sqlalchemy as sa

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """promo_links 에 칸 하나."""
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("promo_links")]
    if "keywords" in cols:
        return
    op.add_column("promo_links",
                  sa.Column("keywords", sa.String(500), nullable=True))


def downgrade() -> None:
    """되돌리기."""
    op.drop_column("promo_links", "keywords")
