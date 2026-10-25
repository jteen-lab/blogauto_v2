"""리뉴얼 제목 — 새 글과 같은 N1·N4·중복 검사를 거친다 (2026-10-25).

예전 리뉴얼 재조합은 title_recombiner 를 바로 불러 맨 앞 검색어(N1)·지난 연도(N4)·
중복 검사를 모두 건너뛰었다. 새 글 생성(lead_keyword_flow)과 같은 길을 쓴다.

- 제목을 바꾸는 판정(title·rewrite)일 때만 재조합. 보호 글·keep 제목은 그대로.
- 재조합 결과가 같은 블로그·형제 사이트(전체 기간)나 다른 블로그 최근 글과 겹치면 원래 제목.
- 제목을 그대로 둘 때도 N4(지난 연도 빼기)는 건다.

순서도: docs/flowcharts/renewal_performance_pick.md (2. 한 글 리뉴얼)
"""
from __future__ import annotations

import json
import random
import re
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

from ...core.logger import get_logger

logger = get_logger("renewal_title", "app.log")

DUP_NOTE = "새 제목 중복"


def source_title(live_title: str, main_title: Any = None) -> SimpleNamespace:
    """lead_recombine 이 읽는 모양(제목·핵심어). 핵심어는 매칭된 정식제목 것을 쓴다."""
    return SimpleNamespace(title=live_title,
                           keywords=getattr(main_title, "keywords", None),
                           cpa_offer_id=None)


async def duplicate_of(db: Any, blog: Any, title: str, live_title: str,
                       settings: dict) -> Optional[str]:
    """새 제목이 이 블로그·형제·다른 블로그 글과 겹치면 사유. 자기 글(원래 제목)은 뺀다."""
    from ..generation import same_blog_dedupe as sb
    from ..generation import topic_gate as tg

    ids = await sb._site_blog_ids(db, blog) if settings.get("dedupe_sibling_sites") else [blog.id]
    mine = [t for t in await sb.history_titles(db, ids, 0) if t.strip() != live_title.strip()]
    hit = sb.find_similar(title, mine, strong=sb.STRONG_SHARED)
    if hit:
        return f"같은 사이트 「{hit[:30]}」"
    other = await tg._recent_other_posts(db, blog.id)
    return tg.find_duplicate(title, 0, other)


_TAILS = re.compile(r"\s*(?:알아보기|알아보자|무엇일까요?|무엇인가요|방법 안내|총정리)(?=\s|$)")


_JOIN_NOUN = r"(방법|계산법|기준|차이|비용|요금|순서|조건|절차|요령|이유|원리)"
_END_TAIL = r"(?:꿀팁|팁|요령|정리)$"
# 명사+은/는, 또는 조사 없이 바로 '…하게·…하는' 말이 붙은 것만(‘전기요금 누진’ 같은 명사 이음은 그대로)
_LOOSE = re.compile(_JOIN_NOUN + r"(?:(?:은|는)\s+|\s+(?=\S*(?:게|는|한)\s))(?=\S+\s.*" + _END_TAIL + ")")


def _join(m: "re.Match[str]") -> str:
    """'방법은 …꿀팁' → '방법과 …꿀팁'(받침 있으면 과, 없으면 와)."""
    noun = m.group(1)
    code = ord(noun[-1]) - 0xAC00
    return noun + ("과 " if 0 <= code < 11172 and code % 28 else "와 ")


def _drop_tails(title: str) -> str:
    """'~알아보기'·'~무엇일까' 꼬리를 빼고, '방법은 …꿀팁'처럼 조사가 어색한 이음을 '과/와'로.

    10/25 /613: '제습기 전기세 절약 방법은 뽀송하게 유지하는 꿀팁' (마케팅 재검수).
    """
    out = re.sub(r"\s{2,}", " ", _TAILS.sub("", title)).strip(" ,")
    out = re.sub(_JOIN_NOUN + r"(?:은|는)$", r"\1", out)  # '방법은 무엇일까요' 꼬리를 뺀 뒤 남은 조사
    if re.search(_END_TAIL, out):
        out = _LOOSE.sub(_join, out, count=1)
    return out if len(out) >= 8 else title


async def resolve(gen: Any, blog: Any, module: Any, live_title: str,
                  recombine: bool, main_title: Any = None) -> Tuple[str, List[str], str]:
    """(제목, 본문 지시, 기록용 메모)."""
    from ..generation import lead_keyword_flow as lkf

    settings = module.settings or {}
    if not recombine:
        title, notes = lkf.finalize(live_title, None, "none")
        return title, notes, "제목 유지" + (" · 지난 연도 뺌" if title != live_title else "")
    ai = (blog.ai_config or {}).get("title_ai", {})
    styles = (settings.get("title_recombine") or {}).get("styles") or []
    try:
        rec, lead, applied = await lkf.lead_recombine(
            gen, source_title(live_title, main_title), settings, ai.get("provider"),
            ai.get("model"), random.choice(styles) if styles else None, module.id)
    except Exception as e:  # noqa: BLE001 — 제목 실패로 리뉴얼을 막지 않는다
        logger.warning("[RENEWAL_TITLE] 재조합 실패 → 원래 제목 | %s", e)
        title, notes = lkf.finalize(live_title, None, "none")
        return title, notes, "재조합 실패 — 원래 제목"
    new = _drop_tails((rec.recombined_title or live_title).strip())
    title, notes = lkf.finalize(new, lead, applied)
    dup = await duplicate_of(gen.db, blog, title, live_title, settings)
    if dup:
        logger.info("[RENEWAL_TITLE] 새 제목 중복 → 원래 제목 | '%s' | %s", title[:40], dup)
        title, notes = lkf.finalize(live_title, None, "none")
        return title, notes, f"{DUP_NOTE}({dup}) — 원래 제목"
    kw = getattr(lead, "text", "") if lead else ""
    return title, notes, json.dumps({"lead": kw, "applied": applied}, ensure_ascii=False)
