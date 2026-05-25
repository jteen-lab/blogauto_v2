"""Add index on modules.module_type_id

Revision ID: 038
Create Date: 2026-05-25

목적:
    modules.module_type_id 컬럼은 ForeignKey만 선언되어 있고 인덱스가 없어,
    used-blog-categories 조회 (ModuleType.code='prompt' AND user_id=? 조인)가
    DB 부하 상황에서 64초까지 걸리던 회귀의 root cause 중 하나였다.
    인덱스를 추가하여 쿼리 플랜이 항상 인덱스 기반으로 동작하도록 한다.

참고:
    함께 적용되는 클라이언트 측 수정으로 used-blog-categories 호출 중복도
    제거되었으므로 양쪽 모두에서 부하가 줄어든다.
"""
from alembic import op


revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """modules.module_type_id 인덱스 생성."""
    op.create_index(
        'ix_modules_module_type_id',
        'modules',
        ['module_type_id'],
        unique=False,
    )


def downgrade() -> None:
    """인덱스 제거."""
    op.drop_index('ix_modules_module_type_id', table_name='modules')
