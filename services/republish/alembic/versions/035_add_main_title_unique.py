"""add unique constraint on main_titles (title, topic_id)

Revision ID: 035
Create Date: 2026-03-30

목적:
    동일 topic_id 내에서 같은 title 을 갖는 MainTitle 중복 생성을 DB 레벨에서 차단.

주의:
    이 마이그레이션은 중복 MainTitle 행을 **삭제**합니다.
    실행 전 반드시 백업을 권장합니다.

중복 정리 규칙:
    - (title, topic_id) 조합이 동일한 행 중 가장 오래된 행(MIN(id))만 유지
    - CrawledPost.matched_main_title_id 는 유지되는 행의 id 로 업데이트
    - TitleGroup.representative_title_id 도 유지되는 행의 id 로 업데이트
    - 나머지 중복 행은 DELETE
"""
from alembic import op
import sqlalchemy as sa


revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """중복 정리 후 유니크 제약 추가"""
    conn = op.get_bind()

    # 1. 중복 그룹 식별: (title, topic_id) 기준, 유지 id=MIN(id), 삭제 대상 리스트
    #    topic_id 는 NULL 도 포함해서 그룹핑 (PostgreSQL IS NOT DISTINCT FROM 사용)
    duplicates_sql = sa.text(
        """
        SELECT
            MIN(id) AS keep_id,
            ARRAY_AGG(id) FILTER (WHERE id <> MIN(id)) AS remove_ids,
            title,
            topic_id,
            COUNT(*) AS dup_count
        FROM main_titles
        GROUP BY title, topic_id
        HAVING COUNT(*) > 1
        """
    )
    duplicates = conn.execute(duplicates_sql).fetchall()

    total_dup_rows = 0
    total_dup_groups = len(duplicates)

    if total_dup_groups == 0:
        print("[migration 035] 중복된 MainTitle 이 없습니다. 제약만 추가합니다.")
    else:
        print(
            f"[migration 035] 중복 그룹 {total_dup_groups} 개 발견. 정리를 시작합니다."
        )

    for row in duplicates:
        keep_id = row.keep_id
        remove_ids = list(row.remove_ids or [])
        if not remove_ids:
            continue
        total_dup_rows += len(remove_ids)
        print(
            f"[migration 035] title='{(row.title or '')[:40]}' "
            f"topic_id={row.topic_id} keep={keep_id} remove={remove_ids}"
        )

        # 2. 연관 테이블의 참조를 keep_id 로 재지정
        # 2-1. crawled_posts.matched_main_title_id
        conn.execute(
            sa.text(
                """
                UPDATE crawled_posts
                SET matched_main_title_id = :keep_id
                WHERE matched_main_title_id = ANY(:remove_ids)
                """
            ),
            {"keep_id": keep_id, "remove_ids": remove_ids},
        )

        # 2-2. title_groups.representative_title_id
        conn.execute(
            sa.text(
                """
                UPDATE title_groups
                SET representative_title_id = :keep_id
                WHERE representative_title_id = ANY(:remove_ids)
                """
            ),
            {"keep_id": keep_id, "remove_ids": remove_ids},
        )

        # 3. 중복 MainTitle 삭제
        conn.execute(
            sa.text(
                """
                DELETE FROM main_titles
                WHERE id = ANY(:remove_ids)
                """
            ),
            {"remove_ids": remove_ids},
        )

    if total_dup_groups > 0:
        print(
            f"[migration 035] 총 {total_dup_rows} 행 삭제 완료 "
            f"(그룹 {total_dup_groups})"
        )

    # 4. 유니크 제약 추가
    op.create_unique_constraint(
        'uq_main_title_topic',
        'main_titles',
        ['title', 'topic_id'],
    )
    print("[migration 035] uq_main_title_topic 제약 추가 완료")


def downgrade() -> None:
    """유니크 제약 제거"""
    op.drop_constraint('uq_main_title_topic', 'main_titles', type_='unique')
