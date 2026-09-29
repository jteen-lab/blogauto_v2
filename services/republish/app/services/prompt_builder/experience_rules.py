"""근거 기반 경험담 규칙 — 생성 프롬프트 맨 끝에 붙는 '경험 서술 규칙'.

자동 블로그에는 실제 경험이 없다. 1인칭을 통째로 막으면 글이 딱딱해지고,
그대로 두면 모델이 "저도 먹어 봤는데 효과가 있었다" 같은 가짜 경험을
지어낸다. 그래서 경험처럼 읽히는 문장은 **모은 자료의 사실에서만** 만든다.

  (A) 후기 요약형  — 자료 속 실제 후기를 풀어 옮긴다
  (B) 절차 체험형  — 자료에 있는 공식·실제 절차를 따라가듯 쓴다
  (C) 1인칭 생활 경험 — 저위험 주제만, 글당 1~2문장, 감각·감정만

모듈 DB 프롬프트(예: 169 user_prompt_template, 로테이션 변형)에도 경험 지시가
있다. DB 를 고치지 않고 이 블록을 **마지막에** 붙여 앞선 지시를 덮는다.

순서도: docs/flowcharts/evidence_based_experience.md
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from ..reference.health_sources import HEALTH_TOPIC_KEYWORDS

RISK_HEALTH = "health"
RISK_YMYL = "ymyl"
RISK_LOW = "low"

# 금융·법률 — 1인칭 경험 금지(YMYL). 목록을 바꾸려면 여기만 고친다.
# '법'·'약' 한 글자는 쓰지 않는다('방법'·'절약'·'예약'이 걸린다).
FINANCE_LEGAL_KEYWORDS: tuple = (
    "금융", "대출", "보험", "세금", "부가세", "종합소득세", "연말정산", "세무",
    "금리", "투자", "주식", "펀드", "코인", "적금", "예금", "신용", "카드론",
    "연금", "법률", "법원", "법적", "민법", "형법", "노동법", "소송", "배상", "합의금", "변호사", "고소", "이혼", "상속",
    "계약", "전세", "보증금", "청약",
)

# 건강 낱말 중 '육아' 만 걸리면 생활 노하우로 본다. 아래 의료 낱말이
# 함께 있으면 건강형(1인칭 금지)이다.
_LIFESTYLE_HEALTH_WORDS: frozenset = frozenset({"육아"})
MEDICAL_KEYWORDS: tuple = (
    "약물", "의약품", "진통제", "감기약", "상비약", "치료", "수술", "주사", "병원", "질환", "증상", "처방", "복용",
    "부작용", "백신", "접종", "시술", "영양제", "위고비", "마운자로",
)

BLOCK_HEADER = "■ 경험 서술 규칙 (최종 우선)"
OVERRIDE_LINE = "이 규칙은 위의 경험·페르소나 지시보다 우선한다."
MAX_REVIEW_SNIPPETS = 3
_SNIPPET_CHARS = 160


def classify_risk(title: str = "",
                  topic_names: Optional[Iterable[str]] = None) -> str:
    """제목·주제 이름으로 위험도를 정한다: health / ymyl / low."""
    text = " ".join([title or ""] + [n for n in (topic_names or []) if n])
    health_hits = {k for k in HEALTH_TOPIC_KEYWORDS if k in text}
    medical = any(k in text for k in MEDICAL_KEYWORDS)
    if health_hits and (medical or not health_hits <= _LIFESTYLE_HEALTH_WORDS):
        return RISK_HEALTH
    if medical:
        return RISK_HEALTH
    if any(k in text for k in FINANCE_LEGAL_KEYWORDS):
        return RISK_YMYL
    return RISK_LOW


def _snippets(review_snippets: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for s in review_snippets or []:
        s = " ".join((s or "").split())
        if not s:
            continue
        out.append(s[:_SNIPPET_CHARS])
        if len(out) >= MAX_REVIEW_SNIPPETS:
            break
    return out


def build_block(risk: str = RISK_LOW,
                review_snippets: Optional[Sequence[str]] = None) -> str:
    """'경험 서술 규칙' 블록 텍스트."""
    lines = [
        BLOCK_HEADER,
        OVERRIDE_LINE,
        "이 글의 필자는 실제로 겪은 일이 없다. 경험처럼 읽히는 문장은 "
        "위 참고 자료에 있는 사실로만 만든다.",
        "",
        "허용되는 경험 서술:",
        "(A) 후기 요약형 — 자료에 나온 실제 후기를 내 말로 풀어 옮긴다. "
        "예: \"직접 해 본 분들의 후기를 보면 ~\", \"~를 겪은 분들은 ~라고 "
        "말합니다\". 문장을 그대로 베끼지 말고, 이름·닉네임·지역 등 개인 "
        "정보는 쓰지 않는다.",
        "(B) 절차 체험형 — 자료에 있는 공식·실제 절차를 따라가듯 쓴다. "
        "예: \"실제로 신청 화면에 들어가면 먼저 ~를 고르게 됩니다\". "
        "자료에 없는 단계·화면·버튼은 만들지 않는다.",
    ]
    if risk == RISK_LOW:
        lines.append(
            "(C) 1인칭 생활 경험 — 글 전체에서 1~2문장까지, 짧게. 냄새·촉감·"
            "번거로움·뿌듯함 같은 일반적인 감각·감정만 쓴다. 자료에 없는 "
            "숫자·날짜·가격·브랜드·결과·기간은 1인칭 문장에 넣지 않는다.")
    else:
        lines.append(
            "(C) 1인칭 경험 금지 — 이 주제는 건강·의료·금융·법률(YMYL)이다. "
            "\"저도 ~해 봤는데\" 같은 1인칭 경험을 쓰지 말고 (A)·(B)만 쓴다.")
    lines += [
        "",
        "금지:",
        "- 경험 문장 안에 자료에 없는 사실(수치·기간·가격·효과·결과)을 지어내기",
        "- 약·치료·수술·시술·주사·다이어트약, 대출·보험·세금·투자, 소송·법률 "
        "문제에 대한 1인칭 경험(주제와 무관하게 항상 금지)",
        "- \"저도 먹어 봤는데 효과가 있었다\", \"제가 받아 보니 한도가 ~였다\" "
        "같은 효과·결과 체험 주장",
        "- 자료에 후기·절차 재료가 없으면 경험 문단을 억지로 만들지 말고 "
        "건너뛴다(구조가 후기·에피소드를 요구해도 사실 설명으로 대신한다)",
    ]
    snips = _snippets(review_snippets)
    if snips:
        lines += ["", "후기 재료 (그대로 옮기지 말고 (A) 형식으로 풀어 쓸 것):"]
        lines += [f"- {s}" for s in snips]
    return "\n".join(lines)


def append_block(prompt: str, title: str = "",
                 topic_names: Optional[Iterable[str]] = None,
                 review_snippets: Optional[Sequence[str]] = None) -> str:
    """프롬프트 맨 끝에 규칙 블록을 붙인다(이미 있으면 그대로)."""
    if BLOCK_HEADER in (prompt or ""):
        return prompt
    block = build_block(classify_risk(title, topic_names), review_snippets)
    return f"{(prompt or '').rstrip()}\n\n{block}"
