"""니치 도메인에 추출 진행 상태·차단·품질 필드 추가

Revision ID: 067
Revises: 066

배경:
    옛 수집은 "키워드로 제목 검색 → 목표 수 채우면 종료" 였다. 도메인
    하나에서 목표를 다 못 채우면 **중단된 도메인은 저장만 되고 다시
    꺼내지지 않았다.** 그래서 URL 126,671건 중 처리된 것이 0.02% 였다.

    "어디까지 했는지" 를 남길 자리가 없던 것이 직접 원인이다.

추가하는 것:
    - 추출 진행: extract_status / extracted_count / last_extracted_at
    - 차단: is_blocked / blocked_reason / blocked_at
    - 품질: promoted_count / deleted_title_count

`is_active`(각도 조회 참조)와 `is_blocked`(재수집 차단)는 **축이 다르다.**
합치면 각도를 끄려다 재수집까지 막힌다.

계획서: docs/plans/title_tab_workplan.md §2-2 · §2-3 · §2-5
"""
import sqlalchemy as sa
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

TABLE = "niche_domains"

COLUMNS = (
    ("extract_status", sa.String(length=20), "pending", False),
    ("extracted_count", sa.Integer(), "0", False),
    ("last_extracted_at", sa.DateTime(timezone=True), None, True),
    ("is_blocked", sa.Boolean(), sa.text("false"), False),
    ("blocked_reason", sa.String(length=200), None, True),
    ("blocked_at", sa.DateTime(timezone=True), None, True),
    ("promoted_count", sa.Integer(), "0", False),
    ("deleted_title_count", sa.Integer(), "0", False),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        # 066 이 아직 안 돌았다. 그쪽이 테이블을 만든다.
        return

    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_, default, nullable in COLUMNS:
        if name in existing:
            continue
        op.add_column(TABLE, sa.Column(
            name, type_, nullable=nullable,
            server_default=default if default is not None else None))

    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    for name in ("extract_status", "is_blocked"):
        index = f"ix_{TABLE}_{name}"
        if index not in indexes and name not in existing:
            op.create_index(index, TABLE, [name])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, _t, _d, _n in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
