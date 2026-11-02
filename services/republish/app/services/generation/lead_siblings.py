"""7단계 새 제목 — D 방식으로 고른 검색어를 그대로 쓰고, 같은 검색어의 다른 글 각도를 피한다.

거르기(title_screen)에서 이미 잰 '가장 큰 말'이 정식 제목에 있으면 발행 때 다시 재지 않는다.
같은 검색어로 통과한 다른 제목(3~5개)과 그 검색어로 이미 나간 글 제목을 재조합 지시에 붙여
'서로 다른 질문'이 되게 한다(D5). 기존 관문·재조합은 그대로다.

순서도: docs/flowcharts/title_screen_d.md (7)
"""
from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import select

from ...core.logger import get_logger
from .lead_keyword_pick import Candidate

logger = get_logger("lead_keyword", "app.log")

MAX_SIBLINGS = 5


def known(title: Any) -> Optional[Candidate]:
    """거르기를 통과한 제목이면 그때 고른 검색어(재지 않는다)."""
    word = getattr(title, "lead_keyword", None)
    vol = getattr(title, "search_volume", None)
    if getattr(title, "screen_result", None) != "pass" or not word or not vol:
        return None
    return Candidate(text=word, source="screen", volume=int(vol))


async def siblings(db: Any, title: Any, word: str) -> List[str]:
    """같은 검색어의 다른 제목(통과 재고 + 이미 나간 글). 실패면 빈 목록."""
    from ...models.generation_history import GenerationHistory
    from ...models.title import MainTitle

    out: List[str] = []
    try:
        rows = (await db.execute(
            select(MainTitle.title).where(MainTitle.lead_keyword == word,
                                          MainTitle.id != getattr(title, "id", None))
            .order_by(MainTitle.id.desc()).limit(MAX_SIBLINGS))).scalars().all()
        out.extend(rows)
        cid = getattr(title, "candidate_id", None)
        if cid:
            done = (await db.execute(
                select(GenerationHistory.recombined_title)
                .where(GenerationHistory.candidate_id == cid)
                .order_by(GenerationHistory.id.desc()).limit(3))).scalars().all()
            out.extend(t for t in done if t)
    except Exception as e:  # noqa: BLE001 — 각도 참고 실패로 생성을 막지 않는다
        logger.warning("[LEAD_KW] 같은 검색어 제목 조회 실패 | %s", e)
    return list(dict.fromkeys(out))[:MAX_SIBLINGS + 3]


def sibling_note(titles: List[str]) -> str:
    """재조합 지시에 붙일 줄."""
    if not titles:
        return ""
    joined = " / ".join(t[:60] for t in titles)
    return ("\n- 같은 검색어로 이미 있거나 나갈 다른 글: " + joined +
            "\n  → 이 글들과 다른 질문(다른 대상·조건·상황)에 답하는 제목으로. 원래 제목들의 "
            "각도는 참고만 하고 문장을 겹치지 말 것")


def stamp_origin(history: Any, title: Any) -> None:
    """B6 — 생성 기록에 출발 검색어(candidate_id)·출처 사이트를 적는다."""
    from ..title_screen.rules import site_key

    try:
        history.candidate_id = getattr(title, "candidate_id", None)
        history.source_site = site_key(getattr(title, "source_url", None)) or None
    except Exception as e:  # noqa: BLE001 — 기록 실패로 생성을 막지 않는다
        logger.warning("[LEAD_KW] 출발 검색어 기록 실패 | %s", e)
