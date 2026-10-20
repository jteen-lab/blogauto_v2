"""F3. 말투 고정 — 모든 문장은 '~습니다/~요' 존댓말.

슈마즈 시험(2026-10-20) haiku 8380 글이 '~다.' 말투로 나왔다. 블로그의
다른 글은 '~습니다' 라 한 블로그 안에서 말투가 갈린다.

  1) 글쓰기 지시문(system_prompt)에 한 줄을 붙인다.
  2) 저장 전 '다.'로 끝나는 평서문(습니다·니다 제외) 비율을 잰다.
     기준(기본 20%)을 넘으면 같은 모델로 말투만 한 번 고쳐 쓰고,
     그래도 넘으면 보류한다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (F3)
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from ....core.logger import get_logger

logger = get_logger("fact_gate", "app.log")

DIRECTIVE = ("모든 문장은 '~습니다/~요' 존댓말로 쓴다. "
             "'~다.'로 끝내지 않는다.")
DEFAULT_MAX_RATIO = 0.2

_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
_MD = re.compile(r"[*_`#>|]|^\s*(?:[-+]|\d+\.)\s+", re.M)


def with_directive(system_prompt: Optional[str]) -> str:
    """지시문에 말투 한 줄을 붙인다(이미 있으면 그대로)."""
    base = (system_prompt or "").rstrip()
    if DIRECTIVE in base:
        return base
    return f"{base}\n\n[말투]\n- {DIRECTIVE}".strip()


def sentences(markdown: str) -> List[str]:
    """마침표로 끝나는 문장(표·제목·짧은 조각 제외)."""
    out = []
    for line in (markdown or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "```")):
            continue
        for piece in _SPLIT.split(_MD.sub("", s)):
            piece = piece.strip()
            if len(piece) >= 8 and piece.endswith("."):
                out.append(piece)
    return out


def plain_da(sentence: str) -> bool:
    """'다.'로 끝나는 평서문인가('습니다.'·'니다.' 는 존댓말이라 제외)."""
    s = sentence.rstrip()
    return s.endswith("다.") and not s.endswith("니다.")


def ratio(markdown: str) -> Tuple[float, int, int]:
    """(비율, '다.' 문장 수, 전체 문장 수)."""
    all_s = sentences(markdown)
    da = sum(1 for s in all_s if plain_da(s))
    return (da / len(all_s) if all_s else 0.0), da, len(all_s)


def _rewrite_prompt(markdown: str) -> str:
    """말투만 바꾸라는 지시."""
    return (
        "아래 글의 말투만 존댓말로 바꾸세요.\n"
        "- '~다.'로 끝나는 문장을 '~습니다.' 또는 '~요.'로 바꿉니다.\n"
        "- 내용·숫자·순서·소제목·표·목록·마크다운 기호는 그대로 둡니다.\n"
        "- 설명이나 머리말 없이 고친 글만 출력합니다.\n\n"
        f"[글]\n{markdown}")


async def enforce(ai_service: Any, markdown: str, provider: str,
                  model: Optional[str], max_tokens: int,
                  max_ratio: float = DEFAULT_MAX_RATIO
                  ) -> Tuple[str, Optional[str], dict]:
    """비율을 재고 넘으면 한 번 고쳐 쓴다.

    Returns:
        (본문, 보류 사유|None, 기록)
    """
    r0, da, total = ratio(markdown)
    rec = {"ratio": round(r0, 3), "da": da, "sentences": total,
           "rewritten": False}
    if r0 <= max_ratio:
        return markdown, None, rec
    logger.warning("[FACT_GATE:F3] '다.' 비율 %.0f%% (%d/%d) → 말투 고쳐 쓰기",
                   r0 * 100, da, total)
    fixed = markdown
    try:
        res = await ai_service.generate(
            prompt=_rewrite_prompt(markdown), provider=provider, model=model,
            max_tokens=max_tokens, temperature=0.2)
        text = ((res or {}).get("content") or "").strip()
        # 반 넘게 줄었으면 글을 잘라 먹은 것이다. 버린다.
        if text and len(text) >= len(markdown) * 0.6:
            fixed = text
            rec["rewritten"] = True
    except Exception as e:  # noqa: BLE001 — 실패하면 아래 재측정이 판정
        logger.warning("[FACT_GATE:F3] 고쳐 쓰기 실패 | %s", e)
    r1, da1, total1 = ratio(fixed)
    rec.update(after=round(r1, 3), da_after=da1)
    if r1 > max_ratio:
        reason = (f"말투 기준 미달 — '다.' 문장 {da1}/{total1} "
                  f"({r1:.0%}, 기준 {max_ratio:.0%})")
        return fixed, reason, rec
    return fixed, None, rec
