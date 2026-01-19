"""make seed_keyword_id nullable and add source column

Revision ID: 010
Revises: 009
Create Date: 2026-01-17

시드 키워드 없이 자동 수집을 지원하기 위해:
- seed_keyword_id를 nullable로 변경
- source 컬럼 추가 (수집 소스 구분)
- 유니크 제약조건 변경
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 기존 유니크 제약조건 삭제
    op.drop_constraint('uq_collected_keyword_seed', 'collected_keywords', type_='unique')

    # 2. seed_keyword_id를 nullable로 변경
    op.alter_column(
        'collected_keywords',
        'seed_keyword_id',
        existing_type=sa.Integer(),
        nullable=True
    )

    # 3. source 컬럼 추가
    op.add_column(
        'collected_keywords',
        sa.Column('source', sa.String(50), nullable=True, comment='수집 소스 (google_trends|naver_datalab|naver_ads)')
    )

    # 4. 새 유니크 제약조건 추가
    op.create_unique_constraint(
        'uq_collected_keyword_source',
        'collected_keywords',
        ['keyword', 'source']
    )


def downgrade() -> None:
    # 1. 새 유니크 제약조건 삭제
    op.drop_constraint('uq_collected_keyword_source', 'collected_keywords', type_='unique')

    # 2. source 컬럼 삭제
    op.drop_column('collected_keywords', 'source')

    # 3. seed_keyword_id를 NOT NULL로 복원
    op.alter_column(
        'collected_keywords',
        'seed_keyword_id',
        existing_type=sa.Integer(),
        nullable=False
    )

    # 4. 기존 유니크 제약조건 복원
    op.create_unique_constraint(
        'uq_collected_keyword_seed',
        'collected_keywords',
        ['keyword', 'seed_keyword_id']
    )
