"""검색 질의를 다시 쓴다 — 제목 문장을 그대로 넣지 않는다.

    "우리은행 우리아파트론 대출 금리와 방식"

이대로 검색하면 조사·수식어까지 매칭에 섞여, 상품명은 놓치고 "우리은행"
만 걸린 문서(대표전화 안내)가 올라온다. 2026-09-06 실측이 그랬다.

**개체(상품명·기관명)를 뽑아 그것 중심으로 묻는다.** 개체는 뒤이어 관련성
관문에서도 쓴다 — 검색과 판정이 같은 기준을 봐야 한다.

계획서: docs/plans/analytics_integration_plan.md 는 별건이고, 이 작업의
순서도는 docs/flowcharts/reference_accuracy.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# 검색어에서 떼어낼 말 — 어느 주제에나 붙어 검색을 흐린다.
_NOISE = {
    "방법", "방식", "정리", "비교", "총정리", "가이드", "안내", "확인",
    "알아보기", "알아보자", "해보세요", "하세요", "무엇", "어떻게", "왜",
    "얼마", "언제", "어디", "차이", "추천", "후기", "리뷰", "핵심",
    "완벽", "한눈에", "쉽게", "바로", "지금", "올해", "최신", "총",
    "및", "그리고", "위한", "관련", "대한", "대해",
}

# 서술어 어미로 끝나는 낱말은 개체가 아니다. "확인하세요" 가 상품명보다
# 길어서 핵심 개체로 뽑히던 자리다.
_VERBAL = re.compile(
    r"(하세요|해보세요|보세요|합니다|입니다|됩니다|할까요|일까요|하기|"
    r"되는|하는|했다|한다|이다|이란|란|해요|어요)$")

# 조사·어미 — 붙어 있으면 같은 말이 다른 낱말이 된다
_TAIL = re.compile(
    r"(으로|로서|로써|에서|에게|까지|부터|이나|나마|이란|란|은|는|이|가|"
    r"을|를|의|에|와|과|도|만|랑|이며|며|고|과의|와의)$")

# 한글·영문·숫자만 남긴다(가운뎃점·물결은 낱말 경계로 본다)
_WORD = re.compile(r"[가-힣A-Za-z0-9]+")


@dataclass
class SearchPlan:
    """이 제목을 어떻게 검색할 것인가."""

    primary: str                                   # 첫 질의
    fallbacks: List[str] = field(default_factory=list)   # 실패 시 순서대로
    entities: List[str] = field(default_factory=list)    # 관련성 관문이 쓸 개체

    def queries(self) -> List[str]:
        """시도할 질의를 순서대로. 중복은 뺀다."""
        out: List[str] = []
        for q in [self.primary, *self.fallbacks]:
            q = (q or "").strip()
            if q and q not in out:
                out.append(q)
        return out


def strip_particle(word: str) -> str:
    """조사를 뗀다. 두 글자 미만이 되면 원본을 돌려준다."""
    cut = _TAIL.sub("", word)
    return cut if len(cut) >= 2 else word


def tokens(text: str) -> List[str]:
    """비교·검색에 쓸 낱말. 순서를 지킨다 — 제목은 앞이 중요하다."""
    out: List[str] = []
    for raw in _WORD.findall(text or ""):
        word = strip_particle(raw)
        if len(word) < 2 or word in _NOISE or _VERBAL.search(word):
            continue
        if word not in out:
            out.append(word)
    return out


def extract_entities(title: str, limit: int = 3) -> List[str]:
    """제목의 **핵심 개체**.

    긴 낱말일수록 고유하다("우리아파트론" > "대출"). 짧은 일반명사는
    어디에나 있어 개체 구실을 못 한다. 길이 내림차순으로 고르되,
    제목에서의 순서를 완전히 무시하지는 않는다(앞쪽이 주제다).
    """
    words = tokens(title)
    if not words:
        return []
    ranked = sorted(
        enumerate(words),
        key=lambda pair: (-len(pair[1]), pair[0]),
    )
    return [word for _, word in ranked[:limit]]


def build(title: str) -> SearchPlan:
    """제목 하나에 대한 검색 계획.

    첫 질의는 **개체 + 바로 뒤 낱말** 정도로 짧게 간다. 검색 엔진은 긴
    문장을 주면 결과가 급격히 줄고, 적게 나온 결과는 대개 엉뚱하다.

    Args:
        title: 재조합된 제목

    Returns:
        SearchPlan. 제목이 비었으면 전부 빈 값이다.
    """
    words = tokens(title)
    if not words:
        return SearchPlan(primary=(title or "").strip())

    entities = extract_entities(title)
    head = entities[0] if entities else words[0]

    # 첫 질의: 가장 고유한 개체 + 제목 앞머리 낱말(맥락)
    lead = [w for w in words[:3] if w != head]
    primary = " ".join([head, *lead[:2]]).strip()

    fallbacks = [
        " ".join(words[:3]),          # 제목 앞머리 그대로
        head,                          # 개체 하나만 — 가장 넓게
    ]
    return SearchPlan(primary=primary, fallbacks=fallbacks,
                      entities=entities)
