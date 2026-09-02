"""URL 12만 건을 니치 도메인 자산으로 요약 — 원본은 버린다

Revision ID: 066
Revises: 065

배경:
    `collected_urls` 에 126,671행이 쌓였다. 287개 도메인의 사이트맵을
    통째로 긁은 결과다(도메인당 최대 801행). 98.9%는 제목까지 수집돼
    있었지만 `is_processed` 는 31건(0.02%)뿐 — 소비하는 코드가 없었다.

    개별 URL 은 재고로서 가치가 없다. 가치는 "이 니치에서 누가 상위에
    있는가" 라는 **도메인 단위 정보**에 있다.

하는 일:
    1) `niche_domains` 생성
    2) `collected_urls` 를 도메인별로 집계해 적재
       (URL 수 · 대표 제목 샘플 · 대표 키워드 · 최초/최종 관측)
    3) `collected_urls` 의 행을 **삭제**

소유자 결정:
    `collected_urls` 에는 user_id 가 없다. `source_module_id` → `modules`
    로 역추적하고, 없으면(레거시 행) 가장 오래된 사용자에게 준다.

⚠️ 되돌릴 수 없다. downgrade 는 `niche_domains` 만 지운다 — URL 원본은
   복구되지 않는다. 도메인 요약은 남으므로 정보 손실은 아니다.

테이블 자체는 남긴다. 옛 `bulk_collect` 코드가 아직 참조한다.

계획서: docs/plans/title_pipeline_redesign_plan.md §2-3
"""
import sqlalchemy as sa
from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None

TABLE = "niche_domains"
SOURCE = "collected_urls"

# 도메인당 남길 대표 제목·키워드 수. 각도는 몇 가지로 수렴하므로
# 많이 남겨도 신호가 좋아지지 않는다.
SAMPLE_TITLES = 20
SAMPLE_KEYWORDS = 10


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("domain", sa.String(length=200), nullable=False),
            sa.Column("platform", sa.String(length=50), nullable=False,
                      server_default="unknown"),
            sa.Column("url_count", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("sample_titles", sa.Text(), nullable=True),
            sa.Column("top_keywords", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column("first_seen_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "domain", name="uq_niche_domain"),
        )
        op.create_index(f"ix_{TABLE}_id", TABLE, ["id"])
        op.create_index(f"ix_{TABLE}_user_id", TABLE, ["user_id"])
        op.create_index(f"ix_{TABLE}_domain", TABLE, ["domain"])
        op.create_index(f"ix_{TABLE}_is_active", TABLE, ["is_active"])

    if not inspector.has_table(SOURCE):
        return

    fallback = conn.execute(
        sa.text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
    if fallback is None:
        print("[migration 066] 사용자가 없어 요약을 건너뛴다")
        return

    columns = {c["name"] for c in inspector.get_columns(SOURCE)}
    # 모듈 역추적은 컬럼이 있을 때만. 없으면 전부 fallback 사용자.
    owner = ("COALESCE((SELECT m.user_id FROM modules m "
             "WHERE m.id = u.source_module_id), :fallback)"
             if "source_module_id" in columns else ":fallback")

    total = conn.execute(sa.text(f"SELECT count(*) FROM {SOURCE}")).scalar() or 0
    if not total:
        print("[migration 066] 요약할 URL 이 없다")
        return

    _summarize(conn, owner, fallback)

    deleted = conn.execute(sa.text(f"DELETE FROM {SOURCE}")).rowcount
    kept = conn.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar() or 0
    print(f"[migration 066] URL {deleted}건 → 도메인 {kept}건으로 요약")


def _summarize(conn, owner: str, fallback: int) -> None:
    """도메인별로 집계해 적재한다. 이미 있는 도메인은 갱신한다."""
    rows = conn.execute(sa.text(f"""
        SELECT {owner} AS user_id,
               u.domain,
               MIN(u.platform) AS platform,
               count(*) AS url_count,
               MIN(u.created_at) AS first_seen_at,
               MAX(u.created_at) AS last_seen_at
          FROM {SOURCE} u
         WHERE u.domain IS NOT NULL AND u.domain <> ''
         GROUP BY 1, 2
    """), {"fallback": fallback}).fetchall()

    for row in rows:
        titles = conn.execute(sa.text(f"""
            SELECT DISTINCT COALESCE(u.title, u.search_title) AS t
              FROM {SOURCE} u
             WHERE u.domain = :domain
               AND COALESCE(u.title, u.search_title) IS NOT NULL
             LIMIT :limit
        """), {"domain": row.domain, "limit": SAMPLE_TITLES}).fetchall()
        keywords = conn.execute(sa.text(f"""
            SELECT DISTINCT u.search_keyword AS k
              FROM {SOURCE} u
             WHERE u.domain = :domain AND u.search_keyword IS NOT NULL
             LIMIT :limit
        """), {"domain": row.domain, "limit": SAMPLE_KEYWORDS}).fetchall()

        conn.execute(sa.text(f"""
            INSERT INTO {TABLE}
                (user_id, domain, platform, url_count, sample_titles,
                 top_keywords, is_active, first_seen_at, last_seen_at)
            VALUES
                (:user_id, :domain, :platform, :url_count, :titles,
                 :keywords, TRUE, :first_seen, :last_seen)
            ON CONFLICT (user_id, domain) DO UPDATE SET
                url_count = EXCLUDED.url_count,
                sample_titles = EXCLUDED.sample_titles,
                top_keywords = EXCLUDED.top_keywords,
                last_seen_at = EXCLUDED.last_seen_at
        """), {
            "user_id": row.user_id, "domain": row.domain,
            "platform": row.platform or "unknown",
            "url_count": row.url_count,
            "titles": "\n".join(r[0] for r in titles if r[0]) or None,
            "keywords": "\n".join(r[0] for r in keywords if r[0]) or None,
            "first_seen": row.first_seen_at, "last_seen": row.last_seen_at,
        })


def downgrade() -> None:
    """도메인 자산만 지운다. URL 원본은 복구되지 않는다."""
    conn = op.get_bind()
    if sa.inspect(conn).has_table(TABLE):
        op.drop_table(TABLE)
