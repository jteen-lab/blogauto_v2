"""회차 산출물 전량 수집 — 만들어진 것을 하나도 빠뜨리지 않고 보여준다.

**왜 필요한가**: 실행기는 요약("40건 수집")만 돌려준다. 그걸로는 누락인지
미동작인지 판별이 안 된다(계획서 §2-3). 리허설 세션에는 이번 회차가 만든
행이 flush 상태로 살아 있으므로, 되돌리기 **전에** 여기서 전부 읽어 화면용
목록으로 바꾼다.

**신규 판별**: 회차 시작 시각 이후 created_at. 리허설 세션 안에서만 조회
하므로 다른 회차·다른 사용자의 데이터와 섞이지 않는다(어차피 이 세션의
flush 는 밖에서 안 보인다).

**제외 사유**: 임시 제목은 filter_reason 컬럼이 이미 있다. 걸러진 것도
행으로 남는 구조라 그대로 읽으면 "왜 빠졌는지"까지 나온다.

계획서: docs/plans/test_workbench_plan.md §5
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from ...models.title import MainTitle, TempTitle

logger = get_logger("workbench_capture", "app.log")

# 화면 표시 상한. 넘으면 잘라서 보내고 총 건수로 말한다.
DISPLAY_LIMIT = 500


def _clip(rows: List[dict]) -> Dict[str, Any]:
    return {"total": len(rows), "items": rows[:DISPLAY_LIMIT],
            "clipped": max(0, len(rows) - DISPLAY_LIMIT)}


async def capture_keywords(db: Any, user_id: int,
                           since: datetime) -> Dict[str, Any]:
    """이번 회차가 만든 키워드 후보 전량."""
    got = await db.execute(
        select(KeywordCandidate)
        .where(KeywordCandidate.user_id == user_id,
               KeywordCandidate.created_at >= since)
        .order_by(KeywordCandidate.id))
    rows = []
    for row in got.scalars():
        rows.append({
            "id": row.id, "kind": "keyword",
            "text": row.keyword, "seed": row.seed,
            "source": getattr(row, "discovery_source", None) or "",
            "search_volume": row.search_volume,
            "verdict": row.verdict,
            "excluded": row.verdict == "reject",
            "reason": row.verdict_reason or "",
            "topic_id": row.topic_id,
        })
    return _clip(rows)


async def capture_titles(db: Any, since: datetime) -> Dict[str, Any]:
    """이번 회차가 만든 제목 전량 — 임시(걸러진 것 포함) + 정식.

    임시 제목은 filter_reason 이 있으면 제외분이다. 정식 재고에 든 것과
    임시에 남은 것을 한 목록으로 합쳐, 화면이 전체/채택/제외로 가른다.
    """
    rows: List[dict] = []

    got = await db.execute(
        select(MainTitle).where(MainTitle.created_at >= since)
        .order_by(MainTitle.id))
    for row in got.scalars():
        rows.append({
            "id": row.id, "kind": "main_title",
            "text": row.title, "status": row.status,
            "source": row.source, "topic_id": row.topic_id,
            "subtopic_id": row.subtopic_id,
            "excluded": False, "reason": "",
        })

    got = await db.execute(
        select(TempTitle).where(TempTitle.created_at >= since)
        .order_by(TempTitle.id))
    for row in got.scalars():
        excluded = bool(row.filter_reason) or row.status in (
            "blocked", "filtered")
        rows.append({
            "id": row.id, "kind": "temp_title",
            "text": row.title, "status": row.status,
            "source": row.collection_stage, "topic_id": row.topic_id,
            "subtopic_id": row.subtopic_id,
            "excluded": excluded,
            "reason": row.filter_reason or ("미분류"
                                            if row.status == "new" else ""),
        })
    return _clip(rows)


def capture_generation(result: Any) -> Dict[str, Any]:
    """글 생성 결과 — 실행기가 돌려준 결과에 전부 들어 있다."""
    if result is None:
        return {"total": 0, "items": [], "clipped": 0}
    item = {
        "kind": "post",
        "text": getattr(result, "recombined_title", "") or "",
        "html": getattr(result, "final_html", "") or "",
        "image_url": getattr(result, "image_url", None),
        "reference_count": getattr(result, "reference_count", 0),
        "content_length": getattr(result, "content_length", 0),
        "body_chars": getattr(result, "body_chars", 0),
        "excluded": not getattr(result, "success", False),
        "reason": getattr(result, "error", "") or "",
    }
    return {"total": 1, "items": [item], "clipped": 0}


def summarize(captured: Dict[str, Any]) -> Dict[str, int]:
    """전체/채택/제외 집계 — 목록 위에 붙는 숫자."""
    items = captured.get("items") or []
    excluded = sum(1 for i in items if i.get("excluded"))
    return {"total": captured.get("total", len(items)),
            "kept": len(items) - excluded, "excluded": excluded}
