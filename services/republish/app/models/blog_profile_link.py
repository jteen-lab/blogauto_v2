"""
블로그-프로파일 연동 모델

Features:
- 블로그별 다중 프로파일 연동
- 스케줄 추적 및 상태 관리
- 실행 통계 추적
"""

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class BlogProfileLink(Base):
    """블로그-프로파일 연동"""
    __tablename__ = "blog_profile_links"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("publish_profiles.id"), nullable=False, index=True)

    # 상태 관리
    is_active = Column(Boolean, default=True, comment="활성/비활성 상태")

    # 스케줄 추적
    last_executed_at = Column(DateTime(timezone=True), nullable=True, comment="마지막 실행 시간")
    next_scheduled_at = Column(DateTime(timezone=True), nullable=True, comment="다음 예정 시간")
    last_post_id = Column(Integer, nullable=True, comment="마지막 재발행 포스트 ID")

    # 실행 통계
    total_executions = Column(Integer, default=0, comment="총 실행 횟수")
    success_count = Column(Integer, default=0, comment="성공 횟수")
    fail_count = Column(Integer, default=0, comment="실패 횟수")

    # 메타
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    blog = relationship("Blog", back_populates="profile_links")
    profile = relationship("PublishProfile", back_populates="blog_links")

    # 제약 조건: 블로그-프로파일 조합 유니크
    __table_args__ = (
        UniqueConstraint('blog_id', 'profile_id', name='uq_blog_profile'),
    )

    @property
    def success_rate(self) -> float:
        """성공률 계산"""
        if self.total_executions == 0:
            return 0.0
        return (self.success_count / self.total_executions) * 100

    def record_execution(self, success: bool, post_id: int = None) -> None:
        """실행 결과 기록"""
        self.total_executions += 1
        self.last_executed_at = datetime.utcnow()

        if success:
            self.success_count += 1
            if post_id:
                self.last_post_id = post_id
        else:
            self.fail_count += 1

    def __repr__(self) -> str:
        return f"<BlogProfileLink(blog_id={self.blog_id}, profile_id={self.profile_id}, active={self.is_active})>"