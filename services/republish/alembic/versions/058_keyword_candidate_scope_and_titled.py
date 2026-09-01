"""키워드 후보 — 블로그별 격리 + 제목 생성 플래그 분리

Revision ID: 058
Revises: 057

목적 1) 유일성을 (user_id, keyword) → (user_id, blog_id, keyword) 로 넓힌다.
    사용자 전역으로 걸려 있어 1번 블로그가 먼저 잡은 키워드를 2~12번 블로그가
    영원히 재수집하지 못했다(검토서 D-6).

목적 2) `titled` 컬럼을 추가해 `promoted` 와 뜻을 분리한다.
    promoted = "시드로 이미 썼다" / titled = "제목을 이미 만들었다".
    한 칸을 겸용해 **검색량 상위 채택 키워드가 시드로 소비되면서 제목 대상에서
    빠지는** 문제가 있었다(검토서 D-4).

백필 방침: `titled` 는 전부 false 로 둔다. 시드로만 소비돼 제목을 못 받은
    키워드들이 이번에 제목을 받게 하기 위해서다. 이미 제목이 있는 키워드는
    TitleMaker 의 제목 중복 검사에서 걸러진다.

순서도: docs/flowcharts/keyword_module.md
"""
import sqlalchemy as sa
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

TABLE = "keyword_candidates"
OLD_UQ = "uq_keyword_candidate"
NEW_UQ = "uq_keyword_candidate_blog"


def _columns(conn) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(TABLE):
        return

    if "titled" not in _columns(conn):
        op.add_column(TABLE, sa.Column(
            "titled", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
            comment="제목을 이미 만든 키워드인지",
        ))

    names = {c["name"] for c in sa.inspect(conn).get_unique_constraints(TABLE)}
    if NEW_UQ in names:
        return

    # SQLite 는 제약 삭제를 지원하지 않아 batch(테이블 재생성)로 처리한다.
    with op.batch_alter_table(TABLE) as batch:
        if OLD_UQ in names:
            batch.drop_constraint(OLD_UQ, type_="unique")
        batch.create_unique_constraint(
            NEW_UQ, ["user_id", "blog_id", "keyword"])


def downgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(TABLE):
        return

    names = {c["name"] for c in sa.inspect(conn).get_unique_constraints(TABLE)}
    with op.batch_alter_table(TABLE) as batch:
        if NEW_UQ in names:
            batch.drop_constraint(NEW_UQ, type_="unique")
        if OLD_UQ not in names:
            batch.create_unique_constraint(OLD_UQ, ["user_id", "keyword"])

    if "titled" in _columns(conn):
        op.drop_column(TABLE, "titled")
