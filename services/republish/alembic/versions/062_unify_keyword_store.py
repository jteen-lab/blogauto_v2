"""키워드 저장소 일원화 — seed_keywords → keyword_candidates

Revision ID: 062
Revises: 061

배경:
    같은 개념이 세 테이블에 나뉘어 있었다.
        seed_keywords        지표 컬럼이 **아예 없다**(검색량·경쟁도 없음)
        collected_keywords   검색량·경쟁도만
        keyword_candidates   검색량·문서수·월발행량·포화도·판정·의도·클러스터·성과
    데이터 관리 키워드 탭이 seed_keywords 를 보고 있어 지표를 보여줄 수 없었고,
    "수집만 된 키워드를 기준값으로 분류" 자체가 불가능했다.

    지표가 이미 있는 keyword_candidates 를 정본으로 삼는다.

하는 일:
    1) 운영에 필요한 컬럼 보강(is_active/use_count/last_used_at/priority)
    2) **전역 풀 중복 방지** — (user_id, keyword) WHERE blog_id IS NULL 부분 유니크.
       (user_id, blog_id, keyword) 유니크는 blog_id 가 NULL 이면 NULL 끼리
       서로 다르다고 보아 중복을 못 막는다.
    3) seed_keywords 를 blog_id NULL(전역 풀)로 이관. 이미 있는 키워드는 건너뛴다.

seed_keywords 는 **지우지 않는다.** 기존 수집 모듈이 아직 읽고 쓴다.
전환이 끝나면(계획서 S6) 그때 정리한다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §6
"""
import sqlalchemy as sa
from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None

TABLE = "keyword_candidates"
LEGACY = "seed_keywords"
GLOBAL_UQ = "uq_keyword_candidate_global"

# 이관분 표시. 어디서 온 키워드인지 남겨야 되돌릴 수 있다.
LEGACY_SOURCE = "legacy_seed"

NEW_COLUMNS = (
    ("is_active", sa.Column("is_active", sa.Boolean(), nullable=False,
                            server_default=sa.text("true"),
                            comment="활성 상태")),
    ("use_count", sa.Column("use_count", sa.Integer(), nullable=False,
                            server_default="0", comment="사용 횟수")),
    ("last_used_at", sa.Column("last_used_at", sa.DateTime(timezone=True),
                               nullable=True)),
    ("priority", sa.Column("priority", sa.Integer(), nullable=False,
                           server_default="0", comment="순환 우선순위")),
    ("legacy_seed_id", sa.Column("legacy_seed_id", sa.Integer(), nullable=True,
                                 comment="이관 전 seed_keywords.id")),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return

    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, column in NEW_COLUMNS:
        if name not in columns:
            op.add_column(TABLE, column)

    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    if GLOBAL_UQ not in indexes:
        # 전역 풀(blog_id IS NULL)에서만 키워드 유일성을 강제한다.
        op.create_index(
            GLOBAL_UQ, TABLE, ["user_id", "keyword"], unique=True,
            postgresql_where=sa.text("blog_id IS NULL"),
            sqlite_where=sa.text("blog_id IS NULL"),
        )

    if inspector.has_table(LEGACY):
        _migrate_rows(conn)


def _migrate_rows(conn) -> None:
    """seed_keywords 를 전역 풀로 옮긴다. 멱등하다.

    지표는 비운 채(미측정) 넣는다. 이후 측정 회차가 채운다.
    소유자는 사용자 최솟값을 쓴다 — seed_keywords 에는 user_id 가 없다.
    """
    owner = conn.execute(sa.text("SELECT MIN(id) FROM users")).scalar()
    if not owner:
        return

    moved = conn.execute(sa.text(f"""
        INSERT INTO {TABLE} (
            user_id, keyword, blog_id, topic_id, subtopic_id,
            verdict, source, is_active, use_count, last_used_at,
            priority, legacy_seed_id, created_at
        )
        SELECT
            :owner, s.keyword, NULL, s.topic_id, s.subtopic_id,
            'pending', :source, s.is_active, s.use_count, s.last_used_at,
            s.priority, s.id, s.created_at
        FROM {LEGACY} s
        WHERE NOT EXISTS (
            SELECT 1 FROM {TABLE} k
            WHERE k.user_id = :owner
              AND k.blog_id IS NULL
              AND lower(k.keyword) = lower(s.keyword)
        )
    """), {"owner": owner, "source": LEGACY_SOURCE})
    print(f"[migration 062] seed_keywords 이관: {moved.rowcount}건")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return

    # 이관분만 되돌린다. 원래 후보는 건드리지 않는다.
    conn.execute(sa.text(
        f"DELETE FROM {TABLE} WHERE source = :source AND legacy_seed_id IS NOT NULL"
    ), {"source": LEGACY_SOURCE})

    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    if GLOBAL_UQ in indexes:
        op.drop_index(GLOBAL_UQ, table_name=TABLE)

    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    for name, _ in reversed(NEW_COLUMNS):
        if name in columns:
            op.drop_column(TABLE, name)
