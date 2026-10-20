"""F2. 사실 검사 — 다른 모델(haiku)이 한 번 더 읽고 틀린 문장만 고친다.

슈마즈 시험(2026-10-20)에서 sonnet 도 '신협은 예금보험공사 보호'를,
haiku 는 '펀드 분배금 재투자 시 금융소득 제외' 같은 틀린 절세 조언을 썼다.
금융·세금 글은 틀리면 치명적이라 다 쓴 뒤 한 번 더 읽힌다.

  1) 검사 모델(기본 claude-haiku-4-5)이 본문 + 참고 자료를 보고
     틀렸거나 자료로 확인 안 되는 문장만 JSON 으로 뽑는다.
  2) 확실도 '높음' 이 있으면 그 문장들만 글쓰기 모델로 고친다
     (고칠 수 없으면 문장 삭제).
  3) 다시 검사해 '높음' 이 남으면 보류.

순서도: docs/flowcharts/shoemaz_fact_gate.md (F2)
"""
from __future__ import annotations

import difflib
import json
import re
from typing import Any, List, Optional, Tuple

from ....core.logger import get_logger

logger = get_logger("fact_gate", "app.log")

HIGH = "높음"
REF_LIMIT = 9000

CHECK_PROMPT = """당신은 한국 금융·세금 글의 사실 검토자입니다.
[본문]에서 기관 이름·숫자·세율·한도·시행 시기·제도 설명 가운데
틀렸거나 [참고 자료]로 확인되지 않는 문장만 고르세요.

- "sentence" 는 본문에서 글자 그대로 복사합니다(고치지 마세요).
- "confidence": "높음" = 한국 제도상 분명히 틀렸거나 참고 자료와 어긋남,
  "중간" = 참고 자료로 확인은 안 되지만 틀렸다고 단정할 수 없음,
  "낮음" = 표현이 모호한 정도.
- 예: 신협·새마을금고·우체국의 보호 주체를 예금보험공사로 쓴 문장,
  예금자보호 한도 1억 원의 시행 시기(2025년 9월 1일)를 틀리게 쓴 문장,
  가산세율·원천징수세율을 틀리게 쓴 문장, 과세 대상을 비과세로 쓴 문장.
- [확정 사실]·[참고 자료]가 당신의 기억과 다르면 그쪽이 맞습니다(제도는 자주 바뀝니다).
  [확정 사실]과 맞는 문장은 고르지 않습니다.
- 같은 잘못이 여러 문장에 있으면 문장마다 따로 적습니다.
- 문장 속 큰따옴표(")는 작은따옴표(')로 바꿔 적습니다.
- 문제가 없으면 items 를 빈 목록으로 둡니다.
- JSON 만 출력합니다:
{{"items":[{{"sentence":"...","reason":"...","confidence":"높음|중간|낮음","fix_hint":"..."}}]}}
{facts}
[참고 자료]
{refs}

[본문]
{body}"""

FIX_PROMPT = """아래 [고칠 문장]은 금융·세금 블로그 글에서 사실 검사에 걸린 문장입니다.
[참고 자료]와 한국 제도에 맞게 문장 하나씩 고쳐 쓰세요.
- 존댓말(~습니다/~요)로, 원래 문장과 비슷한 길이로 씁니다.
- 확실히 고칠 수 없으면 "replacement" 를 빈 문자열로 둡니다(문장 삭제).
- JSON 만 출력합니다:
{{"fixes":[{{"sentence":"원래 문장 그대로","replacement":"고친 문장"}}]}}
{facts}
[참고 자료]
{refs}

[고칠 문장]
{items}"""


def parse_json(text: str) -> dict:
    """모델 답에서 JSON 객체를 꺼낸다. 못 꺼내면 빈 dict."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        # strict=False — 문자열 속 줄바꿈을 받아 준다(haiku 가 자주 넣는다)
        return json.loads(t[start:end + 1], strict=False)
    except json.JSONDecodeError:
        return {}


def facts_block(facts) -> str:
    """모듈 설정의 확정 사실 목록 → 지시문 덩어리(없으면 빈 줄)."""
    rows = [str(f).strip() for f in facts or [] if str(f).strip()]
    return ("\n[확정 사실 — 모델 기억보다 우선]\n" + "\n".join(f"- {r}" for r in rows)
            + "\n") if rows else ""


def _norm(s: str) -> str:
    return re.sub(r"[\s*_`]", "", s or "")


def locate(markdown: str, sentence: str) -> Optional[Tuple[int, int]]:
    """본문에서 문장 자리를 찾는다. 그대로 없으면 비슷한 문장(0.85↑)."""
    i = markdown.find(sentence)
    if i >= 0:
        return i, i + len(sentence)
    target, best, spot = _norm(sentence), 0.0, None
    if not target:
        return None
    for m in re.finditer(r"[^\n.!?]+[.!?]?", markdown):
        piece = m.group(0)
        r = difflib.SequenceMatcher(None, _norm(piece), target).ratio()
        if r > best:
            best, spot = r, (m.start() + len(piece) - len(piece.lstrip()),
                             m.end())
    return spot if best >= 0.85 else None


def apply_fixes(markdown: str, fixes: List[dict]) -> Tuple[str, List[dict]]:
    """고친 문장을 본문에 넣는다. (본문, 적용 기록)."""
    done = []
    for f in fixes:
        src = str(f.get("sentence") or "").strip()
        new = str(f.get("replacement") or "").strip()
        spot = locate(markdown, src) if src else None
        if not spot:
            done.append({"sentence": src, "applied": False})
            continue
        a, b = spot
        markdown = markdown[:a] + new + markdown[b:]
        done.append({"sentence": src, "replacement": new, "applied": True})
    return re.sub(r"[ \t]{2,}", " ", markdown), done


async def check(ai_service: Any, body: str, refs: str, provider: str,
                model: str, facts=None) -> Optional[List[dict]]:
    """검사 모델 호출. 호출 실패면 None(검사 못 함), 문제 없으면 []."""
    prompt = CHECK_PROMPT.format(refs=(refs or "(없음)")[:REF_LIMIT],
                                 body=body, facts=facts_block(facts))
    try:
        res = await ai_service.generate(prompt=prompt, provider=provider,
                                        model=model, max_tokens=2000,
                                        temperature=0.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("[FACT_GATE:F2] 검사 호출 실패 | %s", e)
        return None
    if not res:
        return None
    data = parse_json(res.get("content") or "")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        logger.warning("[FACT_GATE:F2] 검사 답 해석 실패 | %s",
                       (res.get("content") or "")[:200])
        return None
    return [i for i in items if isinstance(i, dict) and i.get("sentence")]


async def fix(ai_service: Any, items: List[dict], refs: str, provider: str,
              model: Optional[str], facts=None) -> List[dict]:
    """'높음' 문장들을 글쓰기 모델로 고친다. 실패하면 빈 목록."""
    listing = "\n".join(
        f"- 문장: {i.get('sentence')}\n  이유: {i.get('reason')}\n"
        f"  힌트: {i.get('fix_hint') or ''}" for i in items)
    try:
        res = await ai_service.generate(
            prompt=FIX_PROMPT.format(refs=(refs or "(없음)")[:REF_LIMIT],
                                     items=listing, facts=facts_block(facts)),
            provider=provider, model=model, max_tokens=2000, temperature=0.2)
    except Exception as e:  # noqa: BLE001
        logger.warning("[FACT_GATE:F2] 고쳐 쓰기 호출 실패 | %s", e)
        return []
    fixes = parse_json((res or {}).get("content") or "").get("fixes")
    return [f for f in fixes or [] if isinstance(f, dict)]


def high(items: Optional[List[dict]]) -> List[dict]:
    """확실도 '높음' 만."""
    return [i for i in items or [] if str(i.get("confidence", "")).strip() == HIGH]
