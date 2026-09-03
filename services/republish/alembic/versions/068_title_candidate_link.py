"""제목 ↔ 정본 키워드 연결

Revision ID: 068
Revises: 067

배경:
    `temp_titles.source_keyword_id` 는 옛 `collected_keywords` 를 가리킨다.
    새 정본은 `keyword_candidates` 라 **연결이 끊겨 있다.**

    이 연결이 없으면 "이 제목은 어떤 채택 키워드로 찾았는가" 를 알 수 없고,
    확장 재조합(계획서 §4-6 ②)이 성립하지 않는다.

FK 를 걸지 않는 이유:
    후보는 정리·재판정으로 지워질 수 있는데, 그때 제목까지 잃거나 삭제가
    막히면 곤란하다. 값만 남기고 끊어진 참조는 무시한다.

계획서: docs/plans/title_tab_workplan.md §2-1
"""
import sqlalchemy as sa
from alembic import op

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None

TARGETS = ("temp_titles", "main_titles")
COLUMN = "candidate_id"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in TARGETS:
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        if COLUMN in existing:
            continue
        op.add_column(table, sa.Column(COLUMN, sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_{COLUMN}", table, [COLUMN])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in TARGETS:
        if not inspector.has_table(table):
            continue
        if COLUMN in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, COLUMN)
