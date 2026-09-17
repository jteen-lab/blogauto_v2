"""제목을 어디서 가져왔느냐에 따라 재조합의 권한을 달리한다.

수집한 제목은 이미 검색어에 맞춰져 있어 **표현만** 손봐야 한다. 반면
지식iN·카페 질문 제목은 사람이 급히 쓴 메모라, 낱말을 붙들고 다듬으면
맥락 없는 제목이 된다.

    부동산 과 계약은 끝났는 데 이사 문제 관리 사무소?
    → 부동산 계약 끝난 뒤 이사 문제 관리 사무소 먼저 확인할 일   (지어낸 말)

**본문 유무로만 가르지 않는다.** 카페 비공개 글은 본문을 못 가져와도
여전히 질문 제목이다. 소스 종류를 먼저 보고, 본문 유무로 권한을 조절한다.

순서도: docs/flowcharts/title_rewrite_by_source.md
"""
from __future__ import annotations

from typing import Any, Dict, Optional

#: 사람이 급히 쓴 메모가 제목으로 오는 소스
QUESTION_SOURCES = ("naver_kin", "naver_cafe")

MODE_POLISH = "polish"    # 다듬기 — 수집 제목
MODE_REWRITE = "rewrite"  # 다시 쓰기 — 질문 + 본문
MODE_REPAIR = "repair"    # 고쳐 쓰기 — 질문, 본문 없음

MODE_LABEL = {
    MODE_POLISH: "다듬기",
    MODE_REWRITE: "다시 쓰기",
    MODE_REPAIR: "고쳐 쓰기",
}

#: 어느 갈래든 지켜야 할 것
COMMON_RULES = (
    "- 그 사람에게만 해당하는 조건은 빼세요 — 날짜, 동·호수, 특정 단지\n"
    "  이름처럼 검색하는 다른 사람에게 쓸모없는 것.\n"
    "- 검색되는 조건은 남기세요 — 평수, 원룸·투룸, 이사 거리, 층수 같은 유형.\n"
    "- 원문 제목의 낱말을 세 개 이상 잇달아 그대로 옮기지 마세요."
)

REWRITE_BLOCK = (
    "[이 제목의 성격]\n"
    "이 제목은 사람이 급히 쓴 질문 제목입니다. 말이 끊겨 있고, 무엇을 묻는지\n"
    "제목만으로는 알기 어렵습니다. **제목이 아니라 아래 본문이 묻는 것**을\n"
    "한 줄로 만드세요.\n"
    "- 원문 제목의 낱말은 지켜야 할 것이 아니라 참고입니다. 맥락이 어긋나면\n"
    "  버리세요.\n"
    "- 본문에 없는 주장을 제목으로 만들지 마세요. 본문이 말하지 않은 것을\n"
    "  \"먼저 확인할 일\" 처럼 단정하면 읽는 사람이 속습니다.\n"
    "- 같은 처지의 사람이 검색할 말로 쓰세요.\n"
)

REPAIR_BLOCK = (
    "[이 제목의 성격]\n"
    "이 제목은 사람이 급히 쓴 질문 제목입니다. 본문은 가져오지 못했습니다.\n"
    "- 끊긴 말을 읽히는 문장으로 이으세요.\n"
    "- **제목이 말하지 않는 것을 단정하지 마세요.** 무엇을 먼저 하라거나\n"
    "  어디에 물어보라는 말은, 제목에 그 내용이 없으면 지어낸 것입니다.\n"
    "- 무엇을 묻는지 분명하지 않으면 묻는 형태 그대로 두세요.\n"
)


def source_of(question: Optional[Dict[str, Any]]) -> str:
    """질문이 어디서 왔는지. 모르면 빈 문자열."""
    if not isinstance(question, dict):
        return ""
    return str(question.get("source") or "").strip()


def has_body(question: Optional[Dict[str, Any]]) -> bool:
    """본문을 가져왔는가."""
    if not isinstance(question, dict):
        return False
    return bool((question.get("question") or "").strip()
                or (question.get("answer") or "").strip())


def resolve_mode(question: Optional[Dict[str, Any]]) -> str:
    """이 제목을 어느 갈래로 다룰지.

    소스를 먼저 본다 — 카페 비공개처럼 본문이 없어도 질문은 질문이다.
    소스를 모르는데 본문만 있으면 그것도 질문으로 본다(옛 저장분 호환).
    """
    source = source_of(question)
    if source in QUESTION_SOURCES:
        return MODE_REWRITE if has_body(question) else MODE_REPAIR
    if has_body(question):
        return MODE_REWRITE
    return MODE_POLISH


def build_block(question: Optional[Dict[str, Any]]) -> str:
    """재조합 프롬프트 앞에 붙일 지시. 다듬기면 빈 문자열."""
    mode = resolve_mode(question)
    if mode == MODE_POLISH:
        return ""
    head = REWRITE_BLOCK if mode == MODE_REWRITE else REPAIR_BLOCK
    return head + COMMON_RULES


def keyword_rule(question: Optional[Dict[str, Any]]) -> str:
    """핵심어를 얼마나 붙들지. 갈래마다 다르다."""
    if resolve_mode(question) == MODE_POLISH:
        return ("\n이 말들이 제목에서 빠지면 검색에 잡히지 않습니다.")
    return ("\n이 말들은 **참고**입니다. 뜻이 통하지 않으면 다른 말로 바꾸거나"
            " 빼도 됩니다 — 읽히는 제목이 먼저입니다.")
