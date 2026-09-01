"""키워드 지표 — **엔진별**로 따로 잰다.

`keyword_candidates` 는 검색량·문서수 컬럼을 엔진 구분 없이 한 벌만 갖고
있었다. 네이버만 볼 때는 문제가 없지만, 우리가 글을 내보내는 곳은
워드프레스·블로거(주로 구글 색인)다. 구글 지표를 더하는 순간 같은 칸을
두 엔진이 다투게 된다.

그래서 지표를 1:N 으로 뗀다. 후보 한 줄에 엔진마다 지표 한 줄.

**공급 지표가 바뀐 점**: 누적 문서수(doc_count)가 아니라 **최근 30일
발행량**(monthly_pub_count)을 본다. 누적은 10년치 총합이라 "지금 경쟁이
붙고 있는지" 를 말해 주지 않는다. 국내 도구(블랙키위 등)가 쓰는 축도 이쪽이다.

계획서: docs/plans/keyword_module_redesign_plan.md
"""
from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.sql import func

from ..core.database import Base

# 지표를 잰 검색 엔진
ENGINE_NAVER = "naver"
ENGINE_GOOGLE = "google"
ENGINES = (ENGINE_NAVER, ENGINE_GOOGLE)

# 화면·판정의 기본 엔진. 블로그별 타깃 엔진이 생기기 전까지의 기본값이다.
PRIMARY_ENGINE = ENGINE_NAVER


class KeywordMetric(Base):
    """키워드 하나의 **한 엔진** 지표."""

    __tablename__ = "keyword_metrics"
    __table_args__ = (
        UniqueConstraint("candidate_id", "engine", name="uq_keyword_metric"),
    )

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(
        Integer, ForeignKey("keyword_candidates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    engine = Column(String(20), nullable=False, index=True,
                    comment="naver | google")

    # ── 수요 ─────────────────────────────────────────────
    search_volume_pc = Column(Integer, nullable=True)
    search_volume_mobile = Column(Integer, nullable=True)
    search_volume = Column(Integer, nullable=True, index=True)
    # 구글 Keyword Planner 는 구간값을 준다(1천~1만). 절대 기준으로 쓰면
    # 안 되므로 어느 정도 신뢰할 수 있는 값인지 남긴다.
    volume_is_range = Column(Integer, nullable=True,
                             comment="1이면 구간값(절대 기준으로 쓰지 말 것)")
    competition = Column(String(10), nullable=True)

    # ── 공급 ─────────────────────────────────────────────
    doc_count = Column(Integer, nullable=True, comment="누적 문서수(참고용)")
    monthly_pub_count = Column(Integer, nullable=True,
                               comment="최근 30일 발행량(경쟁 판정의 기준)")
    # 발행량 표본이 상한에 닿았는지. 100건을 세어 100이 나오면 실제로는
    # 그 이상이라는 뜻이라 '≥100' 으로 읽어야 한다.
    pub_count_capped = Column(Integer, nullable=True)

    # 포화도 = 검색량 ÷ 공급. 클수록 비집고 들어갈 자리가 있다.
    saturation = Column(Float, nullable=True, index=True)

    measured_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<KeywordMetric #{self.candidate_id} {self.engine} "
                f"vol={self.search_volume} pub={self.monthly_pub_count}>")
