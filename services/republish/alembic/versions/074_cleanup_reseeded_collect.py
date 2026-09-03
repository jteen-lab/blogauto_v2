"""시드로 되살아난 collect 타입 정리

Revision ID: 074
Revises: 073

배경:
    073 이 `collect`·`bulk_collect` 타입을 지웠는데, 앱이 시작할 때
    `seed_module_types()` 가 `ModuleType.get_default_types()` 를 보고
    **`collect` 를 다시 만들었다.** 마이그레이션이 지워도 다음 재시작에
    되살아나는 구조였다.

    기본 목록에서 뺐으므로 이제 되살아나지 않는다. 남아 있는 행만
    정리한다.

073 과 같은 안전장치를 둔다 — 플로우에 물려 있으면 지우지 않는다.

계획서: docs/plans/title_tab_workplan.md §6
"""
import sqlalchemy as sa
from alembic import op

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None

CODES = ("collect", "bulk_collect")


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("module_types"):
        return

    ids = [row[0] for row in conn.execute(sa.text(
        "SELECT id FROM module_types WHERE code = ANY(:codes)"
    ), {"codes": list(CODES)}).fetchall()]
    if not ids:
        return

    if inspector.has_table("flow_modules"):
        linked = conn.execute(sa.text(
            "SELECT count(*) FROM flow_modules fm "
            "JOIN modules m ON m.id = fm.module_id "
            "WHERE m.module_type_id = ANY(:ids)"), {"ids": ids}).scalar() or 0
        if linked:
            print(f"[migration 074] 플로우에 {linked}건 연결돼 있어 건너뛴다")
            return

    conn.execute(sa.text(
        "DELETE FROM modules WHERE module_type_id = ANY(:ids)"), {"ids": ids})
    conn.execute(sa.text(
        "DELETE FROM module_types WHERE id = ANY(:ids)"), {"ids": ids})
    print(f"[migration 074] 되살아난 타입 {len(ids)}건 제거")


def downgrade() -> None:
    """073 의 downgrade 가 되살린다. 여기서는 아무것도 하지 않는다."""
