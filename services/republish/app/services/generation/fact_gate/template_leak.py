"""L2. 글쓰기 틀 지시 문구가 본문에 새어 나온 문장을 지운다.

슈마즈 첫 글(5230, 2026-10-21)에 "항목: 값으로 정리하면 다음과 같습니다."가
그대로 실렸다. 프롬프트 블록 Q-AEO 의 '"항목: 값" 줄로 분리할 것' 지시를
모델이 문장으로 옮겨 쓴 것. 심사자 눈에 '찍어낸 글' 표시라 저장 전에 지운다.

  1) 글쓰기 지시문에 '지시 문구를 본문에 쓰지 말 것' 한 줄(with_directive)
  2) 저장 전 새어 나온 문장 삭제(scrub) — 문장 하나만 지우고 줄은 남긴다

순서도: docs/flowcharts/shoemaz_fact_gate.md (L2)
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

DIRECTIVE = ("지시문에 쓰인 형식 이름('항목: 값', '키-값', '즉답', 'FAQ 블록' 등)을 "
             "본문 문장에 그대로 쓰지 않는다.")

# 지시 용어가 들어간 문장(마침표·줄 끝까지)
_LEAK = re.compile(
    r"[ \t]*(?:[^\s.!?。][^\n.!?。]*?)?"
    r"(?:['\"“]?항목\s*[:：]\s*값['\"”]?|키\s*-\s*값\s*형태)"
    r"[^\n.!?。]*[.!?。]?")


def with_directive(system_prompt: Optional[str]) -> str:
    """지시문에 한 줄을 붙인다(이미 있으면 그대로)."""
    base = (system_prompt or "").rstrip()
    if DIRECTIVE in base:
        return base
    return f"{base}\n\n[형식 문구]\n- {DIRECTIVE}".strip()


def scrub(markdown: str) -> Tuple[str, List[str]]:
    """새어 나온 문장을 지운다. 문장만 있던 줄은 줄째 지운다. (본문, 지운 문장)."""
    removed: List[str] = []

    def _cut(m: "re.Match[str]") -> str:
        removed.append(m.group(0).strip())
        return ""

    out = []
    for line in (markdown or "").split("\n"):
        new = _LEAK.sub(_cut, line)
        if new != line and not new.strip():
            continue  # 그 문장뿐이던 줄
        out.append(new.rstrip() if new != line else new)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)), removed
