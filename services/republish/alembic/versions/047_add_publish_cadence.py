"""애드센스 승인 지원 Sprint 2(P2): 발행 케이던스 필드 추가 (F5)

Revision ID: 047
Revises: 046
Create Date: 2026-08-11

목적 (docs/plans/adsense_approval_features_plan.md Phase 2, F5):
    - Blog.adsense_status: 애드센스 승인 상태(none|preparing|applied|approved).
      F9 준비도 감사·A/B 테스트 라벨링에도 재사용 가능한 범용 상태값.
    - Blog.publish_daily_cap: 승인 전 저속 모드 일일 발행 상한. NULL이면
      게이트 비활성(opt-in) — 기존 운영 블로그는 동작 변화 없음.

변경 사항:
    1. blogs.adsense_status 추가 (String(20), NOT NULL, 기본 'none')
    2. blogs.publish_daily_cap 추가 (Integer, nullable)

데이터 보존:
    - 기존 row는 adsense_status='none'(미설정)으로 채워짐.
    - publish_daily_cap은 NULL(게이트 비활성)로 채워짐 — 기존 동작 무영향.
"""
import sqlalchemy as sa
from alembic import op


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """애드센스 승인 상태/발행 상한 컬럼 추가 (데이터 보존)."""
    op.add_column(
        "blogs",
        sa.Column(
            "adsense_status",
            sa.String(20),
            nullable=False,
            server_default="none",
            comment="애드센스 승인 상태: none|preparing|applied|approved",
        ),
    )
    op.add_column(
        "blogs",
        sa.Column(
            "publish_daily_cap",
            sa.Integer(),
            nullable=True,
            comment="승인 전 저속 모드 일일 발행 상한 (NULL이면 게이트 비활성)",
        ),
    )


def downgrade() -> None:
    """추가한 컬럼 제거."""
    op.drop_column("blogs", "publish_daily_cap")
    op.drop_column("blogs", "adsense_status")
