"""키워드 후보 — 수요를 먼저 재고 만든 수집 후보.

기존 `seed_keywords` 를 건드리지 않는다. 운영 중인 12개 블로그가 그 위에서
돌고 있어, 검증 안 된 방식을 섞으면 무엇이 원인인지 가릴 수 없다.

**나중에 seed_keywords 를 대체할 수 있는 모양으로 잡는다.** 그쪽에는
검색량 컬럼이 아예 없어서, 지금 승격해도 측정값이 사라진다.

순서도: docs/flowcharts/keyword_lab.md
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..core.database import Base

# 판정값
VERDICT_PENDING = "pending"      # 아직 문서수를 재지 않음
VERDICT_ADOPT = "adopt"          # 채택
VERDICT_HOLD = "hold"            # 보류 — 사람이 봐야 함(위험 유형)
VERDICT_REJECT = "reject"        # 제외


class KeywordCandidate(Base):
    """수요 지표를 함께 들고 있는 키워드 후보."""

    __tablename__ = "keyword_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_keyword_candidate"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    keyword = Column(String(200), nullable=False, index=True)
    # 어느 시드에서 나왔는지. 시드 자체도 후보로 들어온다(자기 자신이 시드).
    seed = Column(String(200), nullable=True)

    # 어느 블로그의 니치로 모았는지. 나중에 블로그별 재고 계산에 쓴다.
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=True, index=True)
    topic_id = Column(Integer, nullable=True, index=True)
    subtopic_id = Column(Integer, nullable=True, index=True)

    # ── 수요 지표 ────────────────────────────────────────
    search_volume_pc = Column(Integer, nullable=True)
    search_volume_mobile = Column(Integer, nullable=True)
    search_volume = Column(Integer, nullable=True, index=True)   # 합계
    competition = Column(String(10), nullable=True)              # 낮음/중간/높음

    # ── 공급 지표 ────────────────────────────────────────
    doc_count = Column(Integer, nullable=True)      # 네이버 블로그 문서수
    # 포화도 = 검색량 ÷ 문서수. 클수록 비집고 들어갈 자리가 있다.
    saturation = Column(Float, nullable=True, index=True)

    # ── 판정 ─────────────────────────────────────────────
    verdict = Column(String(10), nullable=False, default=VERDICT_PENDING,
                     index=True)
    verdict_reason = Column(String(120), nullable=True)
    # 확인 불가 정보가 핵심인 유형(고객센터·시간표·채용조건 등).
    # 막지 않고 표시만 한다 — 같은 말이 들어가도 정상 글일 수 있다.
    risk_label = Column(String(40), nullable=True)

    source = Column(String(30), nullable=False, default="naver_ads")
    note = Column(Text, nullable=True)

    measured_at = Column(DateTime(timezone=True), nullable=True)
    promoted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<KeywordCandidate {self.keyword} "
                f"vol={self.search_volume} verdict={self.verdict}>")
