"""Add pg_trgm extension + GIN trigram index on title columns

Revision ID: 039
Create Date: 2026-05-29

목적 (memory_optimization_plan.md Phase 2):
    제목 유사도 매칭의 N×M 전수 Jaccard 비교를 줄이기 위해, DB 가
    트라이그램 색인으로 "유사 후보"만 먼저 추려낼 수 있게 한다.
    main_titles.title / temp_titles.title 에 GIN(gin_trgm_ops) 인덱스 생성.

    이후 매칭 로직은 `title % :query` (trigram similarity) 또는
    `similarity(title, :query) > 임계값` 으로 후보를 DB 에서 추출하고,
    파이썬은 소수 후보만 정밀 비교한다(별도 코드 변경).

참고:
    - pg_trgm 확장은 슈퍼유저 권한 필요. 운영 DB(postgres 컨테이너)는
      기본 superuser(blogauto)로 생성됐다면 가능.
    - GIN 인덱스 생성은 대용량에서 시간이 걸릴 수 있으나 CONCURRENTLY 는
      트랜잭션 밖에서만 가능하므로, 여기서는 일반 생성(소규모 전제).
"""
from alembic import op


revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """pg_trgm 확장 + GIN 트라이그램 인덱스 생성."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_main_titles_title_trgm "
        "ON main_titles USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_temp_titles_title_trgm "
        "ON temp_titles USING gin (title gin_trgm_ops)"
    )


def downgrade() -> None:
    """트라이그램 인덱스 제거 (확장은 보존)."""
    op.execute("DROP INDEX IF EXISTS ix_temp_titles_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_main_titles_title_trgm")
