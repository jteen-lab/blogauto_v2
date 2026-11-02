"""제목 D 방식 거르기의 기억 — 버린 제목 지문과 출처 사이트 점수.

- TitleFingerprint: 떨어진 임시 제목은 지우고 공백 뺀 제목만 남긴다. 같은 제목이
  다른 사이트·다음 대량 수집에서 다시 들어오면 0원 규칙 단계에서 바로 버린다.
- TitleSiteScore: 출처 사이트마다 본 수·통과 수. 20개 이상 보고 통과율 10% 미만이면
  차단(90일 뒤 다시 확인), 30% 이상이면 우선(사이트 통째 훑기 허용).

순서도: docs/flowcharts/title_screen_d.md
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..core.database import Base

SITE_NORMAL = "normal"
SITE_BLOCKED = "blocked"
SITE_PRIORITY = "priority"


class TitleFingerprint(Base):
    """버린 제목 하나의 지문."""

    __tablename__ = "title_fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(500), nullable=False, unique=True,
                                             comment="공백 뺀 소문자 제목")
    reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True,
                                                  comment="버린 이유(규칙 이름·low_volume 등)")
    site: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class TitleSiteScore(Base):
    """출처 사이트 점수(통과율)."""

    __tablename__ = "title_site_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site: Mapped[str] = mapped_column(String(255), nullable=False, unique=True,
                                      comment="호스트(네이버 블로그·카페는 호스트/아이디)")
    seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SITE_NORMAL,
                                        server_default=SITE_NORMAL, index=True)
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    recheck_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), onupdate=func.now())

    @property
    def rate(self) -> float:
        """통과율(0~1). 본 것이 없으면 0."""
        return (self.passed or 0) / self.seen if self.seen else 0.0
