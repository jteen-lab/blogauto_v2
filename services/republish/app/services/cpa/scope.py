"""무엇이 CPA 것인가 — 한 곳에서 판정한다.

**숨기지 않고 표시한다.** 전수 조사(2026-09-09) 결과 구분이 필요한 것은
5종뿐이고 7종은 공유해도 된다. 모드 전환은 공유해도 될 것까지 숨긴다.

구분 축은 **니치(주제)** 다. 오퍼 1개 = 니치 1개. 키워드·임시제목·정식
제목이 이미 `topic_id` 를 들고 있어 컬럼을 더 만들지 않는다.

판정을 여기 모으는 이유: `cpa_offer_id` 하나를 세 곳(세는 곳·목록·고르는
곳)에 흩어 넣었다가 한 곳을 빠뜨렸다. 같은 실수를 반복하지 않는다.

순서도: docs/flowcharts/cpa_scope.md
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import Topic

logger = get_logger("cpa_scope", "app.log")

# 화면 필터 값
ALL = "all"          # 기본 — 숨기지 않는다
ADSENSE = "adsense"
CPA = "cpa"
FILTERS = (ALL, ADSENSE, CPA)

# 배지 문구
LABEL = {True: "CPA", False: "애드센스"}


async def cpa_topic_ids(db: AsyncSession) -> Set[int]:
    """CPA 니치인 주제 ID.

    수가 적다(주제 23개). 목록 화면마다 한 번 부르면 된다.
    """
    try:
        rows = (await db.execute(
            select(Topic.id).where(Topic.cpa_offer_id.isnot(None))
        )).scalars().all()
        return {int(r) for r in rows}
    except Exception as e:  # noqa: BLE001 — 판정 실패로 목록을 막지 않는다
        logger.warning("[SCOPE] CPA 주제 조회 실패 | %s", e)
        return set()


async def cpa_blog_ids(db: AsyncSession) -> Set[int]:
    """CPA 오퍼를 담당하는 블로그 ID.

    블로그에는 컬럼을 더하지 않는다 — `cpa_offers.blog_ids` 가 이미 있다.
    """
    try:
        from ...models.cpa_offer import CpaOffer

        rows = (await db.execute(
            select(CpaOffer.blog_ids).where(CpaOffer.is_deleted.is_(False))
        )).scalars().all()
        out: Set[int] = set()
        for ids in rows:
            for one in (ids or []):
                try:
                    out.add(int(one))
                except (TypeError, ValueError):
                    continue
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("[SCOPE] CPA 블로그 조회 실패 | %s", e)
        return set()


def is_cpa_row(topic_id: Optional[int], cpa_topics: Set[int],
               own_offer_id: Optional[int] = None) -> bool:
    """이 행이 CPA 것인가.

    Args:
        topic_id: 행의 주제 ID
        cpa_topics: `cpa_topic_ids()` 결과
        own_offer_id: 행이 직접 들고 있는 오퍼 ID(정식제목 등)

    Returns:
        True 면 CPA
    """
    if own_offer_id:
        return True
    return bool(topic_id) and int(topic_id) in cpa_topics


def badge(is_cpa: bool) -> str:
    """화면에 붙일 배지 문구."""
    return LABEL[bool(is_cpa)]


def keep(is_cpa: bool, wanted: Optional[str]) -> bool:
    """이 행을 필터에 남길지. 기본(전체)은 전부 남긴다."""
    if not wanted or wanted == ALL or wanted not in FILTERS:
        return True
    return (wanted == CPA) == bool(is_cpa)


def mark(rows: Iterable[Dict[str, Any]], cpa_topics: Set[int],
         wanted: Optional[str] = None,
         topic_key: str = "topic_id",
         offer_key: str = "cpa_offer_id") -> List[Dict[str, Any]]:
    """목록에 배지를 붙이고 필터를 적용한다.

    Args:
        rows: dict 목록
        cpa_topics: CPA 주제 ID 모음
        wanted: all|adsense|cpa (없으면 전체)
        topic_key/offer_key: 각 행에서 주제·오퍼를 읽을 키

    Returns:
        `is_cpa` 와 `scope_label` 이 붙은 목록
    """
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        flag = is_cpa_row(row.get(topic_key), cpa_topics, row.get(offer_key))
        if not keep(flag, wanted):
            continue
        out.append({**row, "is_cpa": flag, "scope_label": badge(flag)})
    return out


def condition(model: Any, wanted: Optional[str], cpa_topics: Set[int],
              has_offer_column: bool = False) -> Optional[Any]:
    """목록 질의에 붙일 조건.

    화면에서 거르면 페이지 수가 어긋난다. DB 에서 걸러야 한다.

    Args:
        model: MainTitle · TempTitle · Keyword 등
        wanted: all|adsense|cpa (없거나 all 이면 조건 없음)
        cpa_topics: CPA 니치 주제 ID
        has_offer_column: 그 모델이 `cpa_offer_id` 를 직접 들고 있나

    Returns:
        조건식. 걸 필요가 없으면 None
    """
    from sqlalchemy import and_, or_

    if not wanted or wanted == ALL or wanted not in FILTERS:
        return None

    topic_col = getattr(model, "topic_id", None)
    parts = []
    if topic_col is not None and cpa_topics:
        # NULL 가드가 없으면 주제 없는 행에서 IN 이 NULL 이 되고,
        # NOT(NULL) 도 NULL 이라 애드센스 목록에서 통째로 빠진다.
        parts.append(and_(topic_col.isnot(None),
                          topic_col.in_(list(cpa_topics))))
    if has_offer_column:
        parts.append(model.cpa_offer_id.isnot(None))

    if not parts:
        # CPA 인 것이 하나도 없다. cpa 를 고르면 빈 목록, adsense 면 전부.
        return None if wanted == ADSENSE else _never(model)

    is_cpa = or_(*parts) if len(parts) > 1 else parts[0]
    return is_cpa if wanted == CPA else ~is_cpa


def _never(model: Any) -> Any:
    """아무것도 고르지 않는 조건."""
    return model.id.is_(None)


def topic_condition(model: Any, wanted: Optional[str]) -> Optional[Any]:
    """주제 자체를 거를 때. 주제는 자기 컬럼으로 판정한다."""
    if not wanted or wanted == ALL or wanted not in FILTERS:
        return None
    return (model.cpa_offer_id.isnot(None) if wanted == CPA
            else model.cpa_offer_id.is_(None))
