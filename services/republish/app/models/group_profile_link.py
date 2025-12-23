"""
그룹-프로파일 연결 모델
- 그룹과 프로파일의 다대다 관계
"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..core.database import Base


class GroupProfileLink(Base):
    """그룹-프로파일 연결"""
    __tablename__ = "group_profile_links"
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("profile_groups.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(Integer, ForeignKey("publish_profiles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    group = relationship("ProfileGroup", back_populates="profile_links")
    profile = relationship("PublishProfile", back_populates="group_links")
    
    # 중복 방지
    __table_args__ = (
        UniqueConstraint('group_id', 'profile_id', name='uq_group_profile'),
    )
    
    def __repr__(self):
        return f"<GroupProfileLink(group_id={self.group_id}, profile_id={self.profile_id})>"
