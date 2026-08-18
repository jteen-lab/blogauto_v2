"""문의 수신함 테이블 추가 (F10 대시보드)

Revision ID: 049
Revises: 048
Create Date: 2026-08-18

목적:
    - Tally 폼 제출을 폴링으로 수집해 저장, blogauto 대시보드에서 확인.
    - submission_id UNIQUE로 중복 저장 방지.

변경 사항:
    1. contact_submissions 테이블 신설.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blog_id", sa.Integer(), nullable=True),
        sa.Column("form_id", sa.String(length=64), nullable=True),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("form_name", sa.String(length=255), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("submission_id", name="uq_contact_submissions_submission_id"),
    )
    op.create_index("ix_contact_submissions_blog_id", "contact_submissions", ["blog_id"])
    op.create_index("ix_contact_submissions_form_id", "contact_submissions", ["form_id"])
    op.create_index("ix_contact_submissions_is_read", "contact_submissions", ["is_read"])
    op.create_index(
        "ix_contact_submissions_blog_read", "contact_submissions", ["blog_id", "is_read"]
    )


def downgrade() -> None:
    op.drop_index("ix_contact_submissions_blog_read", table_name="contact_submissions")
    op.drop_index("ix_contact_submissions_is_read", table_name="contact_submissions")
    op.drop_index("ix_contact_submissions_form_id", table_name="contact_submissions")
    op.drop_index("ix_contact_submissions_blog_id", table_name="contact_submissions")
    op.drop_table("contact_submissions")
