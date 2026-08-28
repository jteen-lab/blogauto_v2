"""검색 노출 원장에 네이버 색인 상태 추가

Revision ID: 053
Revises: 052
Create Date: 2026-08-28

목적:
    구글은 GSC URL Inspection 으로 색인 여부를 재고 있으나 네이버는 측정 수단이
    없었다. 네이버 웹문서 검색 API 로 발행 URL 이 검색에 나타나는지 확인해
    "네이버가 수집을 안 한다" 를 숫자로 만든다.

주의:
    검색 결과에 없다고 미색인이 확정되는 것은 아니다(제목이 일반적이거나 순위가
    낮으면 안 잡힌다). 그래서 상태 이름을 found/not_found 로 둔다.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None

TABLE = "search_visibility_urls"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column(TABLE, "naver_index_state"):
        op.add_column(
            TABLE,
            sa.Column(
                "naver_index_state", sa.String(length=20),
                nullable=False, server_default="unknown",
            ),
        )
        op.create_index(
            "ix_svu_blog_naver", TABLE, ["blog_id", "naver_index_state"],
        )
    if not _has_column(TABLE, "naver_checked_at"):
        op.add_column(
            TABLE, sa.Column("naver_checked_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column(TABLE, "naver_detail"):
        op.add_column(TABLE, sa.Column("naver_detail", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    if _has_column(TABLE, "naver_detail"):
        op.drop_column(TABLE, "naver_detail")
    if _has_column(TABLE, "naver_checked_at"):
        op.drop_column(TABLE, "naver_checked_at")
    if _has_column(TABLE, "naver_index_state"):
        op.drop_index("ix_svu_blog_naver", table_name=TABLE)
        op.drop_column(TABLE, "naver_index_state")
