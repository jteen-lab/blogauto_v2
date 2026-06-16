"""P1: 재발행 리뉴얼 기반 컬럼 추가

Revision ID: 044
Revises: 043
Create Date: 2026-06-16

목적 (재발행 리뉴얼 P1):
    - blogs.renewal_config: 리뉴얼 정책(블로그 기본 주기 + 카테고리별 주기 +
      제목 모드 + 본문/이미지 삭제 유예) 저장용 JSON.
    - crawled_posts.last_renewed_at: 마지막 리뉴얼 시각(주기 도래 판정 기준).

변경 사항:
    1. blogs.renewal_config 추가 (JSON, nullable)
    2. crawled_posts.last_renewed_at 추가 (TIMESTAMP tz, nullable)

데이터 보존:
    - 두 컬럼 모두 nullable → 기존 row 는 NULL 로 자동 채워짐(데이터 영향 없음).
"""
import sqlalchemy as sa
from alembic import op


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """리뉴얼 기반 컬럼 2개 추가 (둘 다 nullable, 데이터 보존)."""
    op.add_column(
        "blogs",
        sa.Column(
            "renewal_config",
            sa.JSON(),
            nullable=True,
            comment="재발행 리뉴얼 설정: default_period_months, title_mode, "
                    "delete_grace_days, category_periods",
        ),
    )
    op.add_column(
        "crawled_posts",
        sa.Column(
            "last_renewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="마지막 리뉴얼 시각(NULL=미리뉴얼)",
        ),
    )


def downgrade() -> None:
    """추가한 컬럼 제거."""
    op.drop_column("crawled_posts", "last_renewed_at")
    op.drop_column("blogs", "renewal_config")
