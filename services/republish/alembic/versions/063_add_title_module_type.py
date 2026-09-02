"""제목 생성/수집 모듈 타입 추가

Revision ID: 063
Revises: 062

목적:
    수집 모듈이 제목까지 만들면 중간 결과를 걸러낼 자리가 없고 실패가 한
    덩어리로 묻힌다. 제목 단계를 별도 모듈로 뗀다.

    module_types 컬럼: id, code, name, icon, display_order, created_at
    (description 은 없다 — 041·057 의 주의사항과 같다)

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2
"""
import sqlalchemy as sa
from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None

CODE = "title_gen"

_MODULE_TYPES = sa.table(
    "module_types",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("icon", sa.String),
    sa.column("display_order", sa.Integer),
)


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM module_types WHERE code = :code"),
        {"code": CODE},
    ).first()
    if exists:
        return

    op.bulk_insert(_MODULE_TYPES, [{
        "code": CODE,
        "name": "제목 생성/수집",
        "icon": "📝",
        "display_order": 9,
    }])


def downgrade() -> None:
    conn = op.get_bind()
    # 플로우가 물고 있으면 지우지 않는다 — 참조 무결성이 깨진다.
    in_use = conn.execute(sa.text(
        "SELECT 1 FROM modules m JOIN module_types t ON t.id = m.module_type_id"
        " WHERE t.code = :code"
    ), {"code": CODE}).first()
    if in_use:
        return
    conn.execute(sa.text("DELETE FROM module_types WHERE code = :code"),
                 {"code": CODE})
