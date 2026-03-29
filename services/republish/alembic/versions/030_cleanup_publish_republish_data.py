"""기존 publish/republish 모듈 데이터 정리

Revision ID: 030
Revises: 029
Create Date: 2026-03-22

GP 통합: 기존 publish/republish 타입 모듈, FlowModule 관계,
ModuleType 레코드를 삭제합니다.
publish/republish 실행은 GP에서 직접 제어합니다.
"""
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 기존 publish/republish 타입 모듈의 FlowModule 관계 삭제
    op.execute("""
        DELETE FROM flow_modules
        WHERE module_id IN (
            SELECT m.id FROM modules m
            JOIN module_types mt ON m.module_type_id = mt.id
            WHERE mt.code IN ('publish', 'republish')
        )
    """)

    # 2. 기존 publish/republish 타입 모듈 삭제
    op.execute("""
        DELETE FROM modules
        WHERE module_type_id IN (
            SELECT id FROM module_types
            WHERE code IN ('publish', 'republish')
        )
    """)

    # 3. publish/republish 모듈 타입 삭제
    op.execute("""
        DELETE FROM module_types
        WHERE code IN ('publish', 'republish')
    """)


def downgrade() -> None:
    # publish/republish 모듈 타입 복원
    op.execute("""
        INSERT INTO module_types (code, name, icon, display_order, description)
        VALUES
            ('publish', '발행', '📤', 5, '블로그 발행 모듈'),
            ('republish', '재발행', '🔄', 6, '블로그 재발행 모듈')
        ON CONFLICT (code) DO NOTHING
    """)
    # 참고: 삭제된 modules, flow_modules 레코드는 복원 불가
