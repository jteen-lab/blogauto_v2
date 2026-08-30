"""AI 모델 카탈로그 테이블 추가

Revision ID: 054
Revises: 053
Create Date: 2026-08-30

목적:
    모델 목록이 11개 파일에 하드코딩돼 있어 제공자가 모델을 내려도 죽은
    선택지가 그대로 남았다(구글 선택지 10개 중 5개가 이미 없는 모델이었고,
    그중 하나는 '추천' 배지까지 붙어 있었다). 목록을 DB 한 곳으로 모은다.

    요금은 어느 제공자도 API 로 주지 않아 별도 테이블에 수동 관리한다.

주의:
    create_all 로 이미 테이블이 만들어진 환경이 있을 수 있어 존재 여부를
    확인하고 만든다(051 에서 겪은 문제).
"""
import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    if not _has_table("ai_models"):
        op.create_table(
            "ai_models",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("model_id", sa.String(length=200), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=True),
            sa.Column("capability", sa.String(length=20),
                      server_default="text", nullable=False),
            sa.Column("is_available", sa.Boolean(),
                      server_default=sa.true(), nullable=False),
            sa.Column("shutdown_date", sa.String(length=40), nullable=True),
            sa.Column("tier", sa.String(length=20), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "model_id", name="uq_ai_model"),
        )
        op.create_index("ix_ai_models_id", "ai_models", ["id"])
        op.create_index("ix_ai_models_provider", "ai_models", ["provider"])
        op.create_index("ix_ai_models_is_available", "ai_models",
                        ["is_available"])
        op.create_index("ix_ai_models_provider_cap", "ai_models",
                        ["provider", "capability"])

    if not _has_table("ai_model_prices"):
        op.create_table(
            "ai_model_prices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("model_id", sa.String(length=200), nullable=False),
            sa.Column("input_per_1m", sa.Float(), nullable=True),
            sa.Column("output_per_1m", sa.Float(), nullable=True),
            sa.Column("cached_input_per_1m", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(length=10),
                      server_default="USD", nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "model_id",
                                name="uq_ai_model_price"),
        )
        op.create_index("ix_ai_model_prices_id", "ai_model_prices", ["id"])
        op.create_index("ix_ai_model_prices_provider", "ai_model_prices",
                        ["provider"])


    _seed_prices()


def _seed_prices() -> None:
    """요금 기본값을 넣는다(이미 있는 것은 건드리지 않는다).

    요금은 사용자가 관리 화면에서 고칠 수 있어야 하므로, 재실행 시 사용자가
    수정한 값을 덮어쓰지 않도록 없는 것만 넣는다.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.services.ai.model_prices import SEED

    bind = op.get_bind()
    existing = {
        (r[0], r[1]) for r in bind.execute(
            sa.text("SELECT provider, model_id FROM ai_model_prices")
        )
    }
    rows = [s for s in SEED if (s["provider"], s["model_id"]) not in existing]
    if not rows:
        return
    for s in rows:
        bind.execute(
            sa.text(
                "INSERT INTO ai_model_prices "
                "(provider, model_id, input_per_1m, output_per_1m, "
                " cached_input_per_1m, currency, note) VALUES "
                "(:p, :m, :i, :o, :c, 'USD', :n)"
            ),
            {"p": s["provider"], "m": s["model_id"],
             "i": s.get("input_per_1m"), "o": s.get("output_per_1m"),
             "c": s.get("cached_input_per_1m"), "n": s.get("note")},
        )


def downgrade() -> None:
    for name in ("ai_model_prices", "ai_models"):
        if _has_table(name):
            op.drop_table(name)
