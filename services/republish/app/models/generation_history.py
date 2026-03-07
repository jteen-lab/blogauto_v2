"""
생성 이력 메타데이터 모델

설계 문서: generation_module_workplan.md - Phase 1 - 1.2.2
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..core.database import Base

if TYPE_CHECKING:
    from .blog import Blog


class GenerationHistory(Base):
    """생성 이력 메타데이터"""

    __tablename__ = "generation_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 관계 FK
    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_title_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("main_titles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_module_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("modules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    crawling_post_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("crawled_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 생성 결과
    recombined_title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="재조합된 제목",
    )

    # 사용된 AI 모델
    ai_model_title: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="제목 재조합에 사용된 AI 모델",
    )
    ai_model_content: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="글 생성에 사용된 AI 모델",
    )
    ai_model_image: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="이미지 생성에 사용된 AI 모델",
    )
    image_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="생성된 이미지 URL",
    )

    # 통계
    reference_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="수집된 참조자료 수"
    )
    generation_time_seconds: Mapped[int] = mapped_column(
        Integer, default=0, comment="총 생성 소요 시간(초)"
    )
    content_length: Mapped[int] = mapped_column(
        Integer, default=0, comment="생성된 글 길이"
    )

    # 버전 관리
    version: Mapped[int] = mapped_column(
        Integer, default=1, comment="같은 제목의 몇 번째 버전"
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    blog: Mapped["Blog"] = relationship("Blog", back_populates="generation_histories")

    def __repr__(self) -> str:
        """문자열 표현"""
        title_preview = self.recombined_title[:20] if self.recombined_title else "N/A"
        return (
            f"<GenerationHistory(id={self.id}, "
            f"blog_id={self.blog_id}, "
            f"title={title_preview}...)>"
        )
