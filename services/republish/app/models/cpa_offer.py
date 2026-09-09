"""CPA 오퍼 — 프로모션 하나의 규칙과 상태.

애드릭스 프로모션 페이지는 로그인해야 열려 크롤이 안 된다(실측 2026-09-08).
사람이 복사한 원문을 받아 저장하고, 거기서 규칙을 뽑는다.

**원문을 반드시 보존한다.** 구조화 결과는 파생물이고, 광고주와 다툼이 생기면
원문이 근거다.

순서도: docs/flowcharts/cpa_offer.md
계획서: docs/plans/cpa_affiliate_plan.md
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, String, Text, func,
)

from ..core.database import Base

# 상태
ST_DRAFT = "draft"        # 등록했으나 확인 전 — 글 생성 불가
ST_ACTIVE = "active"      # 확인 완료 — 글 생성 가능
ST_RECHECK = "recheck"    # 재확인 기한 경과 — 글 생성 중단
ST_STOPPED = "stopped"    # 중단

USABLE = (ST_ACTIVE,)

# 오퍼 조건이 바뀌어도 우리는 알 수 없다. 기한으로만 방어한다.
DEFAULT_RECHECK_DAYS = 30

# 규칙 유형. 실제 오퍼 7건(의료·법률·생활·통신·금융·교육) 80건을 분해해 얻었다.
# 업종이 바뀌어도 유형은 늘지 않는다 — 늘어나는 것은 값이다.
RULE_TYPES = (
    "must_include",      # 반드시 포함할 문구
    "must_not_include",  # 포함 금지 낱말
    "required_topic",    # 반드시 다뤄야 할 내용(문자열 아님)
    "forbidden_topic",   # 다루면 안 되는 주제
    "replace",           # 순화 대체
    "position",          # 문구 위치
    "pattern",           # 정규식 금지
    "format",            # 표기 형식
    "conditional",       # X 언급 시 Y 필수
    "channel",           # 매체 허용·금지
    "asset",             # 지정 자산만
    "link_policy",       # 링크 구성 제약
    "conversion",        # 전환·타겟 조건
    "content_axis",      # 소재 축
    "content_source",    # 사실 원천
    "advisory",          # 기계 검사 불가 — 사람이 본다
)

# 규칙 범위. 모르면 가장 넓게(all) 잡는다.
# 스탁론은 '금리'를 금지키워드로 두면서 본문에 "월 0.4%대"를 쓴다.
# 범위를 구분하지 않으면 광고주가 준 문구를 우리가 차단한다.
RULE_SCOPES = ("title", "keywords", "body", "images", "all")

# 처리 강도. 전부 차단으로 두면 글이 나가지 않는다.
SEV_BLOCK = "block"
SEV_WARN = "warn"
SEV_REVIEW = "review"


class CpaOffer(Base):
    """프로모션 하나."""

    __tablename__ = "cpa_offers"

    id = Column(Integer, primary_key=True)
    network = Column(String(50), nullable=False, default="adlix",
                     comment="제휴 네트워크")
    offer_code = Column(String(50), nullable=True, index=True,
                        comment="네트워크의 오퍼 번호")
    name = Column(String(300), nullable=False, comment="캠페인명")
    advertiser = Column(String(200), nullable=True, comment="광고주")
    vertical = Column(String(100), nullable=True, comment="업종")

    # 원문. 이것이 근거다.
    raw_text = Column(Text, nullable=False)

    # 고정 서식에서 뽑은 값 — 애드릭스 서식은 7건 모두 같아 규칙으로 뽑는다
    conversion = Column(JSON, nullable=True, default=dict,
                        comment="action/fields/reject_reasons")
    ftc_notice = Column(Text, nullable=True, comment="공정위 대가성 문구")

    # 자유 서술에서 뽑은 규칙 목록 (P2 에서 채운다)
    rules = Column(JSON, nullable=True, default=list)
    # 규칙으로 바뀌지 않은 문장. 검사되지 않으므로 화면에 보여준다.
    unmatched = Column(JSON, nullable=True, default=list)
    # 오퍼 내부 모순·사전 충돌
    conflicts = Column(JSON, nullable=True, default=list)

    # 이 오퍼를 담당하는 블로그. 비면 아무도 이 오퍼의 제목을 쓰지 않는다.
    # 애드센스 블로그가 CPA 제목을 가져가면 규정 위반 글이 엉뚱한 곳에 나간다.
    blog_ids = Column(JSON, nullable=True, default=list)

    # 오퍼가 제공한 이미지(스크린샷·심의 배너). 글 생성 때 쓴다.
    # 심의 배너 외 이미지를 쓰면 위반인 오퍼가 있어, 쓸 수 있는 것을
    # 미리 등록해 둔다.
    images = Column(JSON, nullable=True, default=list,
                    comment="[{path, name, note}]")

    landing_url = Column(String(500), nullable=True)
    subid_param = Column(String(50), nullable=True, comment="서브아이디 파라미터")

    status = Column(String(20), nullable=False, default=ST_DRAFT, index=True)
    recheck_due = Column(DateTime(timezone=True), nullable=True, index=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)

    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CpaOffer({self.id}, {self.name}, {self.status})>"

    @property
    def usable(self) -> bool:
        """이 오퍼로 글을 만들어도 되나."""
        return self.status in USABLE and not self.overdue

    @property
    def overdue(self) -> bool:
        """재확인 기한이 지났나."""
        if not self.recheck_due:
            return False
        due = self.recheck_due
        if due.tzinfo is not None:
            due = due.replace(tzinfo=None)
        return datetime.now() > due

    @property
    def coverage(self) -> Optional[float]:
        """원문 중 규칙으로 바뀐 비율. 나머지는 검사되지 않는다."""
        matched = len(self.rules or [])
        total = matched + len(self.unmatched or [])
        return round(matched / total, 3) if total else None

    def counts(self) -> Dict[str, int]:
        """강도별 규칙 수. 화면이 한눈에 보여줄 값."""
        out = {SEV_BLOCK: 0, SEV_WARN: 0, SEV_REVIEW: 0}
        for rule in self.rules or []:
            key = (rule or {}).get("severity") or SEV_BLOCK
            if key in out:
                out[key] += 1
        return out

    def advisories(self) -> List[dict]:
        """기계가 못 지키는 항목. 숨기지 않고 사람에게 보여준다."""
        return [r for r in (self.rules or [])
                if (r or {}).get("type") == "advisory"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "network": self.network,
            "offer_code": self.offer_code, "name": self.name,
            "advertiser": self.advertiser, "vertical": self.vertical,
            "conversion": self.conversion or {},
            "ftc_notice": self.ftc_notice or "",
            "rules": self.rules or [], "unmatched": self.unmatched or [],
            "conflicts": self.conflicts or [],
            "landing_url": self.landing_url or "",
            "images": self.images or [],
            "blog_ids": self.blog_ids or [],
            "status": self.status, "usable": self.usable,
            "overdue": self.overdue, "coverage": self.coverage,
            "counts": self.counts(),
            "advisory_count": len(self.advisories()),
            "recheck_due": (self.recheck_due.isoformat()
                            if self.recheck_due else None),
            "created_at": (self.created_at.isoformat()
                           if self.created_at else None),
        }


def default_recheck(days: int = DEFAULT_RECHECK_DAYS) -> datetime:
    """재확인 기한. 지나면 새 글을 만들지 않는다."""
    return datetime.now() + timedelta(days=days)
