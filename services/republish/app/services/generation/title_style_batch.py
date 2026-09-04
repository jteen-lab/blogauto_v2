"""스타일별 제목을 **한 번에** 만든다.

스타일마다 따로 호출하면 서로를 모른다. 같은 프롬프트에 스타일 한 줄만
바뀌니 비슷한 답이 나온다 — 실제로 다섯 스타일이 거의 같은 제목으로
수렴했다.

한 번에 물으면 AI 가 **서로 겹치지 않게** 쓸 수 있고, 호출도 1/5 로 준다
(8초 → 2초대).

파싱이 실패하면 호출부가 스타일별 개별 호출로 돌아간다. 한 번 실패로
아무것도 못 만드는 것보다 낫다.

계획서: docs/plans/title_tab_workplan.md §4-5
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

JSON_RE = re.compile(r"\[.*\]", re.S)

# 한 번에 만들 스타일 수 상한. 너무 많으면 응답이 잘린다.
MAX_STYLES = 8


def build_prompt(base_prompt: str, styles: List[str],
                 labels: Dict[str, str],
                 instructions: Dict[str, Optional[str]]) -> str:
    """스타일 목록을 한 프롬프트로 묶는다.

    `base_prompt` 는 스타일 지시를 뺀 공통 부분이다(원본 제목·규칙·
    추가 지시사항).
    """
    lines = []
    for code in styles:
        text = instructions.get(code) or ""
        lines.append(f'- {code} ({labels.get(code, code)}): {text}')

    return (
        base_prompt
        + "\n\n아래 스타일마다 제목을 **하나씩** 쓰세요.\n"
        + "\n".join(lines)
        + "\n\n**각 제목은 서로 뚜렷하게 달라야 합니다.** 같은 표현을 "
          "돌려쓰지 말고, 그 스타일에만 맞는 형태로 쓰세요.\n"
          "스타일 지시가 위 규칙과 충돌하면 스타일을 우선합니다.\n\n"
          "JSON 배열로만 답하세요:\n"
          '[{"style": "코드", "title": "제목"}]'
    )


def parse(answer: str, styles: List[str]) -> Dict[str, str]:
    """응답에서 스타일별 제목을 꺼낸다.

    설명이 섞여 와도 배열만 찾아 읽는다. 요청하지 않은 스타일은 버린다 —
    AI 가 코드를 지어내는 경우가 있다.
    """
    if not answer:
        return {}
    match = JSON_RE.search(answer)
    if not match:
        return {}
    try:
        rows = json.loads(match.group())
    except (TypeError, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}

    allowed = set(styles)
    out: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("style") or "").strip()
        title = str(row.get("title") or "").strip()
        if code in allowed and title and code not in out:
            out[code] = title
    return out


def is_complete(parsed: Dict[str, str], styles: List[str]) -> bool:
    """요청한 스타일이 모두 왔는가.

    일부만 오면 개별 호출로 돌아간다 — 빠진 스타일을 빈칸으로 두면
    사용자가 무엇이 실패했는지 알 수 없다.
    """
    return all(code in parsed for code in styles)
