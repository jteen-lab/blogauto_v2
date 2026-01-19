"""템플릿 그룹 필드 추가

Revision ID: 006
Revises: 005
Create Date: 2025-01-16

Features:
- flow_modules 테이블에 group_id 추가 (템플릿 그룹)
- flow_modules 테이블에 template_name 추가 (그룹 헤더 표시)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # group_id 컬럼 추가
    op.add_column(
        'flow_modules',
        sa.Column(
            'group_id',
            sa.String(50),
            nullable=True,
            comment='템플릿 그룹 ID (템플릿으로 추가된 모듈들 묶음)'
        )
    )

    # template_name 컬럼 추가
    op.add_column(
        'flow_modules',
        sa.Column(
            'template_name',
            sa.String(100),
            nullable=True,
            comment='템플릿 이름 (그룹 헤더에 표시)'
        )
    )

    # group_id 인덱스 생성
    op.create_index(
        'ix_flow_modules_group_id',
        'flow_modules',
        ['group_id'],
        unique=False
    )


def downgrade() -> None:
    # 인덱스 삭제
    op.drop_index('ix_flow_modules_group_id', table_name='flow_modules')

    # 컬럼 삭제
    op.drop_column('flow_modules', 'template_name')
    op.drop_column('flow_modules', 'group_id')
