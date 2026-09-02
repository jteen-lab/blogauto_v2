"""시드 키워드 테이블 제거 — 저장소 일원화 완료

Revision ID: 065
Revises: 064

배경:
    062 에서 `seed_keywords` 6,333건을 정본(`keyword_candidates`)으로 이관했다.
    그 뒤 구 수집 모듈이 플로우에서 빠지며 신규 유입이 끊겼다(최근 7일 0건).
    읽고 쓰던 코드도 모두 정본으로 옮겼다.

    이제 두 저장소를 유지할 이유가 없다.

지우기 전에 확인한 것:
    - 이관 완료(정본에 `source='legacy_seed'` 로 남아 있다)
    - `collect`·`bulk_collect` 모듈이 어느 플로우에도 없다
    - 코드에서 `SeedKeyword` 참조가 0

`collected_keywords.seed_keyword_id` 는 이 테이블을 가리키는 유일한 FK 라
함께 걷어낸다. 연관 키워드 자체(26건)는 남긴다.

⚠️ 되돌릴 수 없다. downgrade 는 **빈 테이블만** 되살린다 — 데이터는
   정본에 있으므로 손실은 아니다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §5-3
"""
import sqlalchemy as sa
from alembic import op

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None

TABLE = "seed_keywords"
CHILD = "collected_keywords"
CHILD_COLUMN = "seed_keyword_id"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1) 자식 FK 부터 끊는다. 안 끊으면 부모를 못 지운다.
    if inspector.has_table(CHILD):
        columns = {c["name"] for c in inspector.get_columns(CHILD)}
        if CHILD_COLUMN in columns:
            for fk in inspector.get_foreign_keys(CHILD):
                if fk.get("referred_table") == TABLE and fk.get("name"):
                    op.drop_constraint(fk["name"], CHILD, type_="foreignkey")
            op.drop_column(CHILD, CHILD_COLUMN)

    if not inspector.has_table(TABLE):
        return

    moved = conn.execute(sa.text(
        "SELECT count(*) FROM keyword_candidates WHERE source = 'legacy_seed'"
    )).scalar() or 0
    remaining = conn.execute(
        sa.text(f"SELECT count(*) FROM {TABLE}")).scalar() or 0
    print(f"[migration 065] 정본 이관분 {moved}건 확인 · "
          f"{TABLE} {remaining}건 삭제")

    op.drop_table(TABLE)


def downgrade() -> None:
    """빈 테이블만 되살린다. 데이터는 정본에 있다."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("keyword", sa.String(length=200), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("topic_id", sa.Integer(), nullable=True),
            sa.Column("subtopic_id", sa.Integer(), nullable=True),
            sa.Column("matched_keyword_id", sa.Integer(), nullable=True),
            sa.Column("source_type", sa.String(length=50), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if inspector.has_table(CHILD):
        columns = {c["name"] for c in inspector.get_columns(CHILD)}
        if CHILD_COLUMN not in columns:
            op.add_column(CHILD, sa.Column(CHILD_COLUMN, sa.Integer(),
                                           nullable=True))
