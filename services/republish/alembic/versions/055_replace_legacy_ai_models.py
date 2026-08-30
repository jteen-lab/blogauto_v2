"""옛 ai_models 테이블을 보존하고 카탈로그용으로 새로 만든다

Revision ID: 055
Revises: 054
Create Date: 2026-08-30

배경:
    DB 에 마이그레이션 이력이 없는 ai_models 테이블이 남아 있었다(create_all
    로 만들어진 뒤 모델 클래스가 사라진 것으로 보인다). 컬럼 구성이 달라
    (capabilities/pricing/status …) 새 카탈로그 코드와 맞지 않는다.

    054 는 테이블 '이름' 만 보고 존재하면 건너뛰었기 때문에 옛 테이블이
    그대로 남아 조회가 UndefinedColumnError 로 실패했다. 이름이 같아도
    구조가 다를 수 있다는 것을 054 가 놓쳤다.

처리:
    옛 테이블은 지우지 않고 ai_models_legacy 로 옮긴다. 쓰는 코드가 없고
    데이터도 낡았지만(claude-3, gemini-1.5 등 이미 사라진 모델 20건),
    사용자가 수동 입력한 값(source='manual')이라 함부로 버리지 않는다.
"""
import sqlalchemy as sa
from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None

TABLE = "ai_models"
LEGACY = "ai_models_legacy"
# 새 구조에만 있는 컬럼 — 이것으로 옛 테이블인지 가른다
MARKER_COLUMN = "capability"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _create_catalog_table() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("capability", sa.String(length=20),
                  server_default="text", nullable=False),
        sa.Column("is_available", sa.Boolean(),
                  server_default=sa.true(), nullable=False),
        sa.Column("shutdown_date", sa.String(length=40), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_id", name="uq_ai_model"),
    )
    op.create_index("ix_ai_models_id", TABLE, ["id"])
    op.create_index("ix_ai_models_provider", TABLE, ["provider"])
    op.create_index("ix_ai_models_is_available", TABLE, ["is_available"])
    op.create_index("ix_ai_models_provider_cap", TABLE,
                    ["provider", "capability"])


def upgrade() -> None:
    if _has_column(TABLE, MARKER_COLUMN):
        return  # 이미 새 구조

    if _has_table(TABLE):
        if _has_table(LEGACY):
            op.drop_table(LEGACY)
        op.rename_table(TABLE, LEGACY)
        # 인덱스는 테이블을 따라오지만 '이름' 은 그대로라 새 테이블과
        # 부딪힌다. 지우지 않고 이름만 바꾼다 — UNIQUE 제약이 뒤에 붙은
        # 인덱스는 DROP INDEX 로 지울 수 없다(제약을 지워야 한다).
        bind = op.get_bind()
        rows = bind.execute(sa.text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = :t AND schemaname = current_schema()"
        ), {"t": LEGACY}).scalars().all()
        for name in rows:
            if name.endswith("_legacy"):
                continue
            bind.execute(sa.text(
                f'ALTER INDEX "{name}" RENAME TO "{name}_legacy"'
            ))

    _create_catalog_table()


def downgrade() -> None:
    if _has_column(TABLE, MARKER_COLUMN):
        op.drop_table(TABLE)
    if _has_table(LEGACY):
        op.rename_table(LEGACY, TABLE)
