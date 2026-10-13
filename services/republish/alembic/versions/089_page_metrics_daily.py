"""페이지별 일일 유입(유입 경로별) 테이블

블로그오토가 쓰지 않은 옛 글·첫 화면까지 포함해 방문 페이지를 전부 적고,
네이버/구글/직접/기타로 나눈다. `create_all` 이 먼저 만들었으면 건너뛴다.

Revision ID: 089
Revises: 088

순서도: docs/flowcharts/analytics_sources.md
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None

TABLE = "page_metrics_daily"


def _has_table(table: str) -> bool:
    """테이블이 이미 있는지(앱 시작 때 create_all 이 만들었을 수 있다)."""
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    """page_metrics_daily 를 만든다."""
    if _has_table(TABLE):
        return
    bind = op.get_bind()
    float_type = (postgresql.DOUBLE_PRECISION()
                  if bind.dialect.name == "postgresql" else sa.Float())

    def zero(name: str) -> sa.Column:
        return sa.Column(name, sa.Integer(), nullable=False, server_default="0")

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("crawled_post_id", sa.Integer(), nullable=True),
        sa.Column("is_autopost", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        zero("sessions"), zero("engaged_sessions"),
        sa.Column("avg_duration", float_type, nullable=False,
                  server_default="0"),
        zero("naver_sessions"), zero("google_sessions"),
        zero("direct_sessions"), zero("other_sessions"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crawled_post_id"], ["crawled_posts.id"],
                                ondelete="SET NULL"),
        sa.UniqueConstraint("blog_id", "path", "date",
                            name="uq_page_metric_blog_path_date"),
    )
    op.create_index("ix_page_metrics_daily_blog_id", TABLE, ["blog_id"])
    op.create_index("ix_page_metrics_daily_crawled_post_id", TABLE,
                    ["crawled_post_id"])
    op.create_index("ix_page_metric_blog_date", TABLE, ["blog_id", "date"])


def downgrade() -> None:
    """수집한 지표는 되돌릴 수 없다. 테이블만 지운다."""
    if _has_table(TABLE):
        op.drop_table(TABLE)
