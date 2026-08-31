"""키워드 모듈 타입 추가

Revision ID: 057
Revises: 056

목적:
    keyword_lab 을 모듈로 승격한다. 지금은 화면에서 버튼을 눌러야만 돌아
    플로우·오토런·동작 로그 어디에도 붙지 않는다. 재고가 말라도 아무도
    채우지 않는다.

    module_types 컬럼: id, code, name, icon, display_order, created_at
    (description 은 없다 — 041 의 주의사항과 같다)

순서도: docs/flowcharts/keyword_module.md
"""
import sqlalchemy as sa
from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None

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
        sa.text("SELECT 1 FROM module_types WHERE code = 'keyword'")
    ).first()
    if exists:
        return

    op.bulk_insert(_MODULE_TYPES, [{
        "code": "keyword",
        "name": "키워드",
        "icon": "🔑",
        "display_order": 8,
    }])


def downgrade() -> None:
    conn = op.get_bind()
    # 플로우가 물고 있으면 지우지 않는다 — 참조 무결성이 깨진다.
    in_use = conn.execute(sa.text(
        "SELECT 1 FROM modules m JOIN module_types t ON t.id = m.module_type_id"
        " WHERE t.code = 'keyword'"
    )).first()
    if in_use:
        return
    conn.execute(sa.text("DELETE FROM module_types WHERE code = 'keyword'"))
