"""제목 스타일 지시 템플릿.

블로그 성격마다 먹히는 제목 형태가 다르다. 금융에서 통하는 낚시가
맛집에서는 안 먹히고, 그 반대도 마찬가지다.

**각 스타일이 문장의 다른 부분을 건드리도록** 설계했다. 그래야 결과가
갈린다. 다섯 지시가 모두 "느낌" 만 말하면 같은 자리를 건드려 비슷한
제목이 나온다(실제로 그랬다).

    emotional  앞부분 — 독자 상황 호명
    practical  구체 정보 — 숫자·장소·기간
    question   시작 — 의문사
    viral      통념 뒤집기 — 역설·의외성
    minimal    끝 — 명사로 마감

계획서: docs/plans/title_tab_workplan.md §4-5
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 템플릿 정의. `topics` 는 자동 추천에 쓰는 주제 이름 조각이다.
TEMPLATES: List[Dict[str, Any]] = [
    {
        "code": "trust",
        "label": "신뢰·정보형",
        "hint": "금융·재테크·건강 — 과장하면 신뢰를 잃는다",
        "topics": ["금융", "대출", "재테크", "돈관리", "건강", "의학", "보험"],
        "prompts": {
            "emotional": ("독자의 상황을 조건절로 시작할 것. "
                          "예: 대출이 막혔다면 꼭 확인해야 할 신용점수 관리법"),
            "practical": ("숫자·기간·금액 중 하나를 반드시 넣을 것. "
                          "예: 연 3.5% 금리로 30일 안에 승인받는 조건 정리"),
            "question": ("판단을 묻는 의문사로 시작할 것. "
                         "예: 얼마나 빌릴 수 있고 언제까지 갚아야 하는가"),
            # 단정형 낚시는 애드센스 심사에도 불리하다
            "viral": ("통념을 뒤집되 단정하지 말 것. "
                      "예: 알고도 놓치는 중도상환 수수료 오히려 손해인 경우"),
            "minimal": ("명사로 끝낼 것. 수식어·감탄사 금지. "
                        "예: 신용대출 금리 비교와 승인 조건 총정리"),
        },
    },
    {
        "code": "review",
        "label": "체험·후기형",
        "hint": "여행·맛집·레시피 — 숫자보다 구체적 장면",
        "topics": ["여행", "관광", "음식", "레시피", "맛집", "카페"],
        "prompts": {
            "emotional": "감각어를 하나 넣을 것. 예: 진한 육수가 인상적인 성수동 조용한 국밥집 후기",
            "practical": ("장소·시간·인원 중 하나를 넣을 것. "
                          "예: 성수동 주말 오후 4인 예약 가능한 코스 정리"),
            "question": ("선택을 묻는 형태로 쓸 것. "
                         "예: 양양 여행 어디서 자고 뭘 먹어야 좋을까"),
            "viral": "의외성을 넣을 것. 예: 현지인만 아는 간판 없는 양양 숨은 맛집 다섯 곳",
            "minimal": ("지명이나 대상 + 한 단어로 끝낼 것. "
                        "예: 양양 바다 근처 가성비 맛집과 카페 정리"),
        },
    },
    {
        "code": "howto",
        "label": "문제해결형",
        "hint": "IT·생활정보 — 안 될 때 검색하는 니치",
        "topics": ["컴퓨터", "IT", "AI", "인공지능", "생활", "정보", "꿀팁"],
        "prompts": {
            "emotional": ("곤란한 상황을 앞에 둘 것. "
                          "예: 갑자기 인쇄가 안 될 때 가장 먼저 확인할 설정"),
            "practical": "단계 수나 소요 시간을 넣을 것. 예: 5분이면 끝나는 프린터 오프라인 해결 3단계",
            "question": ("방법을 묻는 의문사로 시작할 것. "
                         "예: 왜 연결이 끊기고 어떻게 되돌려야 하는가"),
            "viral": "흔한 실수를 지적할 것. 예: 대부분 틀리는 설정 이것만 바꾸면 바로 해결",
            "minimal": "대상 + 동작 명사로 끝낼 것. 예: 프린터 오프라인 오류 원인과 해결 방법 정리",
        },
    },
    {
        "code": "prep",
        "label": "준비·시험형",
        "hint": "취업·자격증·육아 — 기한과 자격이 걸린 니치",
        "topics": ["취업", "자격증", "시험", "출산", "육아", "교육", "입시"],
        "prompts": {
            "emotional": ("준비 단계를 호명할 것. "
                          "예: 이제 막 시작했다면 알아야 할 실기 준비 순서"),
            "practical": "일정·기간·횟수를 넣을 것. 예: 3개월 준비로 2회차 실기까지 끝내는 일정표",
            "question": ("자격이나 시기를 묻는 형태로 쓸 것. "
                         "예: 접수는 언제부터이고 누가 응시할 수 있는가"),
            "viral": "놓치기 쉬운 조건을 짚을 것. 예: 모르면 못 받는 응시료 환불과 마감 직전 주의점",
            "minimal": "대상 + 항목 명사로 끝낼 것. 예: 전기기사 실기 접수 일정과 준비물 총정리",
        },
    },
]

BY_CODE = {t["code"]: t for t in TEMPLATES}


def recommend(topic_names: List[str]) -> Optional[str]:
    """주제 이름들로 템플릿을 고른다.

    여러 니치를 쓰는 블로그가 많으므로 **가장 많이 맞은 템플릿**을 준다.
    하나도 안 맞으면 None — 짐작해서 고르면 엉뚱한 지시가 들어간다.
    """
    scores: Dict[str, int] = {}
    for name in topic_names:
        text = (name or "").lower()
        if not text:
            continue
        for template in TEMPLATES:
            hits = sum(1 for word in template["topics"]
                       if word.lower() in text)
            if hits:
                scores[template["code"]] = scores.get(
                    template["code"], 0) + hits

    if not scores:
        return None
    # 동점이면 정의 순서가 앞선 것을 쓴다(신뢰형이 가장 보수적이다)
    order = {t["code"]: i for i, t in enumerate(TEMPLATES)}
    return min(scores.items(), key=lambda x: (-x[1], order[x[0]]))[0]


def prompts_for(code: str) -> Dict[str, str]:
    """템플릿의 스타일 지시. 모르는 코드는 빈 dict."""
    template = BY_CODE.get(code)
    return dict(template["prompts"]) if template else {}
