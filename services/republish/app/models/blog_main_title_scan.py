"""
BlogMainTitleScan: (블로그 × 정식제목) 검토 카드 모델

사용자 디벨롭 B 의 핵심 데이터 구조.

(blog_id, main_title_id) 쌍 단위로 "이 블로그에서 이 정식제목을 검토했나?"
를 기록한다. row 존재 = 검토 완료, row 없음 = 미검토(=그룹3).
matched=True 면 그룹1 (매칭됨), matched=False 면 그룹2 (검토 후 매칭 실패).

블로그/정식제목 삭제 시 CASCADE 로 자동 정리된다.
정식제목 텍스트가 수정되면 그 main_title_id 의 모든 row 를 수동 삭제하여
검토 결과를 무효화한다 (= 모든 블로그에서 그룹3 복귀).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class BlogMainTitleScan(Base):
    """블로그 × 정식제목 검토 카드.

    Attributes:
        blog_id: 블로그 ID (PK, FK CASCADE)
        main_title_id: 정식제목 ID (PK, FK CASCADE)
        matched: 검토 결과 (True=매칭됨/그룹1, False=미매칭/그룹2)
        scanned_at: 검토 시각
    """

    __tablename__ = "blog_main_title_scans"

    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    main_title_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("main_titles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    matched: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<BlogMainTitleScan(blog={self.blog_id}, "
            f"main_title={self.main_title_id}, matched={self.matched})>"
        )
