"""Phase A-041: 대량 수집(bulk_collect) 모듈 타입 + 관련 스키마 추가

Revision ID: 041
Revises: 040
Create Date: 2026-06-02

목적 (대량 수집 모듈 분리 Phase A):
    기존 '수집(collect)' 모듈은 키워드 단위 검색·수집에 묶여 있다.
    블로그(도메인) 단위로 sitemap → URL 적재 → 후속 주기 제목 추출
    파이프라인을 별도 모듈로 분리하기 위해 다음을 도입한다.

    1. module_types: 'bulk_collect' row 1개 추가 (display_order=5)
    2. collected_urls: 제목 수집 결과 컬럼 3종 추가
        - title (String 500, nullable)
        - title_fetched_at (DateTime, nullable)
        - title_fetch_status (String 20, server_default='pending')
       + 부분 인덱스 ix_collected_urls_title_pending
         (PostgreSQL 만, SQLite 는 부분 인덱스 미지원이라 skip)
    3. bulk_collect_progress 신규 테이블
        - (module_id, blog_domain) 단위 진행 상태
        - last_seen_lastmod (다음 사이클 신규 변경 감지 기준)
        - 사이클 메트릭 (duration, processed, failed)

비고:
    - module_types 컬럼: id, code, name, icon, display_order, created_at
      (description 컬럼은 존재하지 않으므로 bulk_insert 키에 포함 금지)
    - collected_urls 의 기존 unique 는 (domain) — 모듈별 분리는 추후 단계에서.
"""
import logging

import sqlalchemy as sa
from alembic import op


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

# bulk_insert 시 사용할 module_types 가상 테이블 (description 컬럼 없음 주의)
_MODULE_TYPES_TABLE = sa.table(
    "module_types",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("icon", sa.String),
    sa.column("display_order", sa.Integer),
)


def _is_postgres() -> bool:
    """현재 alembic context 가 PostgreSQL 인지 여부.

    부분 인덱스(`WHERE ...`)는 PostgreSQL 만 안정적으로 지원.
    SQLite 도 3.8+ 부터 가능하지만 alembic op.create_index 의
    postgresql_where 옵션은 PG 전용이라 dialect 분기를 둔다.
    """
    try:
        return op.get_context().dialect.name == "postgresql"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("dialect 판별 실패: %s", exc)
        return False


def upgrade() -> None:
    """Phase A-041 upgrade.

    1) module_types: 'bulk_collect' row INSERT
    2) collected_urls: title / title_fetched_at / title_fetch_status 컬럼 추가
       + (PG 한정) 부분 인덱스 ix_collected_urls_title_pending
    3) bulk_collect_progress 테이블 생성 + UNIQUE 제약
    """
    # ─────────────────────────────────────────────
    # 1) module_types row 추가
    # ─────────────────────────────────────────────
    op.bulk_insert(
        _MODULE_TYPES_TABLE,
        [
            {
                "code": "bulk_collect",
                "name": "대량 수집",
                "icon": "🚀",
                # 기존 (prompt=1, generate=2, collect=3, data=4) 다음 자리
                "display_order": 5,
            }
        ],
    )

    # ─────────────────────────────────────────────
    # 2) collected_urls 컬럼 추가
    # ─────────────────────────────────────────────
    op.add_column(
        "collected_urls",
        sa.Column(
            "title",
            sa.String(length=500),
            nullable=True,
            comment="수집된 포스트 제목 (Phase 2에서 추출)",
        ),
    )
    op.add_column(
        "collected_urls",
        sa.Column(
            "title_fetched_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="제목 수집(또는 마지막 시도) 시각",
        ),
    )
    op.add_column(
        "collected_urls",
        sa.Column(
            "title_fetch_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="제목 수집 상태 (pending|done|failed)",
        ),
    )

    # 부분 인덱스: pending 인 row 만 빠르게 큐잉
    # 모듈별 컬럼이 collected_urls 에 없으므로 (domain, id) 조합으로 정의
    if _is_postgres():
        op.create_index(
            "ix_collected_urls_title_pending",
            "collected_urls",
            ["domain", "id"],
            unique=False,
            postgresql_where=sa.text("title_fetch_status = 'pending'"),
        )
    else:
        # SQLite 등에서는 full index 로 대체 (없는 것보단 낫고, 운영 DB는 PG)
        op.create_index(
            "ix_collected_urls_title_pending",
            "collected_urls",
            ["title_fetch_status", "domain", "id"],
            unique=False,
        )

    # ─────────────────────────────────────────────
    # 3) bulk_collect_progress 신규 테이블
    # ─────────────────────────────────────────────
    op.create_table(
        "bulk_collect_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "module_id",
            sa.Integer(),
            nullable=False,
            comment="대량 수집 모듈 ID",
        ),
        sa.Column(
            "blog_domain",
            sa.String(length=200),
            nullable=False,
            comment="블로그 도메인",
        ),
        sa.Column(
            "last_seen_lastmod",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="마지막 처리한 sitemap entry lastmod",
        ),
        sa.Column(
            "last_cycle_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="가장 최근 사이클 종료 시각",
        ),
        sa.Column(
            "last_cycle_duration_sec",
            sa.Integer(),
            nullable=True,
            comment="가장 최근 사이클 소요 시간(초)",
        ),
        sa.Column(
            "last_cycle_processed",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="가장 최근 사이클 처리 성공 건수",
        ),
        sa.Column(
            "last_cycle_failed",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="가장 최근 사이클 실패 건수",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["module_id"], ["modules.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "module_id",
            "blog_domain",
            name="uq_bulk_collect_progress_module_domain",
        ),
        comment="대량 수집 모듈별·도메인별 진행 상태",
    )
    op.create_index(
        "ix_bulk_collect_progress_module_id",
        "bulk_collect_progress",
        ["module_id"],
        unique=False,
    )
    op.create_index(
        "ix_bulk_collect_progress_blog_domain",
        "bulk_collect_progress",
        ["blog_domain"],
        unique=False,
    )


def downgrade() -> None:
    """Phase A-041 downgrade — 추가한 것 모두 역순 정리.

    주의: bulk_collect 모듈 타입을 사용 중인 modules 가 있다면 FK 위반이
    발생할 수 있다. 그 경우 운영자가 먼저 모듈을 비활성/삭제해야 한다.
    """
    # 3) bulk_collect_progress 테이블 제거
    op.drop_index(
        "ix_bulk_collect_progress_blog_domain",
        table_name="bulk_collect_progress",
    )
    op.drop_index(
        "ix_bulk_collect_progress_module_id",
        table_name="bulk_collect_progress",
    )
    op.drop_table("bulk_collect_progress")

    # 2) collected_urls 인덱스 / 컬럼 제거
    op.drop_index(
        "ix_collected_urls_title_pending",
        table_name="collected_urls",
    )
    op.drop_column("collected_urls", "title_fetch_status")
    op.drop_column("collected_urls", "title_fetched_at")
    op.drop_column("collected_urls", "title")

    # 1) module_types row 삭제
    op.execute(
        "DELETE FROM module_types WHERE code = 'bulk_collect'"
    )
