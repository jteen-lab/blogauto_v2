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


#: 질문에서 온 것으로 볼 소스. 나머지는 참고 글로 다룬다
QUESTION_SOURCES = ("naver_kin", "naver_cafe")


def _is_question(question: Dict[str, Any]) -> bool:
    """질문에서 온 글감인가.

    소스를 모르면 질문으로 본다 — 옛 저장분이 그렇고, 지식iN·카페만
    쓰던 시절에는 소스를 적지 않았다.
    """
    source = str(question.get("source") or "").strip()
    return (not source) or source in QUESTION_SOURCES


def _question_block(body: str, answer: str) -> list:
    """질문에서 왔을 때. 그 상황에 답하는 글을 쓴다."""
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
    return lines


def _reference_block(body: str, answer: str) -> list:
    """검색으로 찾은 글일 때.

    **말을 달리해야 한다.** 남의 블로그 글을 "질문자가 쓴 내용"으로
    알아들으면 엉뚱한 글이 나온다.
    """
    lines = ["[참고한 글]"]
    if body:
        lines.append(f"찾은 내용: {body}")
    if answer:
        lines.append(f"덧붙은 내용: {answer}")
    lines.append(
        "\n위 내용에서 **사실과 정보만** 참고합니다. 문장·구성·표현은"
        " 새로 짭니다 — 옮겨 적으면 남의 글이 됩니다.\n"
        "참고한 글에 없는 수치·날짜·금액을 지어내지 않습니다.\n"
        "어디서 참고했는지는 글에 적지 않습니다."
    )
    return lines


def build(question: Optional[Dict[str, Any]]) -> str:
    """프롬프트 앞에 붙일 블록. 글감이 없으면 빈 문자열.

    질문에서 왔는지 검색으로 찾았는지에 따라 말이 갈린다.
    순서도: docs/flowcharts/workbench_web_sources.md
    """
    if not isinstance(question, dict):
        return ""
    body = (question.get("question") or "").strip()[:Q_LIMIT]
    answer = (question.get("answer") or "").strip()[:A_LIMIT]
    if not body and not answer:
        return ""

    lines = (_question_block(body, answer) if _is_question(question)
             else _reference_block(body, answer))
    return "\n".join(lines)


def attach(settings: Dict[str, Any],
           question: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """설정 사본에 질문을 얹는다. 원본은 건드리지 않는다."""
    out = dict(settings or {})
    if question:
        out[SETTING_KEY] = question
    return out
