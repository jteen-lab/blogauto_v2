"""제목 맨 앞 검색어 — 사람들이 실제로 치는 말을 검색량으로 골라 재조합에 준다.

수작남 마케팅 진단(2026-10-19, 형 승인): 제목이 '~은 무엇일까 / ~알아보기' 같은
질문·안내형이라 실제 검색어와 맞는 부분이 적었다. → 앞 낱말 묶음·핵심어 중
검색량이 가장 큰 말을 '맨 앞에 두라'고 재조합 지시에 붙였다.

N1 확장(2026-10-23, 마케팅 지시·형 승인): 118편 실측에서 핵심어로 웹문서 100위 안
14%. '고흥석류 효능'(10 미만) ↔ 사람들은 '석류 효능'(9,050). 후보를 연관 검색어·
수식어 뺀 묶음까지 넓히고(lead_keyword_pick), 바닥선 30 → 50, 맨 앞이 검색어가
아니면 한 번 다시·그래도 아니면 규칙으로 맞추고, 본문 첫 문단·소제목에도 넣게 한다.
글마다 고른 검색어·검색량·출처를 logs/lead_keyword.jsonl 에 남긴다(마케팅 순위 채점).

모듈 settings 최상위 `title_lead_keyword: true` 일 때만. 바닥선은 `title_lead_floor`
(기본 50). 조회 실패면 아무것도 붙이지 않는다(생성은 그대로).

순서도: docs/flowcharts/title_lead_keyword.md
"""
from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...core.logger import LoggerConfig, get_logger
from . import lead_keyword_pick as pick
from .lead_keyword_pick import MIN_VOLUME, Candidate

logger = get_logger("lead_keyword", "app.log")

SETTINGS_KEY = "title_lead_keyword"
FLOOR_KEY = "title_lead_floor"
JOURNAL = "lead_keyword.jsonl"
CACHE_SEC = 3600
REST_CHARS = 30
_CACHE: Dict[Tuple[str, int], Tuple[float, "Lead"]] = {}


@dataclass
class Lead:
    """검색량 판정. status = ok(고름) | low(바닥선 아래) | fail(조회 못 함)."""

    status: str
    pick: Optional[Candidate] = None
    best: int = 0


def enabled(settings: Optional[dict]) -> bool:
    """모듈 스위치가 켜졌나."""
    return bool((settings or {}).get(SETTINGS_KEY))


def floor(settings: Optional[dict]) -> int:
    """바닥선(모듈 title_lead_floor, 기본 50)."""
    try:
        return max(1, int((settings or {}).get(FLOOR_KEY) or MIN_VOLUME))
    except (TypeError, ValueError):
        return MIN_VOLUME


def _regions() -> set:
    """지역명 목록(같은 블로그 중복 검사와 같은 것)."""
    from .same_blog_dedupe import _regions as regions

    return regions()


async def _stats(db: Any, user_id: int, hints: List[str]) -> Optional[Dict[str, Tuple[int, str]]]:
    """조회 응답 전부(공백 뺀 소문자 → (검색량, 경쟁)). 설정 없거나 실패면 None."""
    from sqlalchemy import select

    from ...models.user_settings import UserSettings
    from ..naver_ads_service import NaverAdsService

    settings = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    service = NaverAdsService(settings)
    if not settings or not service.is_configured():
        return None
    # include_related=False 면 입력어·연관어가 모두 keywords 에 담겨 온다
    result = await service.get_keyword_stats(hints, include_related=False)
    if not result.get("success"):
        logger.warning("[LEAD_KW] 검색량 조회 실패 | %s", result.get("error"))
        return None
    return {(r.get("keyword") or "").replace(" ", "").lower():
            (int(r.get("total_search_volume") or 0), r.get("competition") or "")
            for r in result.get("keywords") or []}


def judge(stats: Dict[str, Tuple[int, str]], title: str,
          keywords: Optional[List[str]], low: int) -> Lead:
    """조회 결과로 고르기(DB 없음 — 시험·모의용)."""
    regions = _regions()
    cands = pick.title_candidates(title, keywords, regions)
    for c in cands:
        c.volume, c.competition = stats.get(c.key, (0, ""))
    allc = cands + pick.related_candidates(stats, title, {c.key for c in cands})
    eligible = [c.volume for c in allc if " " in c.text or len(c.text) >= 3]
    best = max(eligible, default=0)
    chosen = pick.choose(allc, low, pick.region_lead(pick.words(title), regions))
    return Lead("ok" if chosen else "low", chosen, best)


async def measure(db: Any, user_id: int, title: str,
                  keywords: Optional[List[str]], low: int) -> Lead:
    """검색량을 재서 고른다(한 시간 기억 — 관문에서 잰 것을 생성이 다시 쓴다)."""
    key = (title, low)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_SEC:
        return hit[1]
    cands = pick.title_candidates(title, keywords, _regions())
    stats = await _stats(db, user_id, pick.hints(cands, title)) if cands else None
    lead = Lead("fail") if stats is None else judge(stats, title, keywords, low)
    _CACHE[key] = (time.time(), lead)
    return lead


def instruction(c: Candidate, title: str) -> str:
    """재조합 지시에 붙일 줄."""
    lines = [
        f"\n- 제목 맨 앞을 「{c.text}」(네이버 한 달 검색 약 {c.volume:,}회, 사람들이 실제로 "
        "치는 말)로 시작할 것. 띄어쓰기·낱말 순서 그대로, 중간에 다른 말을 끼우지 말 것",
        "- 그 바로 뒤에 쉼표 하나, 이어서 이 글로 알 수 있는 것 하나(순서·조건·비용·비교 중 "
        "하나)를 붙인다. '~은 무엇일까', '~알아보기', '~방법 안내', '~무엇인가요', "
        "'~이 필요하다면' 같은 꼬리는 쓰지 않는다",
    ]
    dropped = [w for w in pick.words(title)[:3]
               if w.replace(" ", "") not in c.key and len(w) >= 2][:2]
    names = f"(예: {'·'.join(dropped)})" if dropped and c.source != "title" else ""
    lines.append(f"- 원래 제목에 있던 지역·은행·회사·제품 이름{names}은 뒤쪽에라도 남길 것")
    return "\n".join(lines)


def body_directive(c: Candidate) -> str:
    """본문 지시 — 제목만 바뀌고 본문이 옛 말이면 순위가 안 오른다."""
    return (f"✦ 검색어 「{c.text}」\n"
            f"- 「{c.text}」를 띄어쓰기 그대로 본문 첫 문단에 한 번, 소제목 하나에 넣을 것. "
            "그 밖에는 억지로 되풀이하지 말 것")


async def apply(db: Any, user_id: int, settings: Optional[dict], title: str,
                keywords: Optional[List[str]] = None,
                cpa: bool = False) -> Tuple[Optional[dict], Optional[Candidate]]:
    """켜져 있으면 재조합용 설정 사본에 맨 앞 검색어 지시를 붙인다.

    Returns:
        (재조합에 넘길 설정, 고른 검색어). CPA 오퍼 제목이면 설정은 그대로 두고
        검색어만 돌려준다(기록용). 꺼져 있으면 (원본 설정, None).
    """
    if not enabled(settings) or "title_recombine" not in settings:
        return settings, None
    try:
        lead = await measure(db, user_id, title, keywords, floor(settings))
    except Exception as e:  # noqa: BLE001 — 검색량 실패로 생성을 막지 않는다
        logger.warning("[LEAD_KW] 판정 실패(그대로 진행) | %s", e)
        return settings, None
    if not lead.pick:
        logger.info("[LEAD_KW] 바닥선 넘는 후보 없음(%s) | '%s'", lead.status, title[:30])
        return settings, None
    c = lead.pick
    if cpa:
        logger.info("[LEAD_KW] CPA 제목 — 검색어만 기록 「%s」(%d) | '%s'",
                    c.text, c.volume, title[:30])
        return settings, c
    out = copy.deepcopy(settings)
    tr = out["title_recombine"]
    tr["custom_prompt"] = (tr.get("custom_prompt") or "") + instruction(c, title)
    logger.info("[LEAD_KW] 맨 앞 검색어 「%s」(%d회·%s) | '%s'",
                c.text, c.volume, c.source, title[:30])
    return out, c


def starts_with(title: str, keyword: Optional[str]) -> bool:
    """재조합 결과가 그 검색어로 시작하나(띄어쓰기 무시)."""
    if not keyword:
        return True
    return (title or "").replace(" ", "").startswith(keyword.replace(" ", ""))


def fit(recombined: str, keyword: str) -> str:
    """규칙으로 맞춤: 「검색어」, + 재조합 결과에서 검색어 낱말을 뺀 앞부분(30자 안)."""
    rest = recombined or ""
    for w in sorted(keyword.split(), key=len, reverse=True):
        rest = rest.replace(w, " ")
    rest = re.sub(r"\s+", " ", rest).strip(" ,·:-!?")
    if len(rest) > REST_CHARS:
        cut = rest[:REST_CHARS]
        rest = cut[:cut.rfind(" ")] if " " in cut else cut
    rest = rest.strip(" ,·:-")
    return f"{keyword}, {rest}" if rest else keyword


def journal(blog: Any, title_id: Optional[int], post_id: Optional[int],
            final_title: str, c: Optional[Candidate], applied: str) -> None:
    """글마다 한 줄 — 마케팅이 이 검색어로 순위를 잰다. 실패해도 생성은 그대로."""
    if c is None:
        return
    try:
        p = Path(LoggerConfig.LOG_DIR) / JOURNAL
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now().isoformat(timespec="seconds"),
               "blog_id": getattr(blog, "id", None), "blog": getattr(blog, "name", None),
               "title_id": title_id, "post_id": post_id, "title": final_title,
               "keyword": c.text, "volume": c.volume, "source": c.source,
               "competition": c.competition, "applied": applied}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[LEAD_KW] 기록 실패(무시) | %s", e)
