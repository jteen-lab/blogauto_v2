"""
포스트 모델

Features:
- 포스트 상태 관리 (collected → processed → generated → pending → published)
- 발행/재발행 추적
- 원격 플랫폼 ID 관리
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from ..core.database import Base


class Post(Base):
    """포스트"""
    __tablename__ = "posts"

    # 기본 필드
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("topics.id"), nullable=True, index=True)

    # 콘텐츠
    title = Column(String(200), nullable=False, comment="제목")
    content = Column(Text, nullable=False, comment="본문 (HTML/Markdown)")
    excerpt = Column(Text, nullable=True, comment="요약")

    # 상태 관리
    status = Column(
        String(20),
        default="collected",
        comment="상태: collected/processed/generated/pending/published/republished",
        index=True
    )

    # 원격 정보
    remote_id = Column(String(50), nullable=True, comment="플랫폼의 포스트 ID")
    remote_url = Column(String(500), nullable=True, comment="발행된 URL")

    # 발행 추적
    published_at = Column(DateTime(timezone=True), nullable=True, comment="최초 발행 시간")
    last_republished_at = Column(DateTime(timezone=True), nullable=True, comment="마지막 재발행 시간")
    republish_count = Column(Integer, default=0, comment="재발행 횟수")

    # 메타
    is_deleted = Column(Boolean, default=False, comment="소프트 삭제")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    user = relationship("User")
    blog = relationship("Blog")
    category = relationship("Topic")
    publish_logs = relationship("PublishLog", back_populates="post")

    @property
    def is_published(self) -> bool:
        """발행 완료 여부"""
        return self.status in ["published", "republished"]

    @property
    def can_be_republished(self) -> bool:
        """재발행 가능 여부"""
        return self.is_published and self.remote_id is not None

    def mark_as_published(self, remote_id: str, remote_url: str = None) -> None:
        """발행 완료 처리"""
        self.status = "published"
        self.remote_id = remote_id
        self.remote_url = remote_url
        self.published_at = datetime.utcnow()

    def mark_as_republished(self) -> None:
        """재발행 완료 처리"""
        self.status = "republished"
        self.last_republished_at = datetime.utcnow()
        self.republish_count += 1

    def transition_to(self, new_status: str) -> bool:
        """상태 전이"""
        valid_transitions = {
            "collected": ["processed"],
            "processed": ["generated"],
            "generated": ["pending"],
            "pending": ["published"],
            "published": ["republished"],
            "republished": ["republished"]  # 재발행은 반복 가능
        }

        if new_status in valid_transitions.get(self.status, []):
            self.status = new_status
            return True
        return False

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, title='{self.title[:50]}...', status={self.status})>"