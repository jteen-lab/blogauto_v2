"""근거 부족 보류 카운터

Revision ID: 077
Revises: 076

수치가 곧 사실인 주제(금융·보험·세금 등)에서 근거를 못 찾으면 글을
만들지 않고 제목을 재고에 남긴다. **삭제하지 않는다** — 지우면 우리가
놓친 잘못을 확인할 방법이 사라진다.

3회 보류된 제목만 검토 목록에 올려 사람이 판단한다.

순서도: docs/flowcharts/evidence_hold.md
"""
import sqlalchemy as sa
from alembic import op

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None

COLUMNS = (
    ("hold_count", sa.Integer(), False, "0"),
    ("last_held_at", sa.DateTime(timezone=True), True, None),
    ("hold_reason", sa.Text(), True, None),
)


def _existing() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("main_titles")}


def upgrade() -> None:
    have = _existing()
    for name, type_, nullable, default in COLUMNS:
        if name in have:
            continue
        # create_all 로 만든 테이블에는 server_default 가 없다. NOT NULL
        # 컬럼은 여기서 기본값을 줘야 기존 행이 있어도 통과한다.
        op.add_column(
            "main_titles",
            sa.Column(name, type_, nullable=nullable,
                      server_default=default),
        )
    if "hold_count" not in have:
        op.create_index("ix_main_titles_hold_count", "main_titles",
                        ["hold_count"])


def downgrade() -> None:
    have = _existing()
    if "hold_count" in have:
        op.drop_index("ix_main_titles_hold_count", table_name="main_titles")
    for name, *_ in COLUMNS:
        if name in have:
            op.drop_column("main_titles", name)
