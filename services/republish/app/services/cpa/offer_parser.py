"""오퍼 원문에서 고정 서식을 뽑는다.

실제 오퍼 7건(의료·법률·생활·통신·금융·교육)을 보니 문서가 두 층이다.

    광고주 자유 서술   업종마다 형식이 제각각  → AI 가 규칙으로 (P2)
    애드릭스 고정 서식  7건 모두 같은 모양      → 여기서 규칙으로 뽑는다

**형식이 정해진 곳에 AI 를 쓰지 않는다.** 규칙이 더 정확하고 공짜다.

순서도: docs/flowcharts/cpa_offer.md
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("cpa_offer_parser", "app.log")

# 첫 줄의 캠페인명. 7건 모두 "[이름] CPA 캠페인입니다" 또는 "# 이름" 으로 시작한다.
_NAME_BRACKET = re.compile(r"^[#\s]*\[([^\]]{2,120})\]")
_NAME_HASH = re.compile(r"^#\s*(.{2,120})$")

# 애드릭스 고정 서식의 구분자
_SEC_CONVERSION = "전환 정보"
_SEC_FIELDS = "접수 항목"
_SEC_FTC = "대가성 문구 표시"

# "미승인조건 :" / "미승인 DB조건 :" 둘 다 쓰인다
_REJECT = re.compile(r"미승인\s*(?:DB)?\s*조건\s*[:：]\s*(.+)")

# 접수 항목의 별표 표기. "＊ 이름" (전각) 과 "* 이름" 이 섞여 있다
_FIELD = re.compile(r"^[＊*]\s*(.+?)\s*$")

# 선택지 줄 ("- 가정이사" 등) 은 항목이 아니라 값이다
_CHOICE = re.compile(r"^[-·]\s*")


# 이름 뒤에 붙는 상투구. 이름의 일부가 아니다.
_TAIL = re.compile(
    r"\s*(CPA\s*캠페인\s*(입니다|진행합니다)?|CPA\s*진행합니다|캠페인\s*입니다)"
    r"\s*\.?\s*$")


def _strip_tail(text: str) -> str:
    """끝에 붙은 'CPA 캠페인입니다' 류를 뗀다."""
    return _TAIL.sub("", (text or "").strip()).strip()[:120]


def _first_nonempty(lines: List[str]) -> str:
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def offer_name(text: str) -> str:
    """캠페인명. 못 찾으면 첫 줄을 쓴다.

    대괄호만 떼면 안 된다. "[자격증]산지식물자원관리사" 는 대괄호가 이름의
    앞머리일 뿐이라 "자격증" 만 남으면 오퍼를 구분할 수 없다.
    """
    lines = (text or "").splitlines()
    head = _first_nonempty(lines)
    for line in [head] + [x.strip() for x in lines[:5]]:
        found = _NAME_HASH.match(line)
        if found:
            return _strip_tail(found.group(1))
        found = _NAME_BRACKET.match(line)
        if found:
            # 대괄호 뒤에 글자가 이어지면 그것까지가 이름이다
            rest = line[found.end():].strip()
            if rest and not rest.startswith("CPA"):
                return _strip_tail(line.lstrip("# ").strip())
            return _strip_tail(found.group(1))
    return _strip_tail(head)[:120]


def reject_reasons(text: str) -> List[str]:
    """미승인 조건. 이걸 모르면 헛수고할 트래픽을 부른다."""
    found = _REJECT.search(text or "")
    if not found:
        return []
    raw = found.group(1)
    # 괄호 안 쉼표로 쪼개면 안 된다.
    # "나이제한(24세미만,55세이상)" 이 둘로 갈라진다.
    parts, buf, depth = [], "", 0
    for ch in raw:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return [p.strip(" .·-") for p in parts if p.strip(" .·-")]


def intake_fields(text: str) -> List[str]:
    """상담 신청 시 받는 항목. 글이 무엇을 안내해야 하는지가 여기서 나온다."""
    body = text or ""
    if _SEC_FIELDS not in body:
        return []
    after = body.split(_SEC_FIELDS, 1)[1]
    # 대가성 문구 절 앞까지만 본다
    if _SEC_FTC in after:
        after = after.split(_SEC_FTC, 1)[0]

    out: List[str] = []
    for line in after.splitlines():
        stripped = line.strip()
        if not stripped or _CHOICE.match(stripped):
            continue
        found = _FIELD.match(stripped)
        if found:
            name = found.group(1).strip()
            if name and name not in out:
                out.append(name)
    return out


def ftc_notice(text: str) -> str:
    """공정위 대가성 문구. 7건 모두 같은 안내가 붙어 있다.

    예시 중 첫 번째를 기본값으로 쓴다. 어느 것을 써도 되지만 하나로 고정해야
    검사가 단순해진다.
    """
    body = text or ""
    if _SEC_FTC not in body:
        return ""
    after = body.split(_SEC_FTC, 1)[1]
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("이 포스팅은"):
            return stripped
    return ""


def notice_position(text: str) -> str:
    """대가성 문구를 어디에 두라고 하는가.

    2024-12-01 개정으로 끝부분 게재가 막혔다. 원문에 그 안내가 있으면 따른다.
    """
    body = text or ""
    if "제목 앞에 [광고]" in body or "내용 첫 부분" in body:
        return "title_or_body_start"
    return "body_start"


def parse(text: str) -> Dict[str, Any]:
    """고정 서식을 뽑는다.

    Args:
        text: 프로모션 페이지 원문 전체

    Returns:
        {"name", "conversion": {...}, "ftc_notice", "found": [...]}
        `found` 는 실제로 찾아낸 항목 이름 — 화면이 무엇이 비었는지 보여준다.
    """
    name = offer_name(text)
    rejects = reject_reasons(text)
    fields = intake_fields(text)
    notice = ftc_notice(text)

    found = [key for key, value in (
        ("캠페인명", name), ("미승인조건", rejects),
        ("접수항목", fields), ("대가성문구", notice)) if value]

    logger.info("[CPA_PARSE] '%s' | 미승인 %d · 접수 %d · 문구 %s",
                name[:30], len(rejects), len(fields), bool(notice))

    return {
        "name": name,
        "conversion": {
            "action": "상담 신청",
            "fields": fields,
            "reject_reasons": rejects,
        },
        "ftc_notice": notice,
        "notice_position": notice_position(text),
        "found": found,
    }
