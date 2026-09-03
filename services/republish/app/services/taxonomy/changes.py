"""분류표 변경 — plan → apply → rollback.

분류표를 잘못 바꾸면 재고 전체의 분류가 틀어진다. 대량 수정 도구는
**되돌릴 수 있어야만** 열 수 있다. 그래서 세 단계다.

    plan   변경안을 받아 **영향만 계산**한다. DB 는 건드리지 않는다.
    apply  사람이 승인하면 적용한다. 적용 전 상태를 스냅샷으로 남긴다.
    rollback 스냅샷으로 되돌린다.

누가 호출하든 같은 통로를 지난다 — 화면·클로드 코드·다른 에이전트·스크립트.
`actor` 로 구분만 남긴다.

계획서: docs/plans/title_tab_workplan.md §9-4
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.category import Keyword, SubTopic, Topic
from ...models.taxonomy_change import (
    ACTOR_UI, ACTORS, STATUS_APPLIED, STATUS_PLANNED, STATUS_ROLLED_BACK,
    TaxonomyChange,
)
from ...models.title import TempTitle

logger = get_logger("taxonomy_changes", "app.log")

# 지원하는 연산. 지금은 키워드 추가·삭제만 연다(§9-6 1차).
OP_ADD_KEYWORD = "add_keyword"
OP_REMOVE_KEYWORD = "remove_keyword"
OPERATIONS = (OP_ADD_KEYWORD, OP_REMOVE_KEYWORD)

# 한 번에 처리할 연산 수 상한. 실수 하나가 통째로 번지는 것을 막는다.
MAX_OPS = 200


def normalize(items: Any) -> List[Dict[str, Any]]:
    """요청을 검증한다. 모르는 연산은 버린다."""
    out: List[Dict[str, Any]] = []
    for row in (items or [])[:MAX_OPS]:
        if not isinstance(row, dict):
            continue
        op = str(row.get("op") or "").strip()
        if op not in OPERATIONS:
            continue
        term = str(row.get("term") or "").strip()
        if not term:
            continue
        entry: Dict[str, Any] = {"op": op, "term": term}
        if op == OP_ADD_KEYWORD:
            try:
                entry["subtopic_id"] = int(row.get("subtopic_id"))
            except (TypeError, ValueError):
                continue
        else:
            try:
                entry["keyword_id"] = int(row.get("keyword_id"))
            except (TypeError, ValueError):
                continue
        out.append(entry)
    return out


async def plan(db: AsyncSession, user_id: int, items: Any,
               actor: str = ACTOR_UI,
               summary: Optional[str] = None) -> Dict[str, Any]:
    """변경안의 영향을 계산한다. **DB 를 바꾸지 않는다.**"""
    ops = normalize(items)
    if not ops:
        return {"success": False, "error": "적용할 변경이 없습니다"}

    impact = {"add": 0, "remove": 0, "recovered": 0, "details": []}
    for entry in ops:
        if entry["op"] == OP_ADD_KEYWORD:
            recovered = await _would_recover(db, entry["term"])
            # 걸릴 제목을 함께 보여 준다. 숫자만 보고 승인하면 오분류를
            # 눈으로 확인할 수 없다.
            samples = await _would_match(db, entry["term"])
            impact["add"] += 1
            impact["recovered"] += recovered
            impact["details"].append(
                {"op": entry["op"], "term": entry["term"],
                 "recovered": recovered, "samples": samples})
        else:
            impact["remove"] += 1
            impact["details"].append({"op": entry["op"],
                                      "term": entry["term"]})

    row = TaxonomyChange(
        user_id=user_id, status=STATUS_PLANNED,
        actor=actor if actor in ACTORS else ACTOR_UI,
        summary=summary or _summary(ops, impact),
        payload=json.dumps({"items": ops}, ensure_ascii=False),
        impact=json.dumps(impact, ensure_ascii=False))
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info("[TAXONOMY] plan #%s | %s", row.id, row.summary)
    return {"success": True, "change_id": row.id, "impact": impact,
            "summary": row.summary}


async def apply(db: AsyncSession, user_id: int,
                change_id: int) -> Dict[str, Any]:
    """승인된 계획을 적용한다. 적용 전 상태를 스냅샷으로 남긴다."""
    row = await _change(db, user_id, change_id)
    if row is None:
        return {"success": False, "error": "변경 계획을 찾을 수 없습니다"}
    if row.status != STATUS_PLANNED:
        return {"success": False,
                "error": f"이미 처리된 계획입니다 (상태: {row.status})"}

    ops = row.payload_dict().get("items") or []
    snapshot: List[Dict[str, Any]] = []
    added = removed = 0

    for entry in ops:
        if entry["op"] == OP_ADD_KEYWORD:
            keyword = Keyword(subtopic_id=entry["subtopic_id"],
                              name=entry["term"])
            db.add(keyword)
            await db.flush()
            snapshot.append({"op": OP_ADD_KEYWORD, "keyword_id": keyword.id})
            added += 1
        else:
            found = await db.get(Keyword, entry["keyword_id"])
            if found is None or found.is_deleted:
                continue
            snapshot.append({"op": OP_REMOVE_KEYWORD,
                             "keyword_id": found.id,
                             "subtopic_id": found.subtopic_id,
                             "name": found.name})
            found.is_deleted = True
            removed += 1

    row.snapshot = json.dumps({"entries": snapshot}, ensure_ascii=False)
    row.status = STATUS_APPLIED
    row.applied_at = func.now()
    await db.commit()

    logger.info("[TAXONOMY] apply #%s | 추가 %d · 삭제 %d",
                change_id, added, removed)
    return {"success": True, "added": added, "removed": removed,
            "change_id": change_id}


async def rollback(db: AsyncSession, user_id: int,
                   change_id: int) -> Dict[str, Any]:
    """스냅샷으로 되돌린다. 추가한 것은 지우고, 지운 것은 되살린다."""
    row = await _change(db, user_id, change_id)
    if row is None:
        return {"success": False, "error": "변경 계획을 찾을 수 없습니다"}
    if row.status != STATUS_APPLIED:
        return {"success": False,
                "error": f"적용된 계획만 되돌릴 수 있습니다 (상태: {row.status})"}

    undone = 0
    for entry in row.snapshot_dict().get("entries") or []:
        found = await db.get(Keyword, entry.get("keyword_id"))
        if found is None:
            continue
        if entry["op"] == OP_ADD_KEYWORD:
            # 추가한 것을 지운다. 하드 삭제하지 않는다 — 그 사이 분류된
            # 제목이 참조하고 있을 수 있다.
            found.is_deleted = True
        else:
            found.is_deleted = False
        undone += 1

    row.status = STATUS_ROLLED_BACK
    await db.commit()
    logger.info("[TAXONOMY] rollback #%s | %d건", change_id, undone)
    return {"success": True, "undone": undone, "change_id": change_id}


async def history(db: AsyncSession, user_id: int,
                  limit: int = 50) -> List[Dict[str, Any]]:
    """변경 이력. 누가 무엇을 언제 바꿨는지."""
    rows = (await db.execute(
        select(TaxonomyChange)
        .where(TaxonomyChange.user_id == user_id)
        .order_by(TaxonomyChange.id.desc())
        .limit(max(1, limit))
    )).scalars().all()
    return [{"id": r.id, "status": r.status, "actor": r.actor,
             "summary": r.summary, "impact": r.impact_dict(),
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "applied_at": r.applied_at.isoformat() if r.applied_at else None}
            for r in rows]


async def tree(db: AsyncSession) -> List[Dict[str, Any]]:
    """전체 분류표. 어디에 넣을지 판단하는 근거다.

    **삭제된 것은 뺀다.** 분류 매처(`CategoryMatcherService._load_keywords`)
    가 `is_deleted` 를 거르므로, 여기서 안 거르면 화면에는 보이는데 실제로는
    분류에 쓰이지 않는 하위주제가 목록에 뜬다. 실제로 테스트용 하위주제
    37개와 주제 4개가 추천 화면 드롭다운에 노출됐다.
    """
    topics = (await db.execute(
        select(Topic).where(Topic.is_deleted.is_(False))
        .order_by(Topic.id))).scalars().all()
    subs = (await db.execute(
        select(SubTopic).where(SubTopic.is_deleted.is_(False))
        .order_by(SubTopic.id))).scalars().all()
    keywords = (await db.execute(
        select(Keyword).where(Keyword.is_deleted.is_(False))
        .order_by(Keyword.id))).scalars().all()

    by_sub: Dict[int, list] = {}
    for row in keywords:
        by_sub.setdefault(row.subtopic_id, []).append(
            {"id": row.id, "name": row.name})

    by_topic: Dict[int, list] = {}
    for row in subs:
        by_topic.setdefault(row.topic_id, []).append(
            {"id": row.id, "name": row.name,
             "keywords": by_sub.get(row.id, [])})

    return [{"id": t.id, "name": t.name,
             "subtopics": by_topic.get(t.id, [])} for t in topics]


async def _would_recover(db: AsyncSession, term: str) -> int:
    """이 말을 넣으면 미분류 몇 건이 살아나는가."""
    from .suggest import recovery_estimate

    return await recovery_estimate(db, term)


async def _would_match(db: AsyncSession, term: str) -> List[str]:
    """이 말에 걸릴 제목 표본."""
    from .suggest import recovery_samples

    return await recovery_samples(db, term)


async def _change(db: AsyncSession, user_id: int,
                  change_id: int) -> Optional[TaxonomyChange]:
    return (await db.execute(
        select(TaxonomyChange).where(TaxonomyChange.id == change_id,
                                     TaxonomyChange.user_id == user_id)
    )).scalar_one_or_none()


def _summary(ops: List[dict], impact: dict) -> str:
    """사람이 읽을 한 줄."""
    parts = []
    if impact["add"]:
        parts.append(f"분류어 {impact['add']}개 추가")
    if impact["remove"]:
        parts.append(f"{impact['remove']}개 삭제")
    if impact["recovered"]:
        parts.append(f"미분류 {impact['recovered']:,}건 회수 예상")
    return " · ".join(parts) or "변경 없음"
