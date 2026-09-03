"""AI 배치 제안 — 후보어를 어느 하위주제에 넣을지.

규칙 기반 추천(§9-2)이 **무엇이 빠졌는지**를 찾는다. 여기서는 그것을
**어디에 넣을지**를 제안한다. 사람은 승인·거부만 한다.

신뢰도가 낮은 것은 보류함으로 보낸다 — 승인 목록을 어지럽히면 사람이
대충 승인하게 되고, 그러면 분류표가 망가진다.

앱에 이미 `anthropic` provider 가 있으므로 새 연동은 없다. **Claude Code
를 서버에 내장하지 않는다** — 같은 일을 하는 에이전트를 앱 안에 두는
쪽이 운영에 안전하다(계획서 §9-5).

계획서: docs/plans/title_tab_workplan.md §9-3
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ...core.logger import get_logger

logger = get_logger("taxonomy_ai", "app.log")

# 이보다 낮으면 보류함으로. 승인 목록을 깨끗하게 유지한다.
MIN_CONFIDENCE = 0.6

# 한 번에 물어볼 후보 수. 너무 많으면 응답이 잘린다.
BATCH_SIZE = 20

JSON_RE = re.compile(r"\[.*\]", re.S)


def build_prompt(candidates: List[dict], tree: List[dict]) -> str:
    """분류표와 후보를 함께 준다. 트리를 모르면 엉뚱한 곳에 넣는다."""
    lines = []
    for topic in tree:
        for sub in topic.get("subtopics") or []:
            sample = ", ".join(k["name"] for k in (sub.get("keywords") or [])[:5])
            lines.append(f"- id={sub['id']} | {topic['name']} > {sub['name']}"
                         + (f" (예: {sample})" if sample else ""))

    terms = "\n".join(
        f"- \"{c.get('term', '')}\" ({c.get('count', 0)}건) 예: "
        + " / ".join((c.get("samples") or [])[:2])
        for c in candidates)

    return (
        "블로그 제목 분류표에 넣을 자리를 정해 주세요.\n\n"
        "[현재 하위주제 목록]\n" + "\n".join(lines) + "\n\n"
        "[분류되지 않은 제목에서 자주 나온 말]\n" + terms + "\n\n"
        "각 말이 어느 하위주제에 속하는지 판단하세요.\n"
        "**어디에도 맞지 않으면 subtopic_id 를 null 로 두세요.** 억지로 "
        "넣으면 분류표가 망가집니다.\n\n"
        "JSON 배열로만 답하세요:\n"
        '[{"term": "말", "subtopic_id": 3, "confidence": 0.9, '
        '"reason": "근거"}]')


def parse(answer: str) -> List[Dict[str, Any]]:
    """응답에서 배열만 꺼낸다. 설명이 섞여 와도 견딘다."""
    if not answer:
        return []
    match = JSON_RE.search(answer)
    if not match:
        return []
    try:
        parsed = json.loads(match.group())
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []

    out = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        term = str(row.get("term") or "").strip()
        if not term:
            continue
        try:
            confidence = float(row.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        subtopic_id = row.get("subtopic_id")
        try:
            subtopic_id = int(subtopic_id) if subtopic_id is not None else None
        except (TypeError, ValueError):
            subtopic_id = None
        out.append({"term": term, "subtopic_id": subtopic_id,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "reason": str(row.get("reason") or "")[:200]})
    return out


def split(rows: List[dict],
          threshold: float = MIN_CONFIDENCE) -> Dict[str, List[dict]]:
    """승인 목록과 보류함으로 가른다.

    자리를 못 찾은 것(`subtopic_id` 없음)도 보류함이다 — 억지로 넣는
    것보다 사람이 보는 편이 낫다.
    """
    approved, held = [], []
    for row in rows:
        if row.get("subtopic_id") and row.get("confidence", 0) >= threshold:
            approved.append(row)
        else:
            held.append(row)
    return {"approved": approved, "held": held}


class AiTaxonomySuggester:
    """후보어의 자리를 AI 에게 묻는다."""

    def __init__(self, ask: Any = None):
        # ask(prompt) -> str. 없으면 아무것도 제안하지 않는다.
        self.ask = ask
        self.last_error: Optional[str] = None

    async def run(self, candidates: List[dict], tree: List[dict],
                  threshold: float = MIN_CONFIDENCE) -> Dict[str, Any]:
        """한 배치. 실패는 빈 결과 — 사람이 규칙 기반으로 계속할 수 있다."""
        if self.ask is None:
            self.last_error = "AI 제공자가 지정되지 않았습니다"
            return {"approved": [], "held": [], "error": self.last_error}
        if not candidates:
            return {"approved": [], "held": [], "error": None}

        picked = candidates[:BATCH_SIZE]
        try:
            answer = await self.ask(build_prompt(picked, tree))
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)[:200]
            logger.warning("[TAXONOMY_AI] 실패 | %s", e)
            return {"approved": [], "held": [], "error": self.last_error}

        rows = parse(answer)
        # 후보에 없던 말을 AI 가 지어내는 경우가 있다. 걸러 낸다.
        allowed = {c["term"] for c in picked}
        rows = [r for r in rows if r["term"] in allowed]

        result = split(rows, threshold)
        logger.info("[TAXONOMY_AI] 후보 %d개 → 승인 %d · 보류 %d",
                    len(picked), len(result["approved"]), len(result["held"]))
        return {**result, "error": None}
