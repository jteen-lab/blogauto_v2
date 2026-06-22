"""P4: 재발행 리뉴얼 저장 정리 컬럼 추가

Revision ID: 045
Revises: 044
Create Date: 2026-06-22

목적 (재발행 리뉴얼 P4):
    - crawled_posts.purged_at: 유예기간 경과 후 본문(content_html)+이미지 파일을
      삭제한 시각. 메타(제목/url/platform_post_id/날짜)는 항상 보존하며, 리뉴얼은
      라이브 글에서 fetch하므로 서버 저장본이 없어도 동작한다.

변경 사항:
    1. crawled_posts.purged_at 추가 (TIMESTAMP tz, nullable)

데이터 보존:
    - nullable → 기존 row 는 NULL(미정리)로 자동 채워짐(데이터 영향 없음).
"""
import sqlalchemy as sa
from alembic import op


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """저장 정리 시각 컬럼 추가 (nullable, 데이터 보존)."""
    op.add_column(
        "crawled_posts",
        sa.Column(
            "purged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="본문/이미지 정리 시각(NULL=미정리)",
        ),
    )


def downgrade() -> None:
    """추가한 컬럼 제거."""
    op.drop_column("crawled_posts", "purged_at")
