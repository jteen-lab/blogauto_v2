"""생성 이력에 제목 스타일 기록

Revision ID: 070
Revises: 069

배경:
    `generator.py` 가 `random.choice(styles)` 로 스타일을 고르는데 **어떤
    스타일을 썼는지 남기지 않았다.** 5개를 굴리면서 무엇이 먹히는지
    영원히 알 수 없는 상태였다.

    기록해 두면 GSC 실측과 대조해 성과 좋은 스타일에 가중치를 줄 수 있다.

계획서: docs/plans/title_tab_workplan.md §4-5 A
"""
import sqlalchemy as sa
from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None

TABLE = "generation_histories"
COLUMN = "title_style"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    if COLUMN not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=30),
                                       nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    if COLUMN in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.drop_column(TABLE, COLUMN)
