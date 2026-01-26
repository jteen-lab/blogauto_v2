"""add blog matching config

Revision ID: 016
Revises: 015
Create Date: 2025-01-26

Phase 3: 블로그 유사도 매칭 설정 필드 추가
- matching_config: JSON 필드로 매칭 설정 저장
  - allow_duplicate_similar_posts: 유사 포스트 중복 발행 허용
  - matching_threshold: 유사도 매칭 임계값
  - use_waiting_category: 대기 분류 사용 여부
  - waiting_threshold_min: 대기 분류 최소 임계값
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # blogs 테이블에 matching_config JSON 컬럼 추가
    op.add_column(
        'blogs',
        sa.Column(
            'matching_config',
            JSON,
            nullable=True,
            server_default='{}',
            comment='유사도 매칭 설정: allow_duplicate_similar_posts, matching_threshold, use_waiting_category, waiting_threshold_min'
        )
    )


def downgrade() -> None:
    # 컬럼 제거
    op.drop_column('blogs', 'matching_config')
