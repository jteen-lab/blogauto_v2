"""애드센스 승인 지원 Sprint 1(P1): 필수 페이지/저자성 필드 추가

Revision ID: 046
Revises: 045
Create Date: 2026-08-06

목적 (docs/plans/adsense_approval_features_plan.md Phase 1, F1~F2):
    - Blog.required_pages_status: 개인정보처리방침/이용약관/소개/문의 4종
      필수 페이지 발행 상태(none|partial|complete).
    - Blog.required_page_ids: 플랫폼별 생성된 페이지 ID
      ({privacy, terms, about, contact} → platform page id).
    - Blog.author_profile: 저자성(E-E-A-T) 신호용 저자 프로필
      (name/bio/expertise). F2(바이라인 주입)는 이번 마이그레이션 범위 밖,
      필드만 선반영.

변경 사항:
    1. blogs.required_pages_status 추가 (String(20), NOT NULL, 기본 'none')
    2. blogs.required_page_ids 추가 (JSON, nullable)
    3. blogs.author_profile 추가 (JSON, nullable)

데이터 보존:
    - 기존 row는 required_pages_status='none'(미생성)으로 채워짐.
    - required_page_ids/author_profile은 NULL(미설정)로 채워짐 — 기존 동작 무영향.
"""
import sqlalchemy as sa
from alembic import op


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """필수 페이지 상태/ID + 저자 프로필 컬럼 추가 (데이터 보존)."""
    op.add_column(
        "blogs",
        sa.Column(
            "required_pages_status",
            sa.String(20),
            nullable=False,
            server_default="none",
            comment="필수 페이지(개인정보처리방침/이용약관/소개/문의) 발행 상태: none|partial|complete",
        ),
    )
    op.add_column(
        "blogs",
        sa.Column(
            "required_page_ids",
            sa.JSON(),
            nullable=True,
            comment="플랫폼별 생성된 필수 페이지 ID: {privacy, terms, about, contact}",
        ),
    )
    op.add_column(
        "blogs",
        sa.Column(
            "author_profile",
            sa.JSON(),
            nullable=True,
            comment="저자성(E-E-A-T) 신호용 저자 프로필: name/bio/expertise",
        ),
    )


def downgrade() -> None:
    """추가한 컬럼 제거."""
    op.drop_column("blogs", "author_profile")
    op.drop_column("blogs", "required_page_ids")
    op.drop_column("blogs", "required_pages_status")
