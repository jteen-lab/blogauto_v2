"""generation_histories에 section_images 컬럼 추가

Revision ID: 025
Revises: 024
Create Date: 2026-03-13

Phase 5 혼용 모드 섹션 이미지 파이프라인을 위해
생성 이력에 섹션별 이미지 정보 JSON 컬럼을 추가합니다.
"""
from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generation_histories",
        sa.Column("section_images", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("generation_histories", "section_images")
