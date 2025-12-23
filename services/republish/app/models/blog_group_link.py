"""
블로그-그룹 연결 모델
- 블로그와 그룹의 다대다 관계
- 블로그에 그룹을 적용하면 그룹 내 모든 프로파일이 적용됨
"""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..core.database import Base


class BlogGroupLink(Base):
    """블로그-그룹 연결"""
    __tablename__ = "blog_group_links"
    
    id = Column(Integer, primary_key=True, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("profile_groups.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    blog = relationship("Blog", back_populates="group_links")
    group = relationship("ProfileGroup", back_populates="blog_links")
    
    # 중복 방지
    __table_args__ = (
        UniqueConstraint('blog_id', 'group_id', name='uq_blog_group'),
    )
    
    def __repr__(self):
        return f"<BlogGroupLink(blog_id={self.blog_id}, group_id={self.group_id})>"
