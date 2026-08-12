"""애드센스 승인 지원 Sprint 2(P2): 니치 강제 필드 추가 (F4)

Revision ID: 048
Revises: 047
Create Date: 2026-08-12

목적 (docs/plans/adsense_approval_features_plan.md Phase 2, F4):
    - Blog.niche_topic_ids: 애드센스 준비 블로그를 단일 니치 topic으로 제한하는
      허용 topic_id 목록(JSON). adsense_status='preparing'인 블로그의 인벤토리
      선택 시 이 topic 밖 제목을 차단(opt-in). NULL/빈 값이면 니치 강제 비활성.

변경 사항:
    1. blogs.niche_topic_ids 추가 (JSON, nullable)

데이터 보존:
    - 기존 row는 NULL(니치 강제 비활성)로 채워짐 — 기존 동작 무영향.
"""
import sqlalchemy as sa
from alembic import op


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """니치 강제 topic 목록 컬럼 추가 (데이터 보존)."""
    op.add_column(
        "blogs",
        sa.Column(
            "niche_topic_ids",
            sa.JSON(),
            nullable=True,
            comment="F4 니치 강제: 허용 topic_id 목록. preparing 상태에서만 차단 적용",
        ),
    )


def downgrade() -> None:
    """추가한 컬럼 제거."""
    op.drop_column("blogs", "niche_topic_ids")
