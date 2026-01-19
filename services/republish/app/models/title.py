"""
제목 모델 정의
- TitleGroup: 활성 그룹 (유사 제목 묶음)
- MainTitle: 메인 타이틀 (정식 제목)
- TempTitle: 임시 수집 제목
- TitleGroup ↔ MainTitle 순환 참조 처리 (use_alter, post_update)
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, Boolean, DateTime, Text, Float, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from ..core.database import Base

if TYPE_CHECKING:
    from .keyword import KeywordCategory, CollectedKeyword


class TitleGroup(Base):
    """활성 그룹 - 유사한 제목들을 그룹으로 묶어 관리"""
    __tablename__ = "title_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="그룹명")
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    representative_title_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("main_titles.id", use_alter=True, name="fk_title_group_rep"), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, comment="멤버 수")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    titles: Mapped[List["MainTitle"]] = relationship("MainTitle", back_populates="group", foreign_keys="MainTitle.group_id")
    representative_title: Mapped[Optional["MainTitle"]] = relationship(
        "MainTitle", foreign_keys=[representative_title_id], post_update=True)

    def __repr__(self) -> str:
        return f"<TitleGroup(id={self.id}, name='{self.name}')>"

    def update_member_count(self) -> None:
        """멤버 수 업데이트"""
        self.member_count = len(self.titles) if self.titles else 0


class MainTitle(Base):
    """
    메인 타이틀 (정식 제목)
    상태: available(사용가능) | matched(매칭됨) | used(사용됨) | archived(보관)
    """
    __tablename__ = "main_titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="제목")
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("keyword_categories.id"), nullable=True)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("title_groups.id"), nullable=True)
    is_group_representative: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="available")
    # 매칭/사용 정보
    matched_blog_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="매칭 블로그 IDs (JSON)")
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 원본 정보
    source_temp_title_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 관계
    category: Mapped[Optional["KeywordCategory"]] = relationship("KeywordCategory")
    group: Mapped[Optional["TitleGroup"]] = relationship("TitleGroup", back_populates="titles", foreign_keys=[group_id])

    __table_args__ = (Index('ix_main_title_status_category', 'status', 'category_id'),)

    def __repr__(self) -> str:
        return f"<MainTitle(id={self.id}, title='{self.title[:30]}...')>"

    def mark_used(self) -> None:
        """사용 기록 업데이트"""
        self.use_count += 1
        self.last_used_at = datetime.now()
        if self.status == "available":
            self.status = "used"


class TempTitle(Base):
    """
    임시 수집 제목 - 크롤링으로 수집된 원본 제목
    수집단계: keyword_search | blog_crawl
    상태: new | filtered | categorized | moved | duplicate
    """
    __tablename__ = "temp_titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="제목")
    # 수집 정보
    source_keyword_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("collected_keywords.id"), nullable=True)
    source_blog_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_post_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    collection_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="new")
    # 필터링 정보
    filter_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    filter_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="필터 키워드 (JSON)")
    # 카테고리 정보 (KeywordCategory)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("keyword_categories.id"), nullable=True)
    category_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 카테고리 관리 연동 (Topic > SubTopic > Keyword)
    topic_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("topics.id"), nullable=True, comment="주제 ID")
    subtopic_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subtopics.id"), nullable=True, comment="하위 주제 ID")
    matched_keyword_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("keywords.id"), nullable=True, comment="매칭된 카테고리 키워드 ID")
    # 유사도 매칭 정보
    similar_title_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 이동 정보
    moved_to_main_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    moved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 관계
    source_keyword: Mapped[Optional["CollectedKeyword"]] = relationship("CollectedKeyword")
    category: Mapped[Optional["KeywordCategory"]] = relationship("KeywordCategory")

    __table_args__ = (
        Index('ix_temp_title_status', 'status'),
        Index('ix_temp_title_collection_stage', 'collection_stage'),
    )

    def __repr__(self) -> str:
        return f"<TempTitle(id={self.id}, title='{self.title[:30]}...')>"

    def mark_filtered(self, reason: str) -> None:
        """필터링 처리"""
        self.status = "filtered"
        self.filter_reason = reason
        self.processed_at = datetime.now()

    def mark_moved(self, main_title_id: int) -> None:
        """메인 타이틀로 이동 처리"""
        self.status = "moved"
        self.moved_to_main_id = main_title_id
        self.moved_at = datetime.now()
        self.processed_at = datetime.now()
