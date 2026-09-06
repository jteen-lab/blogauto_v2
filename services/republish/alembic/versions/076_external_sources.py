"""외부 자료원 등록표 — 1차 출처 API 를 데이터로 관리한다

Revision ID: 076
Revises: 075

니치마다 `if 금융: 금감원 호출` 을 코드에 박으면 API 가 늘 때마다 코드를
고쳐야 한다. 등록표를 두고 글 생성 때 제목·니치로 고른다.

순서도: docs/flowcharts/reference_accuracy.md
"""
import sqlalchemy as sa
from alembic import op

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has_table("external_sources"):
        return

    op.create_table(
        "external_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("auth_key_encrypted", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("match_topics", sa.JSON(), nullable=True),
        sa.Column("match_keywords", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("daily_limit", sa.Integer(), nullable=False,
                  server_default="1000"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_external_source_code"),
    )
    op.create_index("ix_external_sources_code", "external_sources", ["code"])


def downgrade() -> None:
    # 등록한 인증키는 되살릴 수 없다. 표만 지운다.
    if _has_table("external_sources"):
        op.drop_table("external_sources")
