"""제목 맨 앞 검색어 — 사람들이 실제로 치는 짧은 말을 검색량으로 골라 재조합에 준다.

수작남 마케팅 진단(2026-10-19, 형 승인): 제목이 '~은 무엇일까 / ~알아보기' 같은
질문·안내형이라 실제 검색어(예: '관악우체국 근무시간')와 맞는 부분이 적었다.
재조합 AI 에 "핵심어를 지켜라"만 주면 어느 말이 검색되는지 모른다.

모듈 settings 최상위 `title_lead_keyword: true` 일 때만 켠다.
    1. 원본 정식 제목 앞 낱말 1~3개 묶음 + 제목 핵심어를 후보로
    2. 네이버 검색광고 한 달 검색량을 한 번 조회(최대 5개, 호출 1회)
    3. 두 낱말 이상 묶음 중 검색량이 가장 많은 것(MIN_VOLUME 이상) → 없으면 한 낱말
    4. 재조합 지시 끝에 "맨 앞을 「검색어」로 시작" 한 줄을 붙인다(DB 설정은 안 바꿈)
조회 실패·후보 없음이면 아무것도 붙이지 않는다(생성은 그대로).

순서도: docs/flowcharts/title_recombine_rotation.md (맨 앞 검색어)
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import get_logger
from .link_relevance import _strip_suffix

logger = get_logger("lead_keyword", "app.log")

SETTINGS_KEY = "title_lead_keyword"
MIN_VOLUME = 30
MAX_CANDIDATES = 5
_PUNCT = re.compile(r"[^\w가-힣\s]")


def candidates(title: str, keywords: Optional[List[str]] = None) -> List[str]:
    """검색량을 물어볼 후보(앞 낱말 묶음 → 핵심어 순, 중복 없이 최대 5개)."""
    words = _PUNCT.sub(" ", title or "").split()
    out: List[str] = []
    for n in (2, 3, 1):
        if len(words) >= n:
            head = words[:n - 1] + [_strip_suffix(words[n - 1]) or words[n - 1]]
            out.append(" ".join(head))
    out.extend(str(k).strip() for k in (keywords or []) if str(k).strip())
    seen, uniq = set(), []
    for c in out:
        key = c.replace(" ", "")
        if len(key) >= 2 and key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq[:MAX_CANDIDATES]


def choose(volumes: Dict[str, int], cands: List[str]) -> Optional[Tuple[str, int]]:
    """두 낱말 이상 묶음 우선, 없으면 세 글자 이상 한 낱말. 검색량 MIN_VOLUME 이상만."""
    scored = [(c, volumes.get(c.replace(" ", "").lower(), 0)) for c in cands]
    multi = [x for x in scored if " " in x[0] and x[1] >= MIN_VOLUME]
    single = [x for x in scored if " " not in x[0] and len(x[0]) >= 3
              and x[1] >= MIN_VOLUME]
    pool = multi or single
    return max(pool, key=lambda x: x[1]) if pool else None


def instruction(keyword: str, volume: int) -> str:
    """재조합 지시에 붙일 줄."""
    return (f"\n- 제목 맨 앞을 「{keyword}」(네이버 한 달 검색 약 {volume:,}회, "
            "사람들이 실제로 치는 말)로 시작할 것. 띄어쓰기도 그대로 둔다\n"
            "- 그 뒤에는 무엇을 알 수 있는지(비교·상황·선택 기준)를 붙인다. "
            "'~은 무엇일까', '~알아보기', '~방법 안내', '~무엇인가요' 같은 꼬리는 쓰지 않는다")


async def _volumes(db: Any, user_id: int, cands: List[str]) -> Dict[str, int]:
    """후보 검색량(공백 뺀 소문자 → 합계). 설정 없거나 실패면 빈 dict."""
    from sqlalchemy import select

    from ...models.user_settings import UserSettings
    from ..naver_ads_service import NaverAdsService

    settings = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    service = NaverAdsService(settings)
    if not settings or not service.is_configured():
        return {}
    result = await service.get_keyword_stats(cands, include_related=False)
    if not result.get("success"):
        logger.warning("[LEAD_KW] 검색량 조회 실패 | %s", result.get("error"))
        return {}
    return {(r.get("keyword") or "").replace(" ", "").lower():
            int(r.get("total_search_volume") or 0)
            for r in result.get("keywords") or []}


async def apply(db: Any, user_id: int, settings: Optional[dict], title: str,
                keywords: Optional[List[str]] = None) -> Tuple[Optional[dict], Optional[str]]:
    """켜져 있으면 재조합용 설정 사본에 맨 앞 검색어 지시를 붙인다.

    Returns:
        (재조합에 넘길 설정, 고른 검색어 또는 None). 꺼져 있으면 원본 설정 그대로.
    """
    if not (settings or {}).get(SETTINGS_KEY) or "title_recombine" not in settings:
        return settings, None
    try:
        cands = candidates(title, keywords)
        picked = choose(await _volumes(db, user_id, cands), cands) if cands else None
    except Exception as e:  # noqa: BLE001 — 검색량 실패로 생성을 막지 않는다
        logger.warning("[LEAD_KW] 판정 실패(그대로 진행) | %s", e)
        return settings, None
    if not picked:
        logger.info("[LEAD_KW] 검색량 있는 후보 없음 | '%s' | %s", title[:30], cands)
        return settings, None
    out = copy.deepcopy(settings)
    tr = out["title_recombine"]
    tr["custom_prompt"] = (tr.get("custom_prompt") or "") + instruction(*picked)
    logger.info("[LEAD_KW] 맨 앞 검색어 「%s」(%d회) | '%s'", picked[0], picked[1], title[:30])
    return out, picked[0]


def starts_with(title: str, keyword: Optional[str]) -> bool:
    """재조합 결과가 그 검색어로 시작하나(띄어쓰기 무시)."""
    if not keyword:
        return True
    return (title or "").replace(" ", "").startswith(keyword.replace(" ", ""))
