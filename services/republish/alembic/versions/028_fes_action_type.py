"""FES module_id → action_type 전환

Revision ID: 028
Revises: 027
Create Date: 2026-03-22

GP 통합: FlowExecutionState에서 module_id FK를 제거하고
action_type(String) 컬럼으로 교체합니다.

기존 데이터는 modules → module_types JOIN으로 action_type을 매핑합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. action_type 컬럼 추가 (nullable로 먼저)
    op.add_column(
        "flow_execution_states",
        sa.Column("action_type", sa.String(30), nullable=True),
    )

    # 2. 기존 데이터: module_id → action_type 매핑
    #    PostgreSQL 전용 UPDATE ... FROM 구문
    op.execute("""
        UPDATE flow_execution_states fes
        SET action_type = mt.code
        FROM modules m
        JOIN module_types mt ON m.module_type_id = mt.id
        WHERE fes.module_id = m.id
    """)

    # 3. 매핑 안 된 레코드 (삭제된 모듈 등) 기본값
    op.execute("""
        UPDATE flow_execution_states
        SET action_type = 'unknown'
        WHERE action_type IS NULL
    """)

    # 4. NOT NULL 제약 추가
    op.alter_column(
        "flow_execution_states",
        "action_type",
        nullable=False,
    )

    # 5. 기존 유니크 인덱스 삭제
    op.drop_index("ix_fes_flow_module_blog")

    # 6. 새 유니크 인덱스 생성
    op.create_index(
        "ix_fes_flow_action_blog",
        "flow_execution_states",
        ["flow_id", "action_type", "blog_id"],
        unique=True,
    )

    # 7. module_id 인덱스 삭제 (FK 제거 전)
    op.drop_index(
        "ix_flow_execution_states_module_id",
        table_name="flow_execution_states",
    )

    # 8. module_id FK 제거
    op.drop_constraint(
        "flow_execution_states_module_id_fkey",
        "flow_execution_states",
        type_="foreignkey",
    )

    # 9. module_id 컬럼 삭제
    op.drop_column("flow_execution_states", "module_id")

    # 10. action_type 인덱스 추가
    op.create_index(
        "ix_flow_execution_states_action_type",
        "flow_execution_states",
        ["action_type"],
    )


def downgrade() -> None:
    # action_type 인덱스 삭제
    op.drop_index(
        "ix_flow_execution_states_action_type",
        table_name="flow_execution_states",
    )

    # module_id 컬럼 복원
    op.add_column(
        "flow_execution_states",
        sa.Column(
            "module_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # module_id FK 복원
    op.create_foreign_key(
        "flow_execution_states_module_id_fkey",
        "flow_execution_states",
        "modules",
        ["module_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # module_id 인덱스 복원
    op.create_index(
        "ix_flow_execution_states_module_id",
        "flow_execution_states",
        ["module_id"],
    )

    # 새 유니크 인덱스 삭제
    op.drop_index("ix_fes_flow_action_blog")

    # 기존 유니크 인덱스 복원
    op.create_index(
        "ix_fes_flow_module_blog",
        "flow_execution_states",
        ["flow_id", "module_id", "blog_id"],
        unique=True,
    )

    # action_type 컬럼 삭제
    op.drop_column("flow_execution_states", "action_type")
