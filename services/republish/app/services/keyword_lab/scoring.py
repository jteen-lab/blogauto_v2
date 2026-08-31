"""후보 판정 — 수요와 공급을 함께 본다.

검색량만 보면 안 된다. 검색량이 커도 문서가 그보다 훨씬 많으면 비집고
들어갈 자리가 없고, 검색량이 작아도 문서가 거의 없으면 가치가 있다.
국내 도구(블랙키위·키워드마스터)가 쓰는 축을 그대로 따른다.

순서도: docs/flowcharts/keyword_lab.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ...models.keyword_candidate import (
    VERDICT_ADOPT, VERDICT_HOLD, VERDICT_PENDING, VERDICT_REJECT,
)

# 월간 검색량 하한. 이보다 낮으면 써도 아무도 안 온다.
MIN_SEARCH_VOLUME = 100

# 포화도 = 검색량 ÷ 문서수. 낮을수록 이미 포화된 자리다.
MIN_SATURATION = 0.2

# 확인 불가한 정보가 글의 핵심인 유형. 품질 게이트와 같은 축이다
# (app/services/generation/quality_gate.py RISKY_PATTERNS).
# 라이프인포에서 146편을 걷어낸 유형이고, 지금 수집 유입 1·2위가 이것이다.
RISK_PATTERNS = (
    (r"고객센터|전화번호|상담전화|콜센터|문의처", "연락처"),
    (r"영업시간|운영시간|진료시간|상영시간표|배차|시간표", "영업시간"),
    (r"채용공고|구인구직|채용정보|연봉|급여|시급", "채용조건"),
    (r"현금화|상품권", "상품권거래"),
)


@dataclass
class Thresholds:
    """판정 기준. 니치마다 적정선이 달라 화면에서 조정할 수 있게 둔다."""

    min_volume: int = MIN_SEARCH_VOLUME
    min_saturation: float = MIN_SATURATION

    @classmethod
    def build(cls, volume: Optional[int], saturation: Optional[float]) -> "Thresholds":
        try:
            v = int(volume) if volume is not None else MIN_SEARCH_VOLUME
        except (TypeError, ValueError):
            v = MIN_SEARCH_VOLUME
        try:
            s = float(saturation) if saturation is not None else MIN_SATURATION
        except (TypeError, ValueError):
            s = MIN_SATURATION
        return cls(min_volume=max(0, v), min_saturation=max(0.0, s))


def risk_label(keyword: str) -> Optional[str]:
    """확인 불가 정보가 핵심인 유형인지. 막지 않고 표시만 한다."""
    for pattern, label in RISK_PATTERNS:
        if re.search(pattern, keyword or ""):
            return label
    return None


def saturation_of(volume: Optional[int], doc_count: Optional[int]) -> Optional[float]:
    """검색량 ÷ 문서수.

    문서가 0이면 나눌 수 없다. 아무도 안 쓴 자리라는 뜻이므로 가장 좋은
    값으로 친다(하한 판정을 통과시킨다).
    """
    if volume is None or doc_count is None:
        return None
    if doc_count <= 0:
        return float(volume) if volume else 0.0
    return round(volume / doc_count, 4)


def judge(
    keyword: str,
    volume: Optional[int],
    doc_count: Optional[int],
    thresholds: Optional[Thresholds] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """(판정, 사유, 위험표시) 를 돌려준다.

    아직 문서수를 재지 않았으면 pending 이다. 재지 않은 것을 채택으로
    올리면 공급을 보지 않고 뽑는 셈이 된다.
    """
    th = thresholds or Thresholds()
    risk = risk_label(keyword)

    if volume is None:
        return VERDICT_PENDING, "검색량 미측정", risk
    if volume < th.min_volume:
        return VERDICT_REJECT, f"검색량 {volume} (하한 {th.min_volume})", risk
    if doc_count is None:
        return VERDICT_PENDING, "문서수 미측정", risk

    sat = saturation_of(volume, doc_count)
    if sat is not None and sat < th.min_saturation:
        return (VERDICT_REJECT,
                f"포화 (검색 {volume} / 문서 {doc_count:,})", risk)

    if risk:
        # 검색량·포화도는 통과했지만 사람이 봐야 한다.
        return VERDICT_HOLD, f"{risk} 유형 — 확인 필요", risk

    return VERDICT_ADOPT, f"검색 {volume} / 문서 {doc_count:,}", risk
