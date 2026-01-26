"""Add crawled_posts table and blog crawl status fields

Revision ID: 013
Revises: 012
Create Date: 2025-01-26

유사도 매칭 워크플로우를 위한 크롤링 포스트 테이블 추가
- CrawledPost: 블로그에서 크롤링한 포스트 또는 발행 후 생성된 포스트
- Blog 모델에 크롤링/매칭 상태 필드 추가
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. crawled_posts 테이블 생성
    op.create_table(
        'crawled_posts',
        # 기본 키
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        # 블로그 연결
        sa.Column('blog_id', sa.Integer(), sa.ForeignKey('blogs.id', ondelete='CASCADE'), nullable=False, index=True),
        # 포스트 정보
        sa.Column('title', sa.String(500), nullable=False, index=True, comment='포스트 제목'),
        sa.Column('url', sa.String(1000), nullable=True, comment='포스트 URL'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, comment='발행 일시'),
        # 매칭 정보
        sa.Column('match_status', sa.String(20), default='pending', nullable=False, index=True,
                  comment='매칭 상태: pending | matched | unmatched'),
        sa.Column('matched_main_title_id', sa.Integer(),
                  sa.ForeignKey('main_titles.id', ondelete='SET NULL'), nullable=True, index=True,
                  comment='매칭된 메인 타이틀 ID'),
        sa.Column('match_score', sa.Float(), nullable=True, comment='유사도 점수 (0.0 ~ 100.0)'),
        # 소스 정보
        sa.Column('source', sa.String(20), default='crawled', nullable=False,
                  comment='소스: crawled | published'),
        # 타임스탬프
        sa.Column('crawled_at', sa.DateTime(timezone=True), server_default=sa.func.now(), comment='크롤링 일시'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 복합 인덱스 생성
    op.create_index('ix_crawled_post_blog_status', 'crawled_posts', ['blog_id', 'match_status'])
    op.create_index('ix_crawled_post_blog_title', 'crawled_posts', ['blog_id', 'title'])

    # 2. blogs 테이블에 크롤링/매칭 상태 필드 추가
    op.add_column('blogs', sa.Column('is_new_blog', sa.Boolean(), nullable=False, server_default='true',
                                     comment='신규 블로그 여부 (포스트 없음)'))
    op.add_column('blogs', sa.Column('crawl_status', sa.String(20), nullable=False, server_default='never',
                                     comment='크롤링 상태: never | crawling | matching | synced | error'))
    op.add_column('blogs', sa.Column('last_crawled_at', sa.DateTime(timezone=True), nullable=True,
                                     comment='마지막 크롤링 시간'))
    op.add_column('blogs', sa.Column('last_matched_at', sa.DateTime(timezone=True), nullable=True,
                                     comment='마지막 매칭 완료 시간'))
    op.add_column('blogs', sa.Column('crawled_count', sa.Integer(), nullable=False, server_default='0',
                                     comment='크롤링된 포스트 수'))
    op.add_column('blogs', sa.Column('matched_count', sa.Integer(), nullable=False, server_default='0',
                                     comment='매칭된 포스트 수'))


def downgrade() -> None:
    # blogs 테이블에서 필드 제거
    op.drop_column('blogs', 'matched_count')
    op.drop_column('blogs', 'crawled_count')
    op.drop_column('blogs', 'last_matched_at')
    op.drop_column('blogs', 'last_crawled_at')
    op.drop_column('blogs', 'crawl_status')
    op.drop_column('blogs', 'is_new_blog')

    # crawled_posts 테이블 삭제
    op.drop_index('ix_crawled_post_blog_title', table_name='crawled_posts')
    op.drop_index('ix_crawled_post_blog_status', table_name='crawled_posts')
    op.drop_table('crawled_posts')
