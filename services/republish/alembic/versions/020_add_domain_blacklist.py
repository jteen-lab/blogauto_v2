"""Add domain blacklist table

Revision ID: 020
Revises: 019
Create Date: 2026-02-11

크롤링 실패 도메인 블랙리스트 테이블 추가
- 반복 실패 도메인 자동 등록/차단
- 참조자료 수집 시 블랙리스트 도메인 스킵
"""
from alembic import op
import sqlalchemy as sa


revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """domain_blacklist 테이블 생성"""
    op.create_table(
        'domain_blacklist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('domain', sa.String(255), nullable=False, unique=True),
        sa.Column('fail_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column(
            'last_failed_at', sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            'reason', sa.String(100), nullable=False,
            server_default='content_extraction_failed'
        ),
        sa.Column(
            'is_active', sa.Boolean(), nullable=False, server_default='true'
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
    )

    # 인덱스
    op.create_index('ix_domain_blacklist_domain', 'domain_blacklist', ['domain'])
    op.create_index(
        'ix_domain_blacklist_active',
        'domain_blacklist',
        ['is_active', 'fail_count']
    )


def downgrade() -> None:
    """domain_blacklist 테이블 삭제"""
    op.drop_index('ix_domain_blacklist_active', table_name='domain_blacklist')
    op.drop_index('ix_domain_blacklist_domain', table_name='domain_blacklist')
    op.drop_table('domain_blacklist')
