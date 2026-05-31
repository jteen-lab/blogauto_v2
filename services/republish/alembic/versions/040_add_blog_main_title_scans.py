"""Add blog_main_title_scans table for blog x main_title 검토 카드

Revision ID: 040
Create Date: 2026-05-31

목적 (사용자 디벨롭 B):
    정식제목과 블로그 사이의 "검토 카드"를 영구 보관한다.
    카드가 있으면 = 이미 검토됨 (matched=True: 매칭, matched=False: 미매칭).
    카드가 없으면 = 미검토 (= 그룹3).

    이전 구조의 한계: match_status 가 CrawledPost(글 카드) 에만 있어서,
    블로그 선택 시 매번 N개 후보 정식제목과 V3 텍스트 매칭을 반복함.
    이번 구조: (blog_id, main_title_id) 쌍 단위로 검토 결과를 기록하여,
    같은 쌍은 두 번 비교하지 않도록 한다.

    사전체크 쿼리에서 "이 블로그 카테고리 정식제목 중 카드 없는 것이 있나?"
    질문 1회로 매칭 필요 여부를 결정할 수 있다.
"""
from alembic import op
import sqlalchemy as sa


revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """blog_main_title_scans 테이블 생성 + 인덱스."""
    op.create_table(
        'blog_main_title_scans',
        sa.Column('blog_id', sa.Integer(), nullable=False),
        sa.Column('main_title_id', sa.Integer(), nullable=False),
        sa.Column('matched', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('scanned_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['blog_id'], ['blogs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['main_title_id'], ['main_titles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('blog_id', 'main_title_id'),
    )
    # 사전체크 "이 블로그의 검토 카드 빠르게 셈" 용
    op.create_index(
        'ix_bmts_blog_matched',
        'blog_main_title_scans',
        ['blog_id', 'matched'],
    )
    # 정식제목 수정 시 그 main_title_id 의 모든 카드 일괄 삭제 용
    op.create_index(
        'ix_bmts_main_title',
        'blog_main_title_scans',
        ['main_title_id'],
    )


def downgrade() -> None:
    """blog_main_title_scans 테이블 제거."""
    op.drop_index('ix_bmts_main_title', table_name='blog_main_title_scans')
    op.drop_index('ix_bmts_blog_matched', table_name='blog_main_title_scans')
    op.drop_table('blog_main_title_scans')
