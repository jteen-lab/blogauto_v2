"""Add collected_urls table for bulk collection

Revision ID: 012
Revises: 011
Create Date: 2025-01-19

대량 수집 2단계 방식을 위한 URL 저장 테이블 추가
- Phase 1: 키워드 검색 → URL 수집 및 저장
- Phase 2: 저장된 URL에서 제목 수집 (1~3개씩)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # collected_urls 테이블 생성
    op.create_table(
        'collected_urls',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        # URL 정보
        sa.Column('url', sa.String(500), nullable=False, index=True, comment='블로그/사이트 URL'),
        sa.Column('domain', sa.String(200), nullable=False, index=True, comment='도메인'),
        sa.Column('platform', sa.String(50), nullable=False, default='unknown', comment='플랫폼'),
        # 검색 정보
        sa.Column('search_keyword', sa.String(200), nullable=True, comment='검색에 사용된 키워드'),
        sa.Column('search_title', sa.String(500), nullable=True, comment='검색 결과 제목'),
        # 처리 상태
        sa.Column('is_processed', sa.Boolean(), default=False, index=True, comment='제목 수집 완료 여부'),
        sa.Column('process_count', sa.Integer(), default=0, comment='처리 횟수'),
        sa.Column('last_processed_at', sa.DateTime(timezone=True), nullable=True, comment='마지막 제목 수집 시각'),
        sa.Column('titles_collected', sa.Integer(), default=0, comment='수집된 제목 수'),
        # 상태 관리
        sa.Column('is_active', sa.Boolean(), default=True, index=True, comment='활성 상태'),
        sa.Column('error_count', sa.Integer(), default=0, comment='수집 실패 횟수'),
        sa.Column('last_error', sa.Text(), nullable=True, comment='마지막 에러 메시지'),
        # 타임스탬프
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), comment='최초 수집 시각'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        # 유니크 제약조건
        sa.UniqueConstraint('domain', name='uq_collected_url_domain')
    )

    # 인덱스 생성 (복합 조건 조회 최적화)
    op.create_index(
        'ix_collected_urls_pending',
        'collected_urls',
        ['is_processed', 'is_active', 'created_at'],
        postgresql_where=sa.text('is_processed = false AND is_active = true')
    )


def downgrade() -> None:
    op.drop_index('ix_collected_urls_pending', table_name='collected_urls')
    op.drop_table('collected_urls')
