"""분류표 변경 이력·스냅샷 테이블

Revision ID: 072
Revises: 071

배경:
    분류표(주제>하위주제>키워드)를 잘못 바꾸면 재고 전체의 분류가 틀어진다.
    대량 수정 도구는 **되돌릴 수 있어야만** 열 수 있다.

    plan → apply 2단계와 롤백을 위해 변경 전 스냅샷과 감사 정보를 남긴다.
    누가 바꿨는지(사람/에이전트/스크립트)도 함께 적는다.

계획서: docs/plans/title_tab_workplan.md §9-4
"""
import sqlalchemy as sa
from alembic import op

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None

TABLE = "taxonomy_changes"


def upgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # planned → applied → rolled_back
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="planned"),
        # 누가 요청했나: ui / agent / script
        sa.Column("actor", sa.String(length=30), nullable=False,
                  server_default="ui"),
        sa.Column("summary", sa.String(length=300), nullable=True),
        # 요청한 변경(JSON 문자열)
        sa.Column("payload", sa.Text(), nullable=False),
        # 적용 전 스냅샷(JSON 문자열) — 롤백의 근거
        sa.Column("snapshot", sa.Text(), nullable=True),
        # plan 단계에서 계산한 영향
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_{TABLE}_id", TABLE, ["id"])
    op.create_index(f"ix_{TABLE}_user_id", TABLE, ["user_id"])
    op.create_index(f"ix_{TABLE}_status", TABLE, ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        op.drop_table(TABLE)
