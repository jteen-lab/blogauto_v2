"""생성기에서 맨 앞 검색어·최종 제목 검사를 잇는 자리(generator 가 길어 따로 둔다).

  lead_recombine  검색어 지시 붙여 재조합 → 맨 앞이 아니면 한 번 다시 → 그래도 아니면 규칙
  finalize        N4 최종 제목 지난 연도 빼기 + 본문 지시(검색어·연도) 모으기
  with_body       본문 프롬프트 끝에 붙일 지시를 설정 사본에 실어 보낸다

순서도: docs/flowcharts/title_lead_keyword.md (3. 재조합·맞춤·기록)
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from ...core.logger import get_logger
from . import lead_keyword
from .lead_keyword_pick import Candidate
from .title_lifecycle import title_keywords

logger = get_logger("lead_keyword", "app.log")

BODY_KEY = "_body_directives"
PAST_YEAR_NOTE = ("✦ 연도\n- 올해 기준이 확인되지 않은 숫자(금액·기준·인원 등)는 그 숫자의 "
                  "연도를 밝혀 과거형으로 쓸 것(예: '2025년에는 ○○원이었어요'). 올해도 같다고 단정하지 말 것")


async def lead_recombine(gen: Any, source_title: Any, settings: dict, provider: Any,
                         model: Optional[str], style: Any,
                         module_id: int) -> Tuple[Any, Optional[Candidate], str]:
    """재조합 결과, 고른 검색어, 반영 방식(instruction|retry|rule|cpa|none)."""
    kws = title_keywords(source_title)
    cpa = bool(getattr(source_title, "cpa_offer_id", None))
    title_settings, lead = await lead_keyword.apply(
        gen.db, gen.user_id, settings, source_title.title, kws, cpa=cpa)

    async def run() -> Any:
        return await gen.title_recombiner.recombine(
            original_title=source_title.title, module_id=module_id,
            provider=provider, model=model, style=style,
            # 핵심어가 빠지면 검색에 안 잡힌다(계획서 §4-5 B)
            keywords=kws,
            # 프롬프트 템플릿이 갈렸으면 제목 묶음도 그 번호를 쓴다
            settings_override=title_settings)

    result = await run()
    if lead is None:
        return result, None, "none"
    if cpa:
        return result, lead, "cpa"
    if lead_keyword.starts_with(result.recombined_title, lead.text):
        return result, lead, "instruction"
    logger.warning("[LEAD_KW] 맨 앞 검색어 미반영 → 한 번 다시 | 「%s」 | '%s'",
                   lead.text, (result.recombined_title or "")[:40])
    again = await run()
    if lead_keyword.starts_with(again.recombined_title, lead.text):
        return again, lead, "retry"
    fitted = lead_keyword.fit(again.recombined_title, lead.text)
    logger.warning("[LEAD_KW] 다시 해도 미반영 → 규칙으로 맞춤 | '%s' → '%s'",
                   (again.recombined_title or "")[:40], fitted[:40])
    again.recombined_title = fitted
    again.is_modified = True
    return again, lead, "rule"


def finalize(title: str, lead: Optional[Candidate], applied: str) -> Tuple[str, List[str]]:
    """N4 최종 제목 지난 연도 빼기 + 본문 지시 모으기."""
    from .topic_gate import strip_past_year

    notes: List[str] = []
    stripped = strip_past_year(title)
    if stripped:
        logger.info("[TOPIC_GATE] 최종 제목 지난 연도 뺌(N4) | '%s' → '%s'",
                    title[:40], stripped[:40])
        title = stripped
        notes.append(PAST_YEAR_NOTE)
    if lead is not None and applied not in ("cpa", "none") \
            and lead_keyword.starts_with(title, lead.text):
        notes.append(lead_keyword.body_directive(lead))
    return title, notes


def with_body(settings: dict, notes: List[str]) -> dict:
    """본문 지시를 실은 설정 사본(지시가 없으면 원본 그대로)."""
    if not notes:
        return settings
    return {**settings, BODY_KEY: list(settings.get(BODY_KEY) or []) + notes}


def body_notes(settings: dict) -> List[str]:
    """본문 프롬프트 끝에 붙일 지시(content_generator_helper 가 읽는다)."""
    return [n for n in (settings or {}).get(BODY_KEY) or [] if n]
