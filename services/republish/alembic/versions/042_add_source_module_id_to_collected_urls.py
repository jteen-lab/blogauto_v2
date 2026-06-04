"""Phase B-042: collected_urls.source_module_id 추가 + UNIQUE 재정의

Revision ID: 042
Revises: 041
Create Date: 2026-06-02

목적 (대량 수집 모듈 분리 Phase B 핫픽스 W2):
    bulk_collect 모듈을 다수 운영할 때 모듈별 URL 풀을 격리하기 위해
    `collected_urls` 테이블에 `source_module_id` 컬럼을 도입한다.

변경 사항:
    1. `collected_urls.source_module_id` 추가
        - Integer, FK → modules.id (ON DELETE SET NULL)
        - nullable=True (레거시 row 는 NULL)
        - 단일 인덱스
    2. 기존 UNIQUE `uq_collected_url_domain` 제거
        - 도메인 1개당 1 row 제약은 모듈 단위 격리와 충돌
        - 도메인 검색은 기존 `domain` 컬럼 단일 인덱스로 대체
    3. 신규 UNIQUE `uq_collected_url_url_module` 추가
        - (url, source_module_id) 조합
        - URL 단위 격리: 같은 URL이라도 모듈이 다르면 별도 row
        - NULL 끼리는 NULLS DISTINCT(기본) → 레거시 중복 허용
    4. `(source_module_id, title_fetch_status)` 복합 인덱스 추가
        - 청크 SELECT 성능 보강

데이터 보존:
    - 기존 row 의 `source_module_id` 는 NULL 로 자동 채워짐 (server_default 불필요)
    - downgrade 시 도메인 단위 UNIQUE 복원이 실패할 수 있음
      (이미 같은 도메인의 row 가 여러 개 존재할 수 있기 때문) → 운영자 수동 정리 필요
"""
import logging

import sqlalchemy as sa
from alembic import op


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Phase B-042 upgrade.

    트랜잭션 안에서 UNIQUE 교체 + 컬럼 추가 일괄 처리.
    alembic 의 op.* 는 기본적으로 한 트랜잭션 안에서 실행되므로 중간 실패 시 롤백 안전.
    """
    # ─────────────────────────────────────────────
    # 1) source_module_id 컬럼 추가 (nullable, FK SET NULL)
    # ─────────────────────────────────────────────
    op.add_column(
        "collected_urls",
        sa.Column(
            "source_module_id",
            sa.Integer(),
            nullable=True,
            comment="URL을 적재한 모듈 ID (NULL=레거시/일반 collect 모듈)",
        ),
    )
    op.create_foreign_key(
        "fk_collected_urls_source_module_id_modules",
        "collected_urls",
        "modules",
        ["source_module_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_collected_urls_source_module_id",
        "collected_urls",
        ["source_module_id"],
        unique=False,
    )

    # ─────────────────────────────────────────────
    # 2) 기존 UNIQUE (domain) 제거
    # ─────────────────────────────────────────────
    # PostgreSQL/SQLite 양쪽에서 동작하도록 try-안전 처리
    try:
        op.drop_constraint(
            "uq_collected_url_domain",
            "collected_urls",
            type_="unique",
        )
        logger.info("[042] uq_collected_url_domain 제거 완료")
    except Exception as exc:  # noqa: BLE001
        # SQLite 는 명명된 unique 제약 drop 시 batch_alter_table 이 필요할 수 있음
        logger.warning(
            "[042] uq_collected_url_domain drop 실패(이미 제거됐을 수 있음): %s",
            exc,
        )

    # ─────────────────────────────────────────────
    # 3) 신규 UNIQUE (url, source_module_id) 추가
    # ─────────────────────────────────────────────
    op.create_unique_constraint(
        "uq_collected_url_url_module",
        "collected_urls",
        ["url", "source_module_id"],
    )

    # ─────────────────────────────────────────────
    # 4) (source_module_id, title_fetch_status) 복합 인덱스
    #    → 청크 SELECT(모듈별 pending 로딩) 성능 보강
    # ─────────────────────────────────────────────
    op.create_index(
        "ix_collected_urls_source_module_status",
        "collected_urls",
        ["source_module_id", "title_fetch_status"],
        unique=False,
    )


def downgrade() -> None:
    """Phase B-042 downgrade.

    주의: 도메인 단위 UNIQUE 복원은 다음 조건에서만 가능.
        - 모든 (domain) 조합이 유일해야 함.
        - 그렇지 않으면 IntegrityError → 운영자가 사전에 중복 row 를 정리해야 함.
    """
    # 4) 복합 인덱스 제거
    op.drop_index(
        "ix_collected_urls_source_module_status",
        table_name="collected_urls",
    )

    # 3) 신규 UNIQUE 제거
    op.drop_constraint(
        "uq_collected_url_url_module",
        "collected_urls",
        type_="unique",
    )

    # 2) 기존 도메인 UNIQUE 복원 (실패 가능성 있음)
    try:
        op.create_unique_constraint(
            "uq_collected_url_domain",
            "collected_urls",
            ["domain"],
        )
        logger.info("[042 downgrade] uq_collected_url_domain 복원 완료")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[042 downgrade] uq_collected_url_domain 복원 실패 - 중복 도메인 존재 가능: %s",
            exc,
        )

    # 1) source_module_id 컬럼 / FK / 인덱스 제거
    op.drop_index(
        "ix_collected_urls_source_module_id",
        table_name="collected_urls",
    )
    op.drop_constraint(
        "fk_collected_urls_source_module_id_modules",
        "collected_urls",
        type_="foreignkey",
    )
    op.drop_column("collected_urls", "source_module_id")
