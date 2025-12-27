"""
플로우-블로그 연결 모델 - 기존 BlogGroupLink 대체

Features:
- 플로우와 블로그의 다대다 관계
- 블로그에 플로우를 적용하면 플로우 내 모든 모듈이 적용됨
- CASCADE DELETE 지원
"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class FlowBlog(Base):
    """플로우-블로그 연결"""
    __tablename__ = "flow_blogs"

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(
        Integer,
        ForeignKey("flows.id", ondelete="CASCADE"),
        nullable=False,
        comment="플로우 ID"
    )
    blog_id = Column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        comment="블로그 ID"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계
    flow = relationship("Flow", back_populates="blog_links")
    blog = relationship("Blog", back_populates="flow_links")

    # 제약조건
    __table_args__ = (
        UniqueConstraint("flow_id", "blog_id", name="uq_flow_blog"),
    )

    def __repr__(self) -> str:
        return (
            f"<FlowBlog(flow_id={self.flow_id}, "
            f"blog_id={self.blog_id})>"
        )