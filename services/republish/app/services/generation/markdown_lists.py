"""목록이 항목마다 쪼개지는 것을 막는다.

AI 가 목록 항목 사이에 빈 줄을 넣어 쓰는 일이 잦다.

    1. 첫째

    2. 둘째

줄 단위로 읽는 변환기는 빈 줄에서 목록을 닫아 버려 `<ol>` 이 항목 수만큼
생긴다. 브라우저는 목록마다 다시 1 부터 세므로 **화면에는 전부 「1.」** 로
보인다. 실제로 그렇게 나갔다(2026-09-16).

빈 줄 뒤에 같은 목록이 이어지면 닫지 않는다. 사이에 문단이나 소제목이
들어오면 그때 닫는다 — 따로 쓴 두 목록은 따로 남아야 한다.
"""
from __future__ import annotations

import re
from typing import List, Sequence

#: 불릿(-, *) 항목
BULLET = re.compile(r'^[\-\*]\s')

#: 번호(1. 2. …) 항목
ORDERED = re.compile(r'^\d+\.\s')


def _next_line(lines: Sequence[str], start: int) -> str:
    """빈 줄을 건너뛴 다음 줄. 끝이면 빈 문자열."""
    for raw in lines[start:]:
        text = raw.strip()
        if text:
            return text
    return ""


def continues(lines: Sequence[str], index: int,
              pattern: re.Pattern) -> bool:
    """지금 줄이 비어 있고, 빈 줄 뒤에 같은 목록이 이어지는가.

    Args:
        lines: 전체 줄
        index: 지금 보고 있는 줄 번호
        pattern: BULLET 또는 ORDERED

    Returns:
        이어지면 True — 호출부는 목록을 닫지 않는다
    """
    if index >= len(lines) or lines[index].strip():
        return False
    return bool(pattern.match(_next_line(lines, index + 1)))


def bullet_continues(lines: Sequence[str], index: int) -> bool:
    """불릿 목록이 빈 줄을 건너 이어지는가."""
    return continues(lines, index, BULLET)


def ordered_continues(lines: Sequence[str], index: int) -> bool:
    """번호 목록이 빈 줄을 건너 이어지는가."""
    return continues(lines, index, ORDERED)


def renumber(html: str) -> str:
    """이미 만들어진 HTML 을 손본다.

    1) `</ol>` 바로 뒤에 `<ol>` 이 오면 사이에 아무것도 없다는 뜻이라 합친다.
    2) 사이에 문단이 끼어 나뉜 목록은 합칠 수 없다(문단이 목록 안으로 들어가
       버린다). 대신 **번호를 이어 준다** — 두 번째 목록부터 `start` 를 매겨
       화면에서 1, 2, 3 으로 읽히게 한다.
    """
    merged = re.sub(r'</ol>\s*<ol>', '', html or "")
    merged = re.sub(r'</ul>\s*<ul>', '', merged)
    return _continue_numbers(merged)


def _continue_numbers(html: str) -> str:
    """나뉜 번호 목록에 이어지는 start 를 매긴다.

    `<ol>` 이 여럿이면 앞 목록의 항목 수만큼 더한 번호에서 시작한다.
    이미 `start` 가 있는 목록은 손대지 않는다 — 원문 번호가 우선이다.
    """
    if html.count("<ol") < 2:
        return html

    out = []
    seen = 0
    for chunk in re.split(r'(<ol[^>]*>.*?</ol>)', html, flags=re.S):
        if not chunk.startswith("<ol"):
            out.append(chunk)
            continue
        items = chunk.count("<li>")
        if seen and chunk.startswith("<ol>"):
            chunk = f'<ol start="{seen + 1}">' + chunk[len("<ol>"):]
        seen += items
        out.append(chunk)
    return "".join(out)
