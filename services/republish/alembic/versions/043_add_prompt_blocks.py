"""043: 프롬프트 빌더 옵션 블록 DB화 — prompt_blocks 테이블

Revision ID: 043
Revises: 042
Create Date: 2026-06-06

목적:
    프롬프트 빌더의 4축 옵션(페르소나·독자수준·섹션패턴·시작톤)을 코드 하드코딩
    (`services/prompt_builder/blocks.py`)에서 DB로 옮겨, 운영자가 옵션을 영구적으로
    추가·수정할 수 있게 하는 기반 테이블을 만든다.

    - 본 마이그레이션은 빈 테이블만 생성한다.
    - 기본 제공 블록 시드는 앱 레벨에서 멱등 시드(ensure_seeded)로 채운다
      (마이그레이션이 app 코드를 import 하지 않도록 분리).
"""
import sqlalchemy as sa
from alembic import op


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """prompt_blocks 테이블 생성."""
    op.create_table(
        "prompt_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "block_type", sa.String(length=20), nullable=False,
            comment="블록 축: persona|reader|pattern|tone",
        ),
        sa.Column(
            "code", sa.String(length=50), nullable=False,
            comment="축 내 고유 코드",
        ),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cluster", sa.String(length=20), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), server_default="0", nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "is_builtin", sa.Boolean(), server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "block_type", "code", name="uq_prompt_block_type_code",
        ),
        comment="프롬프트 빌더 옵션 블록",
    )
    op.create_index(
        "ix_prompt_blocks_block_type", "prompt_blocks", ["block_type"],
    )
    op.create_index(
        "ix_prompt_blocks_is_active", "prompt_blocks", ["is_active"],
    )
    op.create_index(
        "ix_prompt_blocks_type_active",
        "prompt_blocks", ["block_type", "is_active"],
    )


def downgrade() -> None:
    """prompt_blocks 테이블 제거."""
    op.drop_index("ix_prompt_blocks_type_active", table_name="prompt_blocks")
    op.drop_index("ix_prompt_blocks_is_active", table_name="prompt_blocks")
    op.drop_index("ix_prompt_blocks_block_type", table_name="prompt_blocks")
    op.drop_table("prompt_blocks")
