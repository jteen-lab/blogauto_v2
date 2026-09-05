"""유입 분석 — 블로그별 GA4 속성 + 글별 일일 성과

Revision ID: 075
Revises: 074

두 가지를 넣는다.

    blogs.analytics_config   블로그별 GA4 속성 번호(속성이 블로그마다 따로다)
    post_metrics_daily       글 하나의 하루치 세션·노출·순위

`create_all` 로 만든 테이블에는 server_default 가 없다. NOT NULL 컬럼은
여기에 명시적으로 적어야 기존 행이 있는 환경에서도 통과한다.

계획서: docs/plans/analytics_integration_plan.md
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {
        c["name"] for c in sa.inspect(bind).get_columns(table)
    }


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_column("blogs", "analytics_config"):
        op.add_column(
            "blogs",
            sa.Column("analytics_config", sa.JSON(), nullable=True,
                      comment="GA4 연결 {property_id, display_name}"),
        )

    if _has_table("post_metrics_daily"):
        return

    bind = op.get_bind()
    # JSON 이 아닌 실수형은 방언에 따라 이름이 다르다
    float_type = (postgresql.DOUBLE_PRECISION()
                  if bind.dialect.name == "postgresql" else sa.Float())

    op.create_table(
        "post_metrics_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url_id", sa.Integer(), nullable=False),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("engaged_sessions", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("avg_duration", float_type, nullable=False,
                  server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("position", float_type, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["url_id"], ["search_visibility_urls.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("url_id", "date",
                            name="uq_post_metric_url_date"),
    )
    op.create_index("ix_post_metrics_daily_url_id", "post_metrics_daily",
                    ["url_id"])
    op.create_index("ix_post_metrics_daily_blog_id", "post_metrics_daily",
                    ["blog_id"])
    op.create_index("ix_post_metric_date", "post_metrics_daily", ["date"])
    op.create_index("ix_post_metric_blog_date", "post_metrics_daily",
                    ["blog_id", "date"])


def downgrade() -> None:
    # 수집한 지표는 되돌릴 수 없다. 테이블만 지운다.
    if _has_table("post_metrics_daily"):
        op.drop_table("post_metrics_daily")
    if _has_column("blogs", "analytics_config"):
        op.drop_column("blogs", "analytics_config")
