"""문의 수신함 — Tally 폼 제출 저장 (F10 대시보드).

Tally 폼 제출을 폴링/webhook으로 수집해 저장하고, blogauto 대시보드에서 확인한다.
submission_id UNIQUE로 중복 저장을 방지한다.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..core.database import Base


class ContactSubmission(Base):
    """Tally 문의 폼 제출 1건."""

    __tablename__ = "contact_submissions"

    id = Column(Integer, primary_key=True)
    blog_id = Column(
        Integer, ForeignKey("blogs.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="제출이 속한 블로그(폼 매핑, 삭제 시 NULL)",
    )
    form_id = Column(String(64), nullable=True, index=True, comment="Tally form id")
    submission_id = Column(
        String(64), unique=True, nullable=False, comment="Tally 제출 id(중복 방지)",
    )
    form_name = Column(String(255), nullable=True)
    submitted_at = Column(DateTime, nullable=True, comment="제출 시각")
    # [{"label": str, "value": str}] — 가변 필드(모듈 템플릿별 상이)
    fields = Column(JSONB, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    blog = relationship("Blog", backref="contact_submissions")

    __table_args__ = (
        Index("ix_contact_submissions_blog_read", "blog_id", "is_read"),
    )

    def __repr__(self) -> str:
        return f"<ContactSubmission(id={self.id}, form_id={self.form_id})>"
