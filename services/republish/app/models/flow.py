"""
플로우 모델 - 기존 ProfileGroup을 대체

Features:
- 여러 모듈을 하나의 플로우로 묶음
- 실행 순서 관리 가능
- 상태 기반 오토런 관리 (active/inactive/paused)
- is_active 필드를 status 필드로 대체
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class Flow(Base):
    """플로우 - 기존 ProfileGroup 대체"""

    __tablename__ = "flows"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True, comment="사용자 ID")
    name = Column(String(255), nullable=False, comment="플로우 이름")
    description = Column(Text, nullable=True, comment="플로우 설명")

    # 오토런 상태 (기존 is_active 대체)
    status = Column(
        String(20),
        default="inactive",
        nullable=False,
        comment="플로우 상태: active/inactive/paused",
    )

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 관계
    module_links = relationship(
        "FlowModule",
        back_populates="flow",
        cascade="all, delete-orphan",
        order_by="FlowModule.execution_order",
    )
    blog_links = relationship(
        "FlowBlog", back_populates="flow", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """호환성을 위한 속성 - status가 'active'인지 확인"""
        return self.status == "active"

    @property
    def is_paused(self) -> bool:
        """플로우가 일시 정지 상태인지 확인"""
        return self.status == "paused"

    @property
    def is_inactive(self) -> bool:
        """플로우가 비활성 상태인지 확인"""
        return self.status == "inactive"

    def activate(self) -> None:
        """플로우 활성화"""
        self.status = "active"

    def deactivate(self) -> None:
        """플로우 비활성화"""
        self.status = "inactive"

    def pause(self) -> None:
        """플로우 일시 정지"""
        self.status = "paused"

    def get_modules_by_order(self) -> List["Module"]:
        """실행 순서대로 모듈 목록 반환"""
        return [
            link.module
            for link in sorted(self.module_links, key=lambda x: x.execution_order)
        ]

    def get_module_count(self) -> int:
        """연결된 모듈 수"""
        return len(self.module_links)

    def get_blog_count(self) -> int:
        """연결된 블로그 수"""
        return len(self.blog_links)

    @property
    def module_count(self) -> int:
        return len(self.module_links) if self.module_links else 0

    @property
    def blog_count(self) -> int:
        return len(self.blog_links) if self.blog_links else 0

    def __repr__(self) -> str:
        return f"<Flow(id={self.id}, name='{self.name}', status='{self.status}')>"
