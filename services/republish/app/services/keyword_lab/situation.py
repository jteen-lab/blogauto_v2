"""상황 추출 — 질문에서 *조건*을 뽑는다.

**왜 상황인가**: 「이사 견적」이라는 니치 하나에서 글 11편이 나왔다. 주제를
가른 것은 니치가 아니라 조건이었다.

    2층→3층 · 엘베 없음 · 장롱 3짝 · 15평→32평 · 파주→부산 소형 ·
    합가 경유 · 워시타워만 남음

이 조건은 키워드에서 도출되지 않는다. 사람이 질문에 써 넣는다.

    주제 = 니치 × 상황

**중복이 진짜 문제다**: 같은 니치에서 질문을 계속 긁으면 같은 상황이
반복된다. 지문(fingerprint)을 만들어 이미 쓴 상황을 걸러낸다.

**지명은 버린다**: 개인 정보이기도 하고, "송림동→주안동"을 그대로 쓰면
독자가 좁아진다. 거리·권역 성격만 남긴다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §2-1
순서도: docs/flowcharts/topic_discovery.md §2
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set

# 수치 조건. 단위가 붙은 숫자는 거의 항상 조건이다.
UNIT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(평|층|층짜리|cm|mm|인치|만원|천원|원|kg|톤|km|개월|년|년차|"
    r"인승|짝|개|대|칸|명|시간|박)"
)

# 없다/안 된다 계열. 제약 조건이라 글의 축이 되는 일이 많다.
ABSENCE_PATTERN = re.compile(
    r"([가-힣A-Za-z]{2,10})\s*(?:가|이|은|는|도)?\s*"
    r"(없|안\s*되|못\s*하|불가|미설치|미등록)"
)

# A에서 B로 — 이동·변화. 지명은 버리고 '이동 있음'만 남긴다.
MOVE_PATTERN = re.compile(
    r"([가-힣A-Za-z0-9]{2,12})\s*에서\s+"
    r"([가-힣A-Za-z0-9]{1,10}(?:\s[가-힣A-Za-z0-9]{1,10}){0,2})\s*(?:로|으로)\b")

# 상황으로 치지 않는 흔한 말. 지문이 이런 걸로 채워지면 변별력이 없다.
STOP_TOKENS = {
    "이사", "청소", "견적", "비용", "가격", "업체", "문의", "질문", "궁금",
    "방법", "추천", "후기", "정보", "얼마", "어디", "언제", "어떻게",
}

# 지문에 담을 최대 신호 수. 너무 많으면 사소한 차이로 전부 달라 보인다.
FINGERPRINT_LIMIT = 6


@dataclass
class Situation:
    """질문 하나에서 뽑은 조건 묶음."""

    signals: List[str] = field(default_factory=list)
    has_move: bool = False
    source_title: str = ""

    @property
    def is_concrete(self) -> bool:
        """글의 축이 될 만큼 구체적인가."""
        return len(self.signals) >= 2 or (self.has_move and self.signals)

    def fingerprint(self) -> str:
        """중복 대조용 지문. 신호 집합이 같으면 같은 상황으로 본다."""
        picked = sorted(set(self.signals))[:FINGERPRINT_LIMIT]
        if self.has_move:
            picked.append("@move")
        if not picked:
            return ""
        raw = "|".join(picked)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _norm_unit(value: str, unit: str) -> str:
    """수치를 구간으로 뭉갠다. 15평과 16평은 같은 이야기다."""
    try:
        num = float(value.replace(",", ""))
    except ValueError:
        return f"?{unit}"
    if unit in ("층", "짝", "개", "대", "칸", "명", "인승", "박"):
        bucket = int(num)                      # 세는 수는 그대로
    elif unit in ("만원", "천원", "원"):
        # 견적 70만원과 89만원은 "비싼가요"라는 같은 질문이다.
        bucket = int(num // 50) * 50 if num >= 50 else int(num // 10) * 10
    elif num < 10:
        bucket = int(num)
    elif num < 100:
        bucket = int(num // 5) * 5             # 평수는 5 단위
    else:
        bucket = int(num // 50) * 50
    return f"{bucket}{unit}"


def extract(text: str) -> Situation:
    """질문 문장에서 상황 신호를 뽑는다.

    Args:
        text: 질문 제목 + 설명 합본

    Returns:
        Situation. 신호가 없으면 빈 것을 돌려준다(버릴지는 호출부가 정한다).
    """
    body = re.sub(r"\s+", " ", (text or "")).strip()
    signals: List[str] = []

    for value, unit in UNIT_PATTERN.findall(body):
        signals.append(_norm_unit(value, unit))

    for noun, _ in ABSENCE_PATTERN.findall(body):
        token = noun.strip()
        if token and token not in STOP_TOKENS:
            signals.append(f"-{token}")

    has_move = bool(MOVE_PATTERN.search(body))

    # 중복 제거하되 순서는 지킨다(사람이 읽을 때 원문 순서가 자연스럽다).
    seen: Set[str] = set()
    unique = [s for s in signals if not (s in seen or seen.add(s))]
    return Situation(signals=unique, has_move=has_move,
                     source_title=(text or "")[:120])


def dedupe(situations: Iterable[Situation],
           known: Iterable[str] = ()) -> List[Situation]:
    """이미 쓴 상황과 겹치는 것을 걸러낸다.

    Args:
        situations: 이번에 뽑은 상황들
        known: 이미 발행·재고에 있는 지문 목록

    Returns:
        새로운 상황만. 구체적이지 않은 것도 여기서 뺀다.
    """
    blocked: Set[str] = {k for k in known if k}
    out: List[Situation] = []
    for item in situations:
        if not item.is_concrete:
            continue
        mark = item.fingerprint()
        if not mark or mark in blocked:
            continue
        blocked.add(mark)
        out.append(item)
    return out


def summarize(situations: List[Situation], limit: int = 12) -> Dict[str, int]:
    """어떤 신호가 몇 번 나왔는지. 니치 확장 여지를 화면이 말하게 한다."""
    count: Dict[str, int] = {}
    for item in situations:
        for signal in item.signals:
            count[signal] = count.get(signal, 0) + 1
    top = sorted(count.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return dict(top)
