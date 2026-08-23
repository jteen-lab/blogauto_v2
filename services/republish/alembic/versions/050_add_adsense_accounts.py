"""애드센스 계정·사이트 상태 테이블 추가 (다중 계정)

Revision ID: 050
Revises: 049
Create Date: 2026-08-23

목적:
    - 블로그의 승인 여부를 blogauto 내부 설정이 아니라 **애드센스 사이트 목록의
      실제 상태**로 판정하기 위함.
    - 애드센스 계정을 여러 개 등록할 수 있어야 하므로 계정 테이블 + 사이트 캐시.

변경 사항:
    1. adsense_accounts 테이블 신설(계정별 refresh token 암호화 보관).
    2. adsense_sites 테이블 신설(계정별 사이트 도메인·state 캐시).

주의:
    앱 시작 시 SQLAlchemy create_all 이 이 테이블들을 먼저 만들 수 있다.
    그 경우 upgrade 는 DuplicateTable 로 실패하므로 `alembic stamp 050` 으로
    버전만 정렬한다(구조는 동일 모델 기반이라 이미 정확하다).
"""
import sqlalchemy as sa
from alembic import op


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adsense_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("google_email", sa.String(length=255), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("account_resource", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_adsense_accounts_user_id", "adsense_accounts", ["user_id"])

    op.create_table(
        "adsense_sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=True),
        sa.Column("site_resource", sa.String(length=200), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["adsense_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "domain", name="uq_adsense_site_domain"),
    )
    op.create_index("ix_adsense_sites_account_id", "adsense_sites", ["account_id"])
    op.create_index("ix_adsense_sites_domain", "adsense_sites", ["domain"])


def downgrade() -> None:
    op.drop_table("adsense_sites")
    op.drop_table("adsense_accounts")
