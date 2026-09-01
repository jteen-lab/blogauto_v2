"""검색 의도 분류 — 같은 주제라도 묻는 것이 다르면 다른 글이다.

"전기기사 실기 방법" 과 "전기기사 실기 후기" 는 주제가 같지만 답이 다르다.
의도를 나누지 않으면 키워드 10개로 사실상 같은 글 10편을 쓰게 된다.

구글 AI 검색은 질의 하나를 하위 질의로 쪼개 답을 합성한다(query fan-out).
그래서 의도별로 나눈 하위 글을 갖추는 것이 노출에도 유리하다.

규칙 기반으로 판정한다. AI 를 부르면 키워드마다 호출이 붙어 비용이 커지고,
한국어 의도어는 표현이 정형적이라 규칙으로도 충분히 잡힌다.

계획서: docs/plans/keyword_module_redesign_plan.md §3 [4]
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# 의도 코드
INTENT_INFO = "info"          # 정의·개념 — 이게 뭔가
INTENT_HOWTO = "howto"        # 방법·절차 — 어떻게 하나
INTENT_COMPARE = "compare"    # 비교 — 뭐가 다른가
INTENT_REVIEW = "review"      # 후기·추천 — 쓸 만한가
INTENT_PRICE = "price"        # 비용 — 얼마인가
INTENT_TROUBLE = "trouble"    # 문제 해결 — 왜 안 되나
INTENT_SCHEDULE = "schedule"  # 일정·기한 — 언제인가

INTENTS = (INTENT_INFO, INTENT_HOWTO, INTENT_COMPARE, INTENT_REVIEW,
           INTENT_PRICE, INTENT_TROUBLE, INTENT_SCHEDULE)

INTENT_LABEL = {
    INTENT_INFO: "정보",
    INTENT_HOWTO: "방법",
    INTENT_COMPARE: "비교",
    INTENT_REVIEW: "후기·추천",
    INTENT_PRICE: "비용",
    INTENT_TROUBLE: "문제 해결",
    INTENT_SCHEDULE: "일정",
}

# 판정 규칙. 위에서부터 먼저 걸리는 것을 쓴다 —
# "설치 비용" 은 방법이 아니라 비용 질문이다.
RULES: Tuple[Tuple[str, str], ...] = (
    (INTENT_PRICE, r"가격|비용|요금|얼마|수수료|할인|무료|가성비|시세"),
    (INTENT_TROUBLE, r"안\s*됨|안\s*돼|안\s*될|오류|에러|실패|해결|고장|먹통|증상"),
    (INTENT_COMPARE, r"비교|차이|vs|대비|어느\s*것|뭐가\s*나|장단점"),
    (INTENT_REVIEW, r"후기|리뷰|추천|순위|best|베스트|top\s*\d|평가|실사용"),
    (INTENT_SCHEDULE, r"일정|기한|마감|접수기간|시험일|언제|공고|발표일"),
    (INTENT_HOWTO, r"방법|하는\s*법|하는법|신청|등록|설치|발급|만들기|준비|절차|사용법|따라하기"),
    (INTENT_INFO, r"뜻|이란|정의|개념|종류|조건|자격|기준|정리"),
)

# 의도별 질문 틀. 제목을 만들 때 하위 질문으로 펼친다(query fan-out).
QUESTION_TEMPLATES: Dict[str, List[str]] = {
    INTENT_INFO: ["{kw}이란 무엇인가", "{kw} 종류와 기준", "{kw} 핵심 정리"],
    INTENT_HOWTO: ["{kw} 하는 방법", "{kw} 준비물과 절차", "{kw} 처음 할 때 순서"],
    INTENT_COMPARE: ["{kw} 차이 비교", "{kw} 어떤 걸 골라야 하나", "{kw} 장단점"],
    INTENT_REVIEW: ["{kw} 실사용 후기", "{kw} 고를 때 기준", "{kw} 추천 정리"],
    INTENT_PRICE: ["{kw} 비용은 얼마인가", "{kw} 가격 비교", "{kw} 아끼는 방법"],
    INTENT_TROUBLE: ["{kw} 안 될 때 확인할 것", "{kw} 오류 해결 순서",
                     "{kw} 자주 나는 문제"],
    INTENT_SCHEDULE: ["{kw} 일정 정리", "{kw} 언제까지인가", "{kw} 놓치면 생기는 일"],
}


def classify(keyword: str) -> str:
    """키워드의 검색 의도. 아무 규칙에도 안 걸리면 정보형으로 본다."""
    text = (keyword or "").lower()
    for intent, pattern in RULES:
        if re.search(pattern, text):
            return intent
    return INTENT_INFO


def spread(keywords: List[str]) -> Dict[str, List[str]]:
    """키워드들을 의도별로 나눈다."""
    out: Dict[str, List[str]] = {}
    for keyword in keywords:
        out.setdefault(classify(keyword), []).append(keyword)
    return out


def questions(keyword: str, intent: Optional[str] = None,
              count: int = 3) -> List[str]:
    """이 키워드에서 펼칠 하위 질문.

    제목의 뼈대로 쓴다. 같은 키워드로 말만 바꾼 제목 여러 개를 만드는 대신,
    **서로 다른 질문**에 답하는 제목을 만들기 위한 것이다.
    """
    picked = intent or classify(keyword)
    templates = QUESTION_TEMPLATES.get(picked, QUESTION_TEMPLATES[INTENT_INFO])
    return [t.format(kw=keyword) for t in templates[:max(1, count)]]


def dominant(keywords: List[str]) -> str:
    """묶음 전체를 대표하는 의도(가장 많은 쪽)."""
    if not keywords:
        return INTENT_INFO
    tally: Dict[str, int] = {}
    for keyword in keywords:
        code = classify(keyword)
        tally[code] = tally.get(code, 0) + 1
    return max(tally.items(), key=lambda kv: kv[1])[0]
