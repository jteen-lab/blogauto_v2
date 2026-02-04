"""Add reference collection tables

Revision ID: 018
Revises: 017
Create Date: 2026-02-01

Phase R-1: 참조자료 수집 모듈을 위한 테이블 추가
- collected_references: 참조자료 수집 결과 (검색어별 수집 세션)
- crawl_logs: 개별 URL 크롤링 상세 로그
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. collected_references 테이블 생성
    op.create_table(
        'collected_references',
        # 기본 키
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        # 제목 연결 (선택적)
        sa.Column(
            'title_id',
            sa.Integer(),
            sa.ForeignKey('main_titles.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
            comment='연결된 메인 타이틀 ID'
        ),
        # 검색 정보
        sa.Column(
            'search_query',
            sa.String(500),
            nullable=False,
            index=True,
            comment='검색어'
        ),
        # 수집 통계
        sa.Column(
            'total_searched',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='검색 결과 수'
        ),
        sa.Column(
            'total_crawled',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='크롤링 성공 수'
        ),
        sa.Column(
            'total_failed',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='크롤링 실패 수'
        ),
        # 선택된 참조자료 (JSONB)
        sa.Column(
            'selected_references',
            JSONB,
            nullable=True,
            comment='선택된 참조자료 JSON'
        ),
        # 상태 관리
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='pending',
            index=True,
            comment='상태: pending | collecting | completed | failed'
        ),
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='실패 시 에러 메시지'
        ),
        # 타임스탬프
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment='생성 시간'
        ),
        sa.Column(
            'completed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='완료 시간'
        ),
    )

    # collected_references 복합 인덱스
    op.create_index(
        'ix_collected_ref_status_created',
        'collected_references',
        ['status', 'created_at']
    )
    op.create_index(
        'ix_collected_ref_title_status',
        'collected_references',
        ['title_id', 'status']
    )

    # 2. crawl_logs 테이블 생성
    op.create_table(
        'crawl_logs',
        # 기본 키
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        # 참조자료 연결
        sa.Column(
            'reference_id',
            sa.Integer(),
            sa.ForeignKey('collected_references.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='참조자료 수집 ID'
        ),
        # URL 정보
        sa.Column(
            'url',
            sa.String(2000),
            nullable=False,
            comment='크롤링 URL'
        ),
        sa.Column(
            'domain',
            sa.String(255),
            nullable=True,
            index=True,
            comment='도메인'
        ),
        # 크롤링 결과
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            index=True,
            comment='상태: success | failed | timeout | blocked | skipped'
        ),
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='에러 메시지'
        ),
        # 콘텐츠 정보
        sa.Column(
            'content_length',
            sa.Integer(),
            nullable=True,
            comment='크롤링된 콘텐츠 길이'
        ),
        sa.Column(
            'crawl_duration_ms',
            sa.Integer(),
            nullable=True,
            comment='크롤링 소요 시간(ms)'
        ),
        # 타임스탬프
        sa.Column(
            'crawled_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment='크롤링 시간'
        ),
    )

    # crawl_logs 복합 인덱스
    op.create_index(
        'ix_crawl_log_ref_status',
        'crawl_logs',
        ['reference_id', 'status']
    )
    op.create_index(
        'ix_crawl_log_domain',
        'crawl_logs',
        ['domain']
    )


def downgrade() -> None:
    # crawl_logs 테이블 삭제
    op.drop_index('ix_crawl_log_domain', table_name='crawl_logs')
    op.drop_index('ix_crawl_log_ref_status', table_name='crawl_logs')
    op.drop_table('crawl_logs')

    # collected_references 테이블 삭제
    op.drop_index('ix_collected_ref_title_status', table_name='collected_references')
    op.drop_index('ix_collected_ref_status_created', table_name='collected_references')
    op.drop_table('collected_references')
