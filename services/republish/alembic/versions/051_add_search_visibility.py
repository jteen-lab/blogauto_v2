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

주의:
    앱 시작 시 SQLAlchemy create_all 이 테이블을 먼저 만들 수 있다. 그 경우
    upgrade 는 DuplicateTable 로 실패하므로 `alembic stamp 051` 로 버전만 정렬한다.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
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

    op.add_column(
        "blogs", sa.Column("search_index_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
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
