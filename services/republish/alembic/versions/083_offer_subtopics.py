"""오퍼가 하위주제를 참조한다

니치를 오퍼에 배타적으로 귀속시키면 그 니치를 쓰던 블로그가 전부 CPA 로
넘어간다(실측: '생활 정보' 제목 879건·블로그 7개). 소유가 아니라 참조로
바꾸고, 단위를 주제에서 하위주제로 좁힌다(879 대 1).

Revision ID: 083
Revises: 082
"""
from alembic import op
import sqlalchemy as sa

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    have = {c["name"] for c in sa.inspect(bind).get_columns("cpa_offers")}
    if "subtopic_ids" not in have:
        op.add_column("cpa_offers",
                      sa.Column("subtopic_ids", sa.JSON(), nullable=True))

    # 배타 귀속 컬럼을 뺀다. 연결된 주제가 있으면 남겨 둔다 —
    # 데이터가 있는데 지우면 되돌릴 수 없다.
    topics = {c["name"] for c in sa.inspect(bind).get_columns("topics")}
    if "cpa_offer_id" not in topics:
        return
    used = bind.execute(sa.text(
        "SELECT COUNT(*) FROM topics WHERE cpa_offer_id IS NOT NULL")).scalar()
    if used:
        return
    try:
        op.drop_index("ix_topics_cpa_offer_id", table_name="topics")
    except Exception:  # noqa: BLE001 — 인덱스가 없을 수도 있다
        pass
    op.drop_column("topics", "cpa_offer_id")


def downgrade() -> None:
    op.add_column("topics", sa.Column("cpa_offer_id", sa.Integer(),
                                      nullable=True))
    op.drop_column("cpa_offers", "subtopic_ids")
