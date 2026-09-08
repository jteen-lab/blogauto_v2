"""오퍼 규칙 → 프롬프트 지시문.

**오퍼 명세에 있는 것만 쓴다.** 명세에 없는 수치·효능·혜택을 지어내면
네트워크 규정 위반이자 업종법 위반이다. 근거 등급(`reference/evidence.py`)
에서 쓴 사고를 그대로 옮겼다.

지시만으로는 못 막는다. AI 는 지시를 어긴다. 발행 전 `gate.py` 가 다시 본다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

_LIMIT = 40   # 한 종류당 나열 상한. 다 넣으면 프롬프트가 규칙표가 된다


def _by(rules: Sequence[dict], kind: str) -> List[dict]:
    return [r for r in rules or [] if (r or {}).get("type") == kind]


def _values(rules: Sequence[dict], kind: str,
            scopes: Sequence[str] = ()) -> List[str]:
    out = []
    for rule in _by(rules, kind):
        if scopes and (rule.get("scope") or "all") not in scopes:
            continue
        value = str(rule.get("value") or "").strip()
        if value and value not in out:
            out.append(value)
    return out[:_LIMIT]


def build(offer: Any) -> str:
    """이 오퍼로 글을 쓸 때 붙일 지시문.

    Args:
        offer: CpaOffer

    Returns:
        프롬프트에 넣을 문자열. 규칙이 없으면 그 사실을 밝힌다.
    """
    rules = offer.rules or []
    blocks: List[str] = ["■ 이 글은 광고입니다 (반드시 지킬 것)"]

    notice = (offer.ftc_notice or "").strip()
    if notice:
        blocks.append(
            f"- 다음 문구를 **본문 맨 앞** 또는 제목 앞 [광고] 로 넣으세요.\n"
            f'  "{notice}"')

    for value in _values(rules, "must_include"):
        blocks.append(f"- 다음 문구를 반드시 넣으세요: \"{value}\"")

    topics = _values(rules, "required_topic")
    if topics:
        blocks.append("- 다음 내용을 반드시 다루세요:\n"
                      + "\n".join(f"  · {t}" for t in topics))

    banned = _values(rules, "must_not_include", ("body", "all", "title"))
    if banned:
        blocks.append("- 다음 낱말을 쓰지 마세요: " + ", ".join(banned))

    title_banned = _values(rules, "must_not_include", ("title", "keywords"))
    if title_banned:
        blocks.append("- 제목에는 특히 다음을 쓰지 마세요: "
                      + ", ".join(title_banned))

    forbidden = _values(rules, "forbidden_topic")
    if forbidden:
        blocks.append("- 다음 주제는 다루지 마세요: " + ", ".join(forbidden))

    replaces = _by(rules, "replace")
    if replaces:
        lines = [f"  · {r.get('target') or '금지 표현'} → {r.get('value')}"
                 for r in replaces[:_LIMIT] if r.get("value")]
        if lines:
            blocks.append("- 다음처럼 순화해 쓰세요:\n" + "\n".join(lines))

    conditionals = _by(rules, "conditional")
    for rule in conditionals[:_LIMIT]:
        blocks.append(f"- 조건: {rule.get('target')} → {rule.get('value')}")

    sources = _values(rules, "content_source")
    if sources:
        blocks.append(
            "■ 사실 정보 — **여기 있는 것만** 사실로 쓰세요\n"
            + "\n".join(f"  · {s}" for s in sources))
    else:
        blocks.append(
            "■ 사실 정보 없음\n"
            "- 광고주가 제공한 사실 정보가 없습니다.\n"
            "- 금액·기간·비율·효과 같은 **수치를 쓰지 마세요.**\n"
            "- 확인이 필요하다는 점을 알리고 상담으로 안내하세요.")

    fields = ((offer.conversion or {}).get("fields") or [])
    if fields:
        blocks.append("■ 상담 안내\n"
                      f"- 상담 시 {', '.join(fields)} 을(를) 남기게 됩니다.\n"
                      "- 과장 없이 무엇을 확인할 수 있는지만 적으세요.")

    rejects = ((offer.conversion or {}).get("reject_reasons") or [])
    if rejects:
        blocks.append(
            "■ 대상 안내\n"
            f"- 다음은 상담이 어렵습니다: {', '.join(rejects)}\n"
            "- 해당하지 않는 분이 신청하도록 조건을 분명히 적으세요.")

    blocks.append(
        "■ 글의 성격\n"
        "- 광고주 안내문을 그대로 옮기지 말고, 읽는 사람에게 필요한 정보로 쓰세요.\n"
        "- 단정하지 말고 확인이 필요한 부분은 확인이 필요하다고 쓰세요.")

    return "\n\n".join(blocks)


def summary(offer: Any) -> Dict[str, Any]:
    """지시문에 무엇이 반영됐는지. 화면이 보여줄 값."""
    rules = offer.rules or []
    return {
        "must_include": len(_by(rules, "must_include")),
        "must_not_include": len(_by(rules, "must_not_include")),
        "required_topic": len(_by(rules, "required_topic")),
        "forbidden_topic": len(_by(rules, "forbidden_topic")),
        "content_source": len(_by(rules, "content_source")),
        "has_notice": bool((offer.ftc_notice or "").strip()),
    }
