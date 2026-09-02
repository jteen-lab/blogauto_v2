"""분류 시도 기록 — 같은 키워드를 반복해서 훑지 않게

Revision ID: 064
Revises: 063

문제:
    분류 버튼이 "미분류 상위 N건" 을 매번 다시 집었다. 분류기는 결정적이라
    같은 입력에 같은 결과를 낸다 — 안 붙은 것은 몇 번을 눌러도 안 붙는다.
    그래서 눌러도 "훑음 2000건" 만 반복되고 진행이 없었다.

    시도한 시각을 남겨 **아직 안 훑은 것부터** 가져간다. 다 훑으면 그 사실을
    화면에 말해 준다("분류표에 없는 말입니다").

    분류표를 보강한 뒤에는 다시 훑어야 하므로 기록을 지우는 길도 둔다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-1
"""
import sqlalchemy as sa
from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None

TABLE = "keyword_candidates"
COLUMN = "classify_tried_at"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(TABLE, sa.Column(
            COLUMN, sa.DateTime(timezone=True), nullable=True,
            comment="분류를 시도한 시각(분류표에 없어 실패한 것도 기록)"))
        op.create_index(f"ix_{TABLE}_{COLUMN}", TABLE, [COLUMN])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    if f"ix_{TABLE}_{COLUMN}" in indexes:
        op.drop_index(f"ix_{TABLE}_{COLUMN}", table_name=TABLE)
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)
