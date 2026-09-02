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
    # 유일성은 **블로그별**이다. 사용자 전역으로 걸면 1번 블로그가 먼저 잡은
    # 키워드를 나머지 블로그가 영원히 재수집하지 못한다(검토서 D-6).
    __table_args__ = (
        UniqueConstraint("user_id", "blog_id", "keyword",
                         name="uq_keyword_candidate_blog"),
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
    doc_count = Column(Integer, nullable=True)      # 누적 문서수(참고용)
    # 최근 30일 발행량. 경쟁 판정의 기준은 이쪽이다 — 누적 문서수는 10년치
    # 총합이라 "지금 경쟁이 붙고 있는지" 를 말해 주지 않는다.
    # 엔진별 상세는 keyword_metrics 에 있고 여기는 기본 엔진 미러다.
    monthly_pub_count = Column(Integer, nullable=True)
    # 포화도 = 검색량 ÷ 문서수. 클수록 비집고 들어갈 자리가 있다.
    saturation = Column(Float, nullable=True, index=True)

    # ── 판정 ─────────────────────────────────────────────
    verdict = Column(String(10), nullable=False, default=VERDICT_PENDING,
                     index=True)
    verdict_reason = Column(String(120), nullable=True)
    # 확인 불가 정보가 핵심인 유형(고객센터·시간표·채용조건 등).
    # 막지 않고 표시만 한다 — 같은 말이 들어가도 정상 글일 수 있다.
    risk_label = Column(String(40), nullable=True)

    # 소속 클러스터. 생산 단위는 키워드가 아니라 묶음이다.
    cluster_id = Column(Integer, nullable=True, index=True)
    # 검색 의도. 같은 주제라도 묻는 것이 다르면 다른 글이다.
    intent = Column(String(20), nullable=True, index=True)
    # 분류를 시도한 시각. **실패한 것도 기록한다** — 분류기는 결정적이라
    # 안 붙은 것을 다시 훑어도 결과가 같다. 이 값이 없어 같은 2,000건을
    # 반복해서 훑고 진행이 없었다.
    classify_tried_at = Column(DateTime(timezone=True), nullable=True,
                               index=True)

    source = Column(String(30), nullable=False, default="naver_ads")

    # ── 운영 상태 (seed_keywords 에서 승계) ──────────────
    # 이 테이블이 데이터 관리 키워드 탭의 정본이 되면서, 순환 사용·활성
    # 여부 같은 운영 정보도 여기로 온다.
    is_active = Column(Boolean, nullable=False, default=True)
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    # 이관 추적용. 어디서 온 키워드인지 남아야 되돌릴 수 있다.
    legacy_seed_id = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)

    # ── 성과 되먹임 ──────────────────────────────────────
    # 발행 후 실제로 노출됐는지. 잘 되는 축은 시드 우선순위를 올리고
    # 계속 노출이 없는 축은 내린다. 아직 안 재면 NULL.
    perf_score = Column(Float, nullable=True, index=True)
    perf_checked_at = Column(DateTime(timezone=True), nullable=True)

    measured_at = Column(DateTime(timezone=True), nullable=True)
    # promoted 와 titled 는 뜻이 다르다. 한 칸을 겸용하면 시드로 소비된
    # 상위 키워드가 제목 대상에서 빠진다(검토서 D-4).
    promoted = Column(Boolean, nullable=False, default=False,
                      comment="시드로 이미 쓴 키워드인지")
    titled = Column(Boolean, nullable=False, default=False,
                    comment="제목을 이미 만든 키워드인지")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (f"<KeywordCandidate {self.keyword} "
                f"vol={self.search_volume} verdict={self.verdict}>")
