"""제목 D 방식 거르기 — 지문·사이트 점수 표와 판정 칸(2026-11-02, 마케팅·형 승인)

- title_fingerprints: 버린 제목의 지문(공백 뺀 소문자). 같은 제목이 다시 수집되면 바로 버린다.
- title_site_scores: 출처 사이트별 본 수·통과 수·상태(normal|blocked|priority).
- temp_titles / main_titles: 고른 검색어(lead_keyword)·판정(screen_result)·판정 시각.
  temp_titles 에는 검색량(search_volume)도 둔다(main_titles 는 090 에 있다).
- generation_histories: 출발 검색어(candidate_id)·출처 사이트(source_site) — B6.

Revision ID: 091
Revises: 090

순서도: docs/flowcharts/title_screen_d.md
"""
import sqlalchemy as sa
from alembic import op

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None

COLUMNS = {
    "temp_titles": (
        ("lead_keyword", sa.String(200)),
        ("search_volume", sa.Integer()),
        ("screen_result", sa.String(20)),
        ("screened_at", sa.DateTime(timezone=True)),
    ),
    "main_titles": (
        ("lead_keyword", sa.String(200)),
        ("screen_result", sa.String(20)),
        ("screened_at", sa.DateTime(timezone=True)),
    ),
    "generation_histories": (
        ("candidate_id", sa.Integer()),
        ("source_site", sa.String(255)),
    ),
}


def _columns(table: str) -> set:
    """표에 이미 있는 컬럼 이름."""
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set:
    """이미 있는 표 이름(create_all 로 먼저 생겼을 수 있다)."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """표 둘을 만들고 판정 칸을 더한다."""
    have = _tables()
    if "title_fingerprints" not in have:
        op.create_table(
            "title_fingerprints",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fingerprint", sa.String(500), nullable=False, unique=True),
            sa.Column("reason", sa.String(60), nullable=True),
            sa.Column("site", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "title_site_scores" not in have:
        op.create_table(
            "title_site_scores",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("site", sa.String(255), nullable=False, unique=True),
            sa.Column("seen", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="normal"),
            sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recheck_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_title_site_scores_status", "title_site_scores", ["status"])
    for table, cols in COLUMNS.items():
        exist = _columns(table)
        for name, type_ in cols:
            if name not in exist:
                op.add_column(table, sa.Column(name, type_, nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_temp_titles_screen_result "
               "ON temp_titles (screen_result)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_main_titles_screen_result "
               "ON main_titles (screen_result)")


def downgrade() -> None:
    """칸과 표를 뺀다(운영 서버에서는 쓰지 않는다)."""
    op.execute("DROP INDEX IF EXISTS ix_main_titles_screen_result")
    op.execute("DROP INDEX IF EXISTS ix_temp_titles_screen_result")
    for table, cols in COLUMNS.items():
        exist = _columns(table)
        for name, _ in cols:
            if name in exist:
                op.drop_column(table, name)
    have = _tables()
    for table in ("title_site_scores", "title_fingerprints"):
        if table in have:
            op.drop_table(table)
