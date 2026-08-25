"""검색 노출 원장 테이블 + 블로그 설정 컬럼 추가

Revision ID: 051
Revises: 050
Create Date: 2026-08-25

목적:
    검색 노출 3종(S1 IndexNow 제출, S2 사이트맵 신선도, S6 색인 점검)의 결과를
    발행 URL 단위로 한 행에 누적한다. 계획서 search_visibility_plan.md §4.1.

변경 사항:
    1. search_visibility_urls 테이블 신설.
    2. blogs.search_index_config JSON 컬럼 추가(기본 NULL → 서비스에서 기본값 병합).

주의(중요):
    앱 시작 시 SQLAlchemy create_all 이 **테이블은** 먼저 만들 수 있다. 하지만
    create_all 은 기존 테이블에 **컬럼을 추가하지 않는다** — blogs.search_index_config
    는 이 마이그레이션이 반드시 실행돼야 생긴다.
    그래서 upgrade 를 멱등하게 작성한다(있으면 건너뛴다). stamp 로 넘기면 컬럼이
    누락돼 블로그 조회가 전부 실패한다.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    """대상 테이블이 이미 있는지 확인한다(create_all 선행 대비)."""
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    """대상 컬럼이 이미 있는지 확인한다."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if _has_table("search_visibility_urls"):
        # create_all 이 이미 만든 경우 — 인덱스까지 동일 모델 기반이라 건너뛴다.
        _add_blog_column()
        return

    op.create_table(
        "search_visibility_urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("crawled_post_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        # S1
        sa.Column(
            "indexnow_status", sa.String(length=20),
            nullable=False, server_default="pending",
        ),
        sa.Column("indexnow_status_code", sa.Integer(), nullable=True),
        sa.Column("indexnow_error", sa.Text(), nullable=True),
        sa.Column(
            "indexnow_attempts", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("indexnow_submitted_at", sa.DateTime(), nullable=True),
        # S2
        sa.Column(
            "sitemap_state", sa.String(length=20),
            nullable=False, server_default="unknown",
        ),
        sa.Column("sitemap_checked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "sitemap_miss_streak", sa.Integer(), nullable=False, server_default="0",
        ),
        # S6
        sa.Column(
            "index_state", sa.String(length=20),
            nullable=False, server_default="unknown",
        ),
        sa.Column("index_checked_at", sa.DateTime(), nullable=True),
        sa.Column("index_detail", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["crawled_post_id"], ["crawled_posts.id"], ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blog_id", "url", name="uq_svu_blog_url"),
    )
    op.create_index(
        "ix_search_visibility_urls_blog_id", "search_visibility_urls", ["blog_id"],
    )
    op.create_index(
        "ix_search_visibility_urls_crawled_post_id",
        "search_visibility_urls", ["crawled_post_id"],
    )
    op.create_index(
        "ix_search_visibility_urls_published_at",
        "search_visibility_urls", ["published_at"],
    )
    op.create_index(
        "ix_svu_blog_indexnow", "search_visibility_urls",
        ["blog_id", "indexnow_status"],
    )
    op.create_index(
        "ix_svu_blog_index_state", "search_visibility_urls",
        ["blog_id", "index_state"],
    )
    op.create_index(
        "ix_svu_blog_sitemap", "search_visibility_urls",
        ["blog_id", "sitemap_state"],
    )

    _add_blog_column()


def _add_blog_column() -> None:
    """blogs.search_index_config 를 없을 때만 추가한다."""
    if _has_column("blogs", "search_index_config"):
        return
    op.add_column(
        "blogs", sa.Column("search_index_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    if _has_column("blogs", "search_index_config"):
        op.drop_column("blogs", "search_index_config")
    op.drop_index("ix_svu_blog_sitemap", table_name="search_visibility_urls")
    op.drop_index("ix_svu_blog_index_state", table_name="search_visibility_urls")
    op.drop_index("ix_svu_blog_indexnow", table_name="search_visibility_urls")
    op.drop_index(
        "ix_search_visibility_urls_published_at", table_name="search_visibility_urls",
    )
    op.drop_index(
        "ix_search_visibility_urls_crawled_post_id",
        table_name="search_visibility_urls",
    )
    op.drop_index(
        "ix_search_visibility_urls_blog_id", table_name="search_visibility_urls",
    )
    op.drop_table("search_visibility_urls")
