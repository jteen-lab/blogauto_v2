"""소스 패널 — 지식iN·카페에서 질문을 찾아 작업의 출발점으로 삼는다.

키워드로 시작하면 니치 안에서만 돈다. 사람이 쓴 질문에는 상황(2층→3층,
엘베 없음)이 실려 있어 주제가 넓어진다 — 수작업 20편이 그렇게 나왔다.

수집기는 키워드 소스로 만든 `community` 를 그대로 쓴다. 여기서는 화면용
으로 감싸고, 각 질문에서 뽑힌 **상황 신호**를 함께 붙여 고를 근거를 준다.

계획서: docs/plans/test_workbench_plan.md §4-2
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
                           limit: int = 20) -> Dict[str, Any]:
    """질문을 검색해 화면 목록으로 돌려준다.

    Args:
        user_settings: 네이버 검색 자격증명 보유 객체
        query: 검색어(니치 키워드)
        sources: 소스 코드 목록. 비우면 지식iN·카페 둘 다
        limit: 소스당 최대 건수

    Returns:
        {"items": [...], "by_source": {소스: 건수}, "error": str|None}
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
            user_settings, [text], code, limit_per_seed=limit)
        by_source[code] = len(rows)
        for row in rows:
            sit = situation.extract(row.text)
            items.append({
                "title": row.title,
                "description": row.description,
                "link": row.link,
                "source": code,
                "source_label": SOURCE_LABEL[code],
                "signals": sit.signals,
                "has_situation": sit.is_concrete,
            })

    # 상황이 붙은 질문을 앞으로 — 고를 가치가 높은 것부터 보인다
    items.sort(key=lambda i: (not i["has_situation"],))
    logger.info("[WORKBENCH] 질문 검색 | '%s' → %d건 %s",
                text, len(items), by_source)
    return {"items": items, "by_source": by_source, "error": None}
