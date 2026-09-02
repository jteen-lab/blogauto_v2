"""경쟁 제목에서 **각도**를 뽑는다.

지금까지 제목 수집이 비효율이었던 이유는 수집한 제목을 **그대로 재고로 썼기**
때문이다. 최신성이 낮고 무관한 제목이 섞였다.

역할을 바꾼다. 경쟁 제목은 "이 키워드에서 이미 먹히는 각도" 를 알려 주는
신호다. 그것을 AI 프롬프트에 넣어 **겹치지 않는 제목**을 만들게 한다.
업계 권고도 순수 AI·순수 스크래핑이 아니라 혼합이다.

원문을 재고에 넣지 않으므로 저작권 문제도 생기지 않는다.

계획서: docs/plans/keyword_pipeline_restructure_review.md §4-2
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Set

from ...core.logger import get_logger
from .niche import in_niche

logger = get_logger("title_angles", "app.log")

# 키워드당 참고할 제목 수. 많이 봐도 각도는 몇 가지로 수렴한다.
DEFAULT_SAMPLE = 10

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&[a-z]+;")


def clean(title: str) -> str:
    """검색 결과 제목의 태그·엔티티를 걷어낸다."""
    text = TAG_RE.sub("", title or "")
    text = ENTITY_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


async def fetch(search_service: Any, keyword: str,
                sample: int = DEFAULT_SAMPLE,
                niche: Optional[Set[str]] = None) -> List[str]:
    """이 키워드로 이미 상위에 있는 제목들.

    `niche` 를 주면 그 도메인의 결과를 **앞에 놓는다**. 배제가 아니라
    우선순위다 — 목록에 없는 새 경쟁자를 놓치면 각도가 낡는다.

    실패는 빈 목록이다 — 참고 자료가 없다고 제목 생성을 멈출 이유는 없다.
    """
    try:
        result = await search_service.search_blog(
            keyword, display=max(1, min(30, sample)))
    except Exception as e:  # noqa: BLE001
        logger.warning("[TITLE_ANGLES] 조회 실패 | %s | %s", keyword, e)
        return []

    if not result.get("success"):
        return []

    inside: List[str] = []
    outside: List[str] = []
    seen = set()
    for item in result.get("items") or []:
        title = clean(item.get("title", ""))
        if len(title) < 6 or title in seen:
            continue
        seen.add(title)
        link = item.get("link") or item.get("bloggerlink")
        (inside if in_niche(link, niche or set()) else outside).append(title)

    if niche and inside:
        logger.info("[TITLE_ANGLES] 니치 %s건 · 그 밖 %s건 | %s",
                    len(inside), len(outside), keyword)
    return inside + outside


def hint(titles: List[str], limit: int = 8) -> str:
    """프롬프트에 넣을 참고 문구. 없으면 빈 문자열."""
    picked = [t for t in titles[:limit] if t]
    if not picked:
        return ""
    lines = "\n".join(f"- {t}" for t in picked)
    return (
        "\n\n이미 나와 있는 제목들(참고):\n" + lines +
        "\n위 각도와 **겹치지 않는** 각도로 쓰세요. 같은 말을 다르게 적는 것이 "
        "아니라, 저 글들이 다루지 않은 질문에 답해야 합니다."
    )
