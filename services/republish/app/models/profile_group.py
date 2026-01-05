"""
프로파일 그룹 모델 (레거시)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..core.database import Base


class ProfileGroup(Base):
    __tablename__ = "profile_groups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile_links = relationship(
        "GroupProfileLink", back_populates="group", cascade="all, delete-orphan"
    )
    blog_links = relationship(
        "BlogGroupLink", cascade="all, delete-orphan", overlaps="group"
    )

    def __repr__(self):
        return f"<ProfileGroup(id={self.id}, name='{self.name}')>"


class GroupProfileLink(Base):
    __tablename__ = "group_profile_links"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(
        Integer, ForeignKey("profile_groups.id", ondelete="CASCADE"), nullable=False
    )
    profile_id = Column(
        Integer, ForeignKey("publish_profiles.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("ProfileGroup", back_populates="profile_links")
    profile = relationship("PublishProfile", back_populates="group_links")

    def __repr__(self):
        return f"<GroupProfileLink(group_id={self.group_id}, profile_id={self.profile_id})>"
