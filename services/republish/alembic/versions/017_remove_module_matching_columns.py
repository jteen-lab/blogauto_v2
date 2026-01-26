"""remove module matching columns

Revision ID: 017
Revises: 016
Create Date: 2025-01-26

모듈에서 매칭 설정 컬럼 제거 (블로그 레벨로 이동됨)
- allow_duplicate_similar_posts
- matching_threshold
- use_waiting_category
- waiting_threshold_min
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # modules 테이블에서 매칭 설정 컬럼 제거
    op.drop_column('modules', 'allow_duplicate_similar_posts')
    op.drop_column('modules', 'matching_threshold')
    op.drop_column('modules', 'use_waiting_category')
    op.drop_column('modules', 'waiting_threshold_min')


def downgrade() -> None:
    # 컬럼 복원 (롤백용)
    op.add_column(
        'modules',
        sa.Column(
            'waiting_threshold_min',
            sa.Integer(),
            nullable=False,
            server_default='50',
            comment='대기 분류 최소 임계값(%)'
        )
    )
    op.add_column(
        'modules',
        sa.Column(
            'use_waiting_category',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='대기 분류 사용 여부'
        )
    )
    op.add_column(
        'modules',
        sa.Column(
            'matching_threshold',
            sa.Integer(),
            nullable=False,
            server_default='65',
            comment='유사도 매칭 임계값(%)'
        )
    )
    op.add_column(
        'modules',
        sa.Column(
            'allow_duplicate_similar_posts',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='유사 포스트 중복 발행 허용'
        )
    )
