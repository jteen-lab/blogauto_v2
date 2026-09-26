"""소스 패널 — 지식iN·카페에서 질문을 찾아 작업의 출발점으로 삼는다.

키워드로 시작하면 니치 안에서만 돈다. 사람이 쓴 질문에는 상황(2층→3층,
엘베 없음)이 실려 있어 주제가 넓어진다 — 수작업 20편이 그렇게 나왔다.

수집기는 키워드 소스로 만든 `community` 를 그대로 쓴다. 여기서는 화면용
으로 감싸고, 각 질문에서 뽑힌 **상황 신호**를 함께 붙여 고를 근거를 준다.

**순서는 네이버가 준 대로 둔다.** 예전에는 상황이 실린 질문을 앞으로 다시
정렬하고 질문이 아닌 것을 버려서, 네이버에서 셋째였던 글이 여기선 첫째로
올라왔다. 지금은 버리지 않고 배지만 달아 자리를 지킨다 — 수집기는 그대로
걸러 쓴다(거기선 순서가 아니라 질이 중요하다).

계획서: docs/plans/test_workbench_plan.md §4-2
순서도: docs/flowcharts/workbench_source_modes.md
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...core.logger import get_logger
from ..keyword_lab import situation
from ..keyword_lab.sources import community
from ..keyword_lab.sources.base import SRC_NAVER_CAFE, SRC_NAVER_KIN

logger = get_logger("workbench_sources", "app.log")

SOURCE_LABEL = {SRC_NAVER_KIN: "지식iN", SRC_NAVER_CAFE: "카페"}


async def search_questions(user_settings: Any, query: str,
                           sources: List[str] | None = None,
                           limit: int = 20,
                           start: int = 1,
                           sort: str = "sim") -> Dict[str, Any]:
    """질문을 검색해 화면 목록으로 돌려준다.

    Args:
        user_settings: 네이버 검색 자격증명 보유 객체
        query: 검색어(니치 키워드)
        sources: 소스 코드 목록. 비우면 지식iN·카페 둘 다
        limit: 소스당 최대 건수
        start: 몇 번째 결과부터. 같은 검색어로 더 보려면 올린다
        sort: 'sim'(정확도순, 네이버 화면 기본) 또는 'date'(최신순)

    Returns:
        {"items": [...], "by_source": {소스: 건수}, "next_start": int|None,
         "error": str|None}
    """
    if not community.is_configured(user_settings):
        return {"items": [], "by_source": {},
                "error": "네이버 검색 API 키가 없습니다 — 설정에서 등록하세요"}
    text = (query or "").strip()
    if len(text) < 2:
        return {"items": [], "by_source": {}, "error": "검색어가 너무 짧습니다"}

    picked = [s for s in (sources or [SRC_NAVER_KIN, SRC_NAVER_CAFE])
              if s in SOURCE_LABEL]
    items: List[dict] = []
    by_source: Dict[str, int] = {}
    for code in picked:
        rows = await community.collect_questions(
            user_settings, [text], code, limit_per_seed=limit,
            start=start, sort=sort, keep_all=True)
        by_source[code] = len(rows)
        for rank, row in enumerate(rows, start=start):
            sit = situation.extract(row.text)
            items.append({
                "title": row.title,
                "description": row.description,
                "link": row.link,
                "source": code,
                "source_label": SOURCE_LABEL[code],
                "signals": sit.signals,
                "has_situation": sit.is_concrete,
                # 네이버 검색에서 몇 번째였나. 순서를 눈으로 대조할 수 있다
                "rank": rank,
                "is_promo": bool(row.extra.get("is_promo")),
                "is_question": bool(row.extra.get("is_question", True)),
            })

    # 여기서 다시 정렬하지 않는다 — 네이버가 준 순서가 곧 화면 순서다.
    # 다만 **같은 글이 겹쳐 오는 것**은 걸러 낸다. 지식iN 은 한 페이지 안에서
    # 제목이 같은 것을 여러 건 준다(링크는 달라 링크만으로는 못 걸러진다).
    from . import dedup

    items = dedup.unique(items, label=f"질문 '{text}'")

    # 더 볼 것이 남았나. 어느 소스든 요청한 만큼 왔으면 다음 묶음이 있다.
    # (질문이 아닌 글을 걸러내 건수가 줄므로 받은 원본 기준으로 본다)
    next_start = start + limit
    if next_start > community.MAX_START or not items:
        next_start = None

    logger.info("[WORKBENCH] 질문 검색 | '%s' %s %d번째부터 → %d건 %s",
                text, sort, start, len(items), by_source)
    return {"items": items, "by_source": by_source,
            "start": start, "next_start": next_start, "error": None}
