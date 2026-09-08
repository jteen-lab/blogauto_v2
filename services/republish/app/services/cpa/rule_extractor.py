"""원문 자유 서술 → 규칙.

애드릭스 고정 서식은 `offer_parser` 가 규칙으로 뽑는다. 여기는 **광고주가
자유롭게 쓴 부분**을 다룬다. 업종마다 형식이 제각각이라 AI 를 쓴다.

**AI 가 모든 문장을 규칙으로 바꾸리라 기대하지 않는다.** 못 바꾼 문장을
그대로 돌려주고 화면이 보여준다. 유입 분석에서 매칭률 0%가 로그에만 찍혀
아무도 몰랐던 일을 반복하지 않는다.

순서도: docs/flowcharts/cpa_offer.md
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from ...core.logger import get_logger
from ...models.cpa_offer import RULE_SCOPES, RULE_TYPES
from .lexicon import generic_warnings, legal_rules, verticals_in

logger = get_logger("cpa_rule_extractor", "app.log")

# 고정 서식 절. 여기부터는 offer_parser 담당이라 AI 에게 주지 않는다.
_FIXED_SECTIONS = ("전환 정보", "접수 항목", "대가성 문구 표시")

# 문장 분해. 줄바꿈이 곧 항목인 문서라 줄 단위가 낫다.
_SPLIT = re.compile(r"[\r\n]+")

# 규칙이 될 수 없는 줄 — 장식·구분선·빈 항목
_NOISE = re.compile(r"^[\s*※#\-=~_·●○◆▶★☆\d\.\)\(]*$")

# 한 번에 보낼 최대 줄 수. 너무 길면 AI 가 뒤쪽을 흘린다.
BATCH = 60

PROMPT = """다음은 CPA 제휴 마케팅 프로모션의 광고주 안내문입니다.
각 줄을 "글을 쓸 때 지켜야 할 규칙"으로 바꾸세요.

규칙 유형은 아래 중 하나여야 합니다.
- must_include: 반드시 넣어야 할 문구
- must_not_include: 쓰면 안 되는 낱말
- required_topic: 반드시 다뤄야 할 내용(문자열이 아니라 내용)
- forbidden_topic: 다루면 안 되는 주제
- replace: 이 표현 대신 저 표현을 쓰라
- position: 문구를 어디에 둘지
- pattern: 정규식으로 막을 형태(수치·전화번호 등)
- format: 표기 형식(글자 크기 등)
- conditional: X를 쓰면 Y도 반드시
- channel: 홍보해도 되는/안 되는 매체
- asset: 쓸 수 있는 이미지·자료
- link_policy: 링크 구성 제약
- conversion: 전환·타겟 조건
- content_axis: 추천 키워드·소재
- content_source: 글에 쓸 사실 정보
- advisory: 기계가 검사할 수 없는 당부

범위(scope)는 title, keywords, body, images, all 중 하나입니다.
원문이 "제목에"라고 했으면 title, "금지키워드"라고 했으면 keywords,
범위를 밝히지 않았으면 all 입니다.

강도(severity)는 block(어기면 발행 불가), warn(경고), review(사람 확인)입니다.
법 위반이 되는 것은 block, 권고는 review 입니다.

규칙으로 바꿀 수 없는 줄(인사말·소개 문장 등)은 결과에 넣지 마세요.

JSON 배열만 출력하세요. 설명하지 마세요.
[{"line": 원문줄번호, "type": "...", "scope": "...", "target": "...",
  "value": "...", "severity": "..."}]

--- 안내문 ---
%s"""


def _lines(text: str) -> List[str]:
    """규칙이 될 수 있는 줄만 남긴다."""
    body = text or ""
    for marker in _FIXED_SECTIONS:
        if marker in body:
            body = body.split(marker, 1)[0]
    out: List[str] = []
    for raw in _SPLIT.split(body):
        line = raw.strip()
        if len(line) < 4 or _NOISE.match(line):
            continue
        out.append(line)
    return out


def _valid(rule: Any, lines: Sequence[str]) -> Optional[dict]:
    """AI 응답 한 건을 검사해 정규화한다. 이상하면 버린다."""
    if not isinstance(rule, dict):
        return None
    kind = str(rule.get("type") or "").strip()
    if kind not in RULE_TYPES:
        return None
    scope = str(rule.get("scope") or "all").strip()
    if scope not in RULE_SCOPES:
        scope = "all"          # 범위를 모르면 가장 넓게 잡는다
    severity = str(rule.get("severity") or "block").strip()
    if severity not in ("block", "warn", "review"):
        severity = "block"

    index = rule.get("line")
    quote = ""
    if isinstance(index, int) and 0 <= index - 1 < len(lines):
        quote = lines[index - 1]

    return {
        "type": kind, "scope": scope,
        "target": str(rule.get("target") or "")[:100],
        "value": str(rule.get("value") or "")[:300],
        "source_quote": quote[:300],
        "severity": severity,
    }


def _parse_response(text: str, lines: Sequence[str]) -> List[dict]:
    """AI 응답에서 JSON 배열을 건져낸다."""
    body = (text or "").strip()
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        raw = json.loads(body[start:end + 1])
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        found = _valid(item, lines)
        if found:
            out.append(found)
    return out


async def extract(ai_service: Any, raw_text: str,
                  provider: Optional[str] = None,
                  model: Optional[str] = None) -> Dict[str, Any]:
    """원문에서 규칙을 뽑는다.

    Args:
        ai_service: AIService
        raw_text: 프로모션 원문
        provider/model: 쓸 AI

    Returns:
        {"rules": [...], "unmatched": [...], "verticals": [...],
         "coverage": 0.0~1.0}
        `unmatched` 는 규칙이 되지 못한 줄이다. **검사되지 않는다.**
    """
    lines = _lines(raw_text)
    if not lines:
        return {"rules": [], "unmatched": [], "verticals": [], "coverage": None}

    rules: List[dict] = []
    for start in range(0, len(lines), BATCH):
        chunk = lines[start:start + BATCH]
        numbered = "\n".join(f"{start + i + 1}. {line}"
                             for i, line in enumerate(chunk))
        try:
            # 규칙 추출은 창의성이 필요 없다. 낮은 온도로 고정한다.
            result = await ai_service.generate(
                prompt=PROMPT % numbered, provider=provider, model=model,
                max_tokens=4000, temperature=0.1)
        except Exception as e:  # noqa: BLE001 — 추출 실패로 등록을 막지 않는다
            logger.warning("[CPA_EXTRACT] 호출 실패 | %s", e)
            continue
        text = result if isinstance(result, str) else (
            getattr(result, "content", None) or getattr(result, "text", "")
            or (result or {}).get("content", "")
            if isinstance(result, dict) else "")
        rules.extend(_parse_response(str(text), lines))

    used = {r["source_quote"] for r in rules if r["source_quote"]}
    unmatched = [line for line in lines if line not in used]

    verticals = verticals_in(raw_text)
    rules.extend(legal_rules(verticals))
    rules.extend(generic_warnings())

    coverage = round(1 - len(unmatched) / len(lines), 3) if lines else None
    logger.info("[CPA_EXTRACT] 줄 %d · 규칙 %d · 미분류 %d · 커버리지 %s%% · 업종 %s",
                len(lines), len(rules), len(unmatched),
                int((coverage or 0) * 100), verticals)

    return {"rules": rules, "unmatched": unmatched,
            "verticals": verticals, "coverage": coverage}
