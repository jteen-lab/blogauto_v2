"""마무리 섹션은 글의 맨 끝에 있어야 한다.

두 자리에서 마무리 뒤에 내용이 더 붙는다.

1. **이어쓰기** — 초안이 짧으면 한 번 더 받아 뒤에 잇는다. 초안이 이미
   「마치며」로 끝났으면 그 뒤에 새 섹션이 생긴다.
2. **AEO 지시** — 「구조를 바꾸지 말고 맨 뒤에 자주 묻는 질문을 덧붙이라」고
   한다. 구조가 마무리로 끝나면 역시 마무리 뒤로 간다.

둘 다 내용은 쓸모 있는데 자리만 틀렸다. 그래서 지우지 않고 **옮긴다.**

순서도: docs/flowcharts/closing_last.md
"""
from __future__ import annotations

import re
from typing import List, Tuple

from ...core.logger import get_logger

logger = get_logger("closing_section", "app.log")

#: 마무리로 보는 소제목 낱말
CLOSING_WORDS = (
    "마치며", "마무리", "맺음말", "맺으며", "정리하며", "끝으로",
    "마지막으로", "마지막", "글을 마치며", "총정리",
)

#: h2 소제목 한 줄
_H2 = re.compile(r'^##\s+(.+?)\s*$', re.M)


def _sections(markdown: str) -> List[Tuple[int, str]]:
    """h2 소제목의 (시작 위치, 제목) 목록."""
    return [(m.start(), m.group(1)) for m in _H2.finditer(markdown or "")]


def _is_closing(title: str) -> bool:
    """이 소제목이 마무리인가."""
    text = (title or "").strip()
    return any(word in text for word in CLOSING_WORDS)


def move_closing_last(markdown: str) -> str:
    """마무리 섹션을 맨 끝으로 옮긴다. 옮길 것이 없으면 그대로.

    조심해서 옮긴다.
    - 마무리로 보이는 섹션이 **하나**일 때만 움직인다. 여럿이면 어느 것이
      진짜 마무리인지 알 수 없다.
    - 이미 마지막이면 두지 않는다.
    - 뒤에 남는 내용이 없으면 옮길 이유가 없다.
    """
    text = markdown or ""
    rows = _sections(text)
    if len(rows) < 2:
        return text

    closings = [i for i, (_, title) in enumerate(rows) if _is_closing(title)]
    if len(closings) != 1:
        return text

    at = closings[0]
    if at == len(rows) - 1:
        return text      # 이미 끝이다

    start = rows[at][0]
    end = rows[at + 1][0]
    closing = text[start:end].rstrip()
    rest = (text[:start].rstrip() + "\n\n" + text[end:].rstrip()).strip()
    if not rest:
        return text

    logger.info("[CLOSING] 마무리를 끝으로 옮김 | %s | 뒤에 있던 섹션 %d개",
                rows[at][1][:20], len(rows) - at - 1)
    return f"{rest}\n\n{closing}\n"
