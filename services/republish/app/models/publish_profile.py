"""
발행 프로파일 모델 (레거시)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..core.database import Base


class PublishProfile(Base):
    __tablename__ = "publish_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    schedule_matrix = Column(Text, nullable=True)
    interval_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    group_links = relationship(
        "GroupProfileLink", back_populates="profile", cascade="all, delete-orphan"
    )

    @property
    def calculated_interval_minutes(self) -> int:
        return self.interval_minutes or 60

    def __repr__(self):
        return f"<PublishProfile(id={self.id}, name='{self.name}')>"
