"""
플로우-모듈 연결 모델 - 기존 GroupProfileLink 대체

Features:
- 플로우와 모듈의 다대다 관계
- 실행 순서 관리 (execution_order)
- CASCADE DELETE 지원
"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class FlowModule(Base):
    """플로우-모듈 연결"""
    __tablename__ = "flow_modules"

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(
        Integer,
        ForeignKey("flows.id", ondelete="CASCADE"),
        nullable=False,
        comment="플로우 ID"
    )
    module_id = Column(
        Integer,
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        comment="모듈 ID"
    )
    execution_order = Column(
        Integer,
        default=0,
        nullable=False,
        comment="실행 순서 (0부터 시작)"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계
    flow = relationship("Flow", back_populates="module_links")
    module = relationship("Module", back_populates="flow_links")

    # 제약조건
    __table_args__ = (
        UniqueConstraint("flow_id", "module_id", name="uq_flow_module"),
    )

    def __repr__(self) -> str:
        return (
            f"<FlowModule(flow_id={self.flow_id}, "
            f"module_id={self.module_id}, order={self.execution_order})>"
        )