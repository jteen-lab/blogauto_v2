"""검색 노출 원장의 시각 컬럼을 timezone-aware 로 변경

Revision ID: 052
Revises: 051
Create Date: 2026-08-28

문제:
    crawled_posts.published_at 은 timestamptz 인데 search_visibility_urls 는
    timestamp(naive)로 만들었다. 백필이 aware 값을 그대로 넣으려다
    asyncpg DataError("can't subtract offset-naive and offset-aware datetimes")
    로 전량 실패했다. 기간 비교(유예 시간)도 어긋난다.

변경:
    시각 컬럼 6개를 timestamptz 로 변경한다.
    기존 값은 naive KST 로 기록돼 있고 DB TimeZone 이 Asia/Seoul 이므로
    USING 없이도 세션 시간대 기준으로 올바르게 해석된다.
"""
import sqlalchemy as sa
from alembic import op


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None

TABLE = "search_visibility_urls"
COLUMNS = (
    "published_at",
    "indexnow_submitted_at",
    "sitemap_checked_at",
    "index_checked_at",
    "created_at",
    "updated_at",
)


def _dialect() -> str:
    return op.get_bind().dialect.name


def upgrade() -> None:
    if _dialect() != "postgresql":
        # SQLite 등은 타입 구분이 없어 변경할 것이 없다(테스트 경로).
        return
    for column in COLUMNS:
        op.alter_column(
            TABLE, column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=column not in ("created_at", "updated_at"),
        )


def downgrade() -> None:
    if _dialect() != "postgresql":
        return
    for column in COLUMNS:
        op.alter_column(
            TABLE, column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=column not in ("created_at", "updated_at"),
        )
