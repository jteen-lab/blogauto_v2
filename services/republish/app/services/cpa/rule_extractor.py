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

# provider 를 안 넘기면 AIService 가 "제공자 미지정" 으로 호출조차 하지 않는다.
# 실측(2026-09-08): 이 때문에 이사스토리 추출이 통째로 0건이었다.
DEFAULT_PROVIDERS = ("openai", "google", "deepseek")


async def _pick_provider(db) -> Optional[str]:
    """쓸 수 있는 AI 를 고른다. 활성 키가 있는 것 중 앞선 것."""
    try:
        from sqlalchemy import select

        from ...models.ai_api_key import AIApiKey

        rows = (await db.execute(
            select(AIApiKey.provider).where(AIApiKey.status == "active")
        )).scalars().all()
        alive = {str(r) for r in rows}
        for name in DEFAULT_PROVIDERS:
            if name in alive:
                return name
        return next(iter(alive), None)
    except Exception as e:  # noqa: BLE001
        logger.warning("[CPA_EXTRACT] AI 키 조회 실패 | %s", e)
        return None

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

**광고주 소개 문단은 반드시 content_source 로 만드세요.** 글에 쓸 사실이
거기 있습니다. 여러 줄이면 줄마다 하나씩 만드세요.
"이사 불가지역", "나이 제한", "○일 이후 미승인" 같은 대상 제한은 conversion
으로 만드세요. 대상이 아닌 사람을 부르면 수익이 0 이 됩니다.
"~할 수 있습니다", "~상이할 수 있습니다" 같은 고지는 required_topic 입니다.
다운로드 링크·이미지 자료는 asset 입니다.

유형을 고를 때 아래를 따르세요. 전부 must_not_include 로 몰면 안 됩니다.
- 후기·경험담·비용 공개처럼 **글의 소재**를 막는 것 → forbidden_topic
- 전화번호·할인율·건수처럼 **형태**를 막는 것 → pattern (정규식으로)
- 검색광고·SNS·카페처럼 **어디에 올릴지** → channel
- 배너·이미지·다운로드 자료 → asset
- 낱말 하나를 막는 것만 must_not_include
- 광고주가 알려 주는 사실(위치·경력·장비·프로그램) → content_source
- "~을 명시하세요" 처럼 내용을 요구하는 것 → required_topic

인사말("캠페인 많은 홍보 부탁드립니다")과 제목 줄만 결과에서 빼세요.
나머지는 되도록 규칙으로 만드세요 — 빠진 줄은 검사되지 않습니다.

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

    target = str(rule.get("target") or "")[:100]
    value = str(rule.get("value") or "")[:300]
    # 사실 정보·고지는 value 를 비우고 target 만 채워 오는 일이 잦다.
    # 비어 있으면 프롬프트에도 게이트에도 쓸 수 없다.
    if not value and kind in ("content_source", "required_topic",
                              "content_axis", "conversion", "advisory"):
        value = (target or quote)[:300]

    return {
        "type": kind, "scope": scope, "target": target, "value": value,
        "source_quote": quote[:300], "severity": severity,
    }


# 따옴표를 빼먹은 값. 실측(2026-09-08): openai 가 {"type": required_topic}
# 처럼 돌려줘 파싱이 통째로 실패했고, 조용히 규칙 0건이 됐다.
_BARE = re.compile(r'(:\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*[,}])')


def _repair(text: str) -> str:
    """따옴표 없는 값에 따옴표를 씌운다. true/false/null 은 그대로 둔다."""
    def fix(m):
        word = m.group(2)
        if word in ("true", "false", "null"):
            return m.group(0)
        return f'{m.group(1)}"{word}"{m.group(3)}'

    return _BARE.sub(fix, text)


def _parse_response(text: str, lines: Sequence[str]) -> List[dict]:
    """AI 응답에서 JSON 배열을 건져낸다. 깨져 있으면 한 번 고쳐 본다."""
    body = (text or "").strip()
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        return []
    chunk = body[start:end + 1]
    try:
        raw = json.loads(chunk)
    except Exception:  # noqa: BLE001
        try:
            raw = json.loads(_repair(chunk))
            logger.info("[CPA_EXTRACT] 깨진 JSON 복구 성공")
        except Exception:  # noqa: BLE001
            logger.warning("[CPA_EXTRACT] JSON 파싱 실패 | %s", chunk[:120])
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        found = _valid(item, lines)
        if found:
            out.append(found)
    return out


def _text_of(result: Any) -> str:
    """AIService 응답에서 본문을 꺼낸다. dict·객체·문자열 다 온다."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("content") or result.get("text") or "")
    return str(getattr(result, "content", None)
               or getattr(result, "text", "") or "")


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
         "coverage": 0.0~1.0, "ai_error": str}
        `unmatched` 는 규칙이 되지 못한 줄이다. **검사되지 않는다.**
        `ai_error` 가 있으면 AI 추출이 실패한 것이다 — 법정 사전만 남는다.
    """
    lines = _lines(raw_text)
    if not lines:
        return {"rules": [], "unmatched": [], "verticals": [],
                "coverage": None, "ai_error": ""}

    if not provider:
        provider = await _pick_provider(getattr(ai_service, "db", None))
    if not provider:
        logger.error("[CPA_EXTRACT] 쓸 수 있는 AI 가 없다 — 추출 불가")
        return {"rules": [], "unmatched": lines, "verticals": [],
                "coverage": 0.0,
                "ai_error": "활성 AI 키가 없어 규칙을 뽑지 못했습니다"}

    rules: List[dict] = []
    ai_error = ""
    for start in range(0, len(lines), BATCH):
        chunk = lines[start:start + BATCH]
        numbered = "\n".join(f"{start + i + 1}. {line}"
                             for i, line in enumerate(chunk))
        try:
            # 규칙 추출은 창의성이 필요 없다. 낮은 온도로 고정한다.
            result = await ai_service.generate(
                prompt=PROMPT % numbered, provider=provider, model=model,
                max_tokens=4000, temperature=0.1)
        except Exception as e:  # noqa: BLE001 — 등록 자체는 막지 않는다
            logger.warning("[CPA_EXTRACT] 호출 실패 | %s", e)
            ai_error = f"AI 호출 실패: {e}"
            continue
        if not result:
            # AIService 는 실패를 None 으로 돌려준다. 조용히 넘기면
            # "규칙이 없는 오퍼" 로 보여 사용자가 원인을 알 수 없다.
            ai_error = "AI 응답이 비었습니다 (제공자·키 확인 필요)"
            logger.error("[CPA_EXTRACT] 빈 응답 | provider=%s", provider)
            continue
        text = _text_of(result)
        found = _parse_response(str(text), lines)
        if not found:
            # 형식이 깨진 것이지 내용이 없는 게 아니다. 한 번 더 부른다.
            try:
                retry = await ai_service.generate(
                    prompt=PROMPT % numbered + "\n\n반드시 올바른 JSON 만 출력하세요.",
                    provider=provider, model=model,
                    max_tokens=4000, temperature=0.0)
            except Exception as e:  # noqa: BLE001
                retry = None
                ai_error = f"재시도 실패: {e}"
            if retry:
                found = _parse_response(str(_text_of(retry)), lines)
            if not found:
                ai_error = ai_error or "AI 응답을 규칙으로 바꾸지 못했습니다"
        rules.extend(found)

    used = {r["source_quote"] for r in rules if r["source_quote"]}
    unmatched = [line for line in lines if line not in used]

    verticals = verticals_in(raw_text)
    rules.extend(legal_rules(verticals))
    rules.extend(generic_warnings())

    coverage = round(1 - len(unmatched) / len(lines), 3) if lines else None
    logger.info("[CPA_EXTRACT] 줄 %d · 규칙 %d · 미분류 %d · 커버리지 %s%% · 업종 %s",
                len(lines), len(rules), len(unmatched),
                int((coverage or 0) * 100), verticals)

    if not any(r for r in rules
               if not str(r.get("source_quote", "")).startswith("[법정]")):
        ai_error = ai_error or "AI 가 규칙을 하나도 만들지 못했습니다"

    return {"rules": rules, "unmatched": unmatched,
            "verticals": verticals, "coverage": coverage,
            "ai_error": ai_error}
