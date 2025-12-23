"""
프로파일 그룹 모델
- 여러 프로파일을 하나의 그룹으로 묶음
- 블로그에 그룹을 적용하면 그룹 내 모든 프로파일이 적용됨
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..core.database import Base


class ProfileGroup(Base):
    """프로파일 그룹"""
    __tablename__ = "profile_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="profile_groups")
    profile_links = relationship("GroupProfileLink", back_populates="group", cascade="all, delete-orphan")
    blog_links = relationship("BlogGroupLink", back_populates="group", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ProfileGroup(id={self.id}, name='{self.name}')>"
