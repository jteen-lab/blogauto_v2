"""니치 도메인 — 이 니치에서 이미 상위에 있는 블로그/사이트.

`collected_urls` 는 URL 을 12만 건 쌓았지만 소비하는 코드가 없었다.
개별 URL 은 재고로서 가치가 없다. 가치는 **"이 니치에서 누가 상위에
있는가"** 라는 도메인 단위 정보에 있다.

그래서 URL 을 도메인으로 요약하고 원본은 버린다. 데이터량 1/400,
정보는 보존. 남은 것은 각도 조회(`title_gen/angles.py`)가 조회 대상을
좁히는 데 쓴다 — 니치 밖 도메인의 제목은 각도로 삼지 않는다.

계획서: docs/plans/title_pipeline_redesign_plan.md §2-3
순서도: docs/flowcharts/title_pipeline.md §4
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..core.database import Base


class NicheDomain(Base):
    """니치에서 관측된 도메인 하나.

    사용자별로 니치가 다르므로 `user_id` 로 나눈다. 같은 도메인이라도
    사용자가 다르면 다른 행이다.
    """

    __tablename__ = "niche_domains"
    __table_args__ = (
        UniqueConstraint("user_id", "domain", name="uq_niche_domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    domain: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
        comment="도메인 (예: example.tistory.com)")
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown",
        comment="플랫폼 (naver|tistory|wordpress|blogger|unknown)")

    # 얼마나 자주 상위에 나타났는가 — 이 니치에서의 존재감
    url_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="이 도메인에서 관측된 URL 수(요약 시점 기준)")

    # 각도 조회의 원재료. 원문 제목을 재고로 쓰지는 않는다.
    sample_titles: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="대표 제목 샘플(줄바꿈 구분) — 각도 추출용")
    top_keywords: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="이 도메인을 찾게 한 검색 키워드(줄바꿈 구분)")

    # 각도 조회에서 뺄 도메인. 스팸·무관 사이트를 사용자가 끈다.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True,
        comment="False 면 각도 조회 대상에서 제외")

    first_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="최초 관측")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="최종 관측")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())

    def titles(self) -> list:
        """대표 제목 목록."""
        return [t for t in (self.sample_titles or "").split("\n") if t.strip()]

    def keywords(self) -> list:
        """대표 키워드 목록."""
        return [k for k in (self.top_keywords or "").split("\n") if k.strip()]
