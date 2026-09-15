"""글을 쓰게 된 질문을 프롬프트에 얹는다.

제목만 넘기면 모델은 제목에서 상황을 짐작해 쓴다. 질문자가 쓴 본문이
있으면 조건(지역·품목·날짜·층수)이 그대로 들어와 글이 구체적으로 된다.

순서도: docs/flowcharts/question_body.md
"""
from typing import Any, Dict, Optional

#: 모듈 설정에 실려 오는 키
SETTING_KEY = "source_question"

#: 프롬프트가 길어지지 않게 자른다
Q_LIMIT = 1200
A_LIMIT = 900


def build(question: Optional[Dict[str, Any]]) -> str:
    """프롬프트 앞에 붙일 블록. 질문이 없으면 빈 문자열.

    답변은 **참고만** 하라고 명시한다. 그대로 옮기면 남의 글이 된다.
    """
    if not isinstance(question, dict):
        return ""
    body = (question.get("question") or "").strip()[:Q_LIMIT]
    answer = (question.get("answer") or "").strip()[:A_LIMIT]
    if not body and not answer:
        return ""

    lines = ["[이 글을 쓰게 된 질문]"]
    if body:
        lines.append(f"질문자가 쓴 내용: {body}")
    if answer:
        lines.append(f"달린 답(참고용): {answer}")
    lines.append(
        "\n위 상황에 답하는 글을 씁니다. 질문에 나온 조건(지역·품목·"
        "날짜·층수 같은 것)을 글에 살립니다.\n"
        "달린 답은 참고만 합니다 — 문장을 그대로 옮기지 않습니다.\n"
        "질문을 어디서 봤는지는 글에 적지 않습니다."
    )
    return "\n".join(lines)


def attach(settings: Dict[str, Any],
           question: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """설정 사본에 질문을 얹는다. 원본은 건드리지 않는다."""
    out = dict(settings or {})
    if question:
        out[SETTING_KEY] = question
    return out
