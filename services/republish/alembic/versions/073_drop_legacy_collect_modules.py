"""옛 수집·대량수집 모듈 제거

Revision ID: 073
Revises: 072

배경:
    제목 수집·생성은 `title_gen` 모듈로 옮겼고 운영 테스트가 끝났다.
    `collect`·`bulk_collect` 는 그 자리를 대신하던 옛 경로다.

    옛 수집은 키워드 수집과 제목 수집을 한 사이클에서 했고, 도메인 하나
    에서 목표를 못 채우면 그 도메인을 방치했다(URL 12만 건 중 0.02%만
    처리). 새 구조가 그 문제를 풀었으므로 남겨 둘 이유가 없다.

지우기 전에 확인한 것:
    - 두 타입의 모듈은 각각 1개씩이고 **어느 플로우에도 연결돼 있지 않다**
    - 사이트맵 파서는 `title_collect/sitemap.py` 로 옮겨 새 코드가 옛
      패키지에 의존하지 않는다

⚠️ 되돌릴 수 없다. downgrade 는 **타입만** 되살린다 — 모듈 인스턴스와
   그 설정은 복구되지 않는다.

계획서: docs/plans/title_tab_workplan.md §6
"""
import sqlalchemy as sa
from alembic import op

revision = "073"
down_revision = "072"
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
        print("[migration 073] 제거할 모듈 타입이 없다")
        return

    # 플로우에 물려 있으면 지우지 않는다. 운영이 도는 중일 수 있다.
    if inspector.has_table("flow_modules"):
        linked = conn.execute(sa.text(
            "SELECT count(*) FROM flow_modules fm "
            "JOIN modules m ON m.id = fm.module_id "
            "WHERE m.module_type_id = ANY(:ids)"), {"ids": ids}).scalar() or 0
        if linked:
            print(f"[migration 073] 플로우에 {linked}건 연결돼 있어 건너뛴다")
            return

    modules = conn.execute(sa.text(
        "SELECT count(*) FROM modules WHERE module_type_id = ANY(:ids)"),
        {"ids": ids}).scalar() or 0

    conn.execute(sa.text(
        "DELETE FROM modules WHERE module_type_id = ANY(:ids)"), {"ids": ids})
    conn.execute(sa.text(
        "DELETE FROM module_types WHERE id = ANY(:ids)"), {"ids": ids})
    print(f"[migration 073] 모듈 {modules}건 · 타입 {len(ids)}건 제거")


def downgrade() -> None:
    """타입만 되살린다. 모듈 인스턴스는 복구되지 않는다."""
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("module_types"):
        return

    rows = (("collect", "수집", "키워드·제목 수집(폐기)"),
            ("bulk_collect", "대량 수집", "사이트맵 기반 대량 수집(폐기)"))
    for code, name, description in rows:
        exists = conn.execute(sa.text(
            "SELECT 1 FROM module_types WHERE code = :code"),
            {"code": code}).scalar()
        if exists:
            continue
        conn.execute(sa.text(
            "INSERT INTO module_types (code, name, description, is_active) "
            "VALUES (:code, :name, :description, FALSE)"),
            {"code": code, "name": name, "description": description})
