"""정식제목 수동 재조합 — 결과를 재고로 남긴다.

지금까지 재조합은 **발행 직전에만** 일어나 결과가 휘발됐다. 같은 제목을
다음에 또 쓰면 처음부터 다시 만들었다.

여기서는 정식제목 탭에서 사람이 돌리고 **결과를 정식제목으로 저장**한다.

    원본 정식제목 ──재조합──▶ 새 정식제목
                              group_id = 원본 그룹 (같은 묶음)
                              recombined_from_id = 원본 id (♻ 배지)

생성 모듈이 재조합 제목을 고르면 **다시 재조합하지 않는다.** 두 단계
멀어지면 키워드가 유실된다.

계획서: docs/plans/title_tab_workplan.md §4-2 · §4-3 · §4-6
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate
from ...models.title import MainTitle
from .freshness import plan as freshness_plan

logger = get_logger("recombine_service", "app.log")

# 한 번에 만들 재조합 제목 수 상한. AI 호출이라 비싸다.
MAX_PER_RUN = 30


class RecombineService:
    """정식제목을 재조합해 같은 그룹에 넣는다."""

    def __init__(self, db: AsyncSession, user_id: int, recombiner: Any = None):
        self.db = db
        self.user_id = user_id
        self.recombiner = recombiner
        self.last_error: Optional[str] = None

    async def run(self, title_ids: List[int], module_id: int,
                  style: Optional[str] = None,
                  provider: Optional[str] = None,
                  model: Optional[str] = None,
                  freshness: bool = False,
                  expand: bool = False) -> Dict[str, Any]:
        """고른 제목들을 재조합한다.

        Args:
            title_ids: 원본 정식제목 ID 목록
            module_id: 프롬프트 모듈(재조합 프롬프트를 여기서 읽는다)
            style: 스타일. None 이면 모듈 설정을 따른다
            freshness: 최신성 갱신 모드 — 연도만 바꾸면 되는 것은 AI 없이
            expand: 키워드 축 확장 — 원본의 채택 키워드에서 뽑은 질문을
                힌트로 넣는다. `candidate_id` 가 있어야 동작한다(§4-6 ②)
        """
        rows = await self._titles(title_ids[:MAX_PER_RUN])
        if not rows:
            return {"made": 0, "items": [], "error": "대상 제목이 없습니다"}

        made: List[Dict[str, Any]] = []
        skipped = 0

        for row in rows:
            if row.recombined_from_id:
                # 재조합 결과를 또 재조합하면 원문에서 두 단계 멀어진다
                skipped += 1
                continue
            result = await self._one(row, module_id, style, provider, model,
                                     freshness, expand)
            if result:
                made.append(result)

        await self.db.commit()
        logger.info("[RECOMBINE] %d건 생성 · %d건 건너뜀", len(made), skipped)
        return {"made": len(made), "items": made, "skipped": skipped,
                "error": self.last_error}

    async def _one(self, row: MainTitle, module_id: int,
                   style: Optional[str], provider: Optional[str],
                   model: Optional[str], freshness: bool,
                   expand: bool = False) -> Optional[Dict[str, Any]]:
        """제목 하나. 규칙으로 끝나면 AI 를 부르지 않는다."""
        if freshness:
            decision = freshness_plan(row.title, row.created_at)
            row.freshness_checked_at = func.now()
            if not decision["stale"]:
                return None
            if decision["rule_only"]:
                # 연도만 바꾸면 되는 경우가 가장 흔하다. AI 비용 0.
                return self._store(row, decision["rule_only"], "freshness")

        if self.recombiner is None:
            self.last_error = "재조합 AI 가 지정되지 않았습니다"
            return None

        keywords = await self._keywords(row)
        if expand:
            # 원본 키워드에서 질문 축을 뽑아 함께 넣는다. 같은 말을 다르게
            # 적는 대신 **다른 질문에 답하는** 제목이 나온다.
            keywords = keywords + await self._question_axes(row)
        try:
            result = await self.recombiner.recombine(
                original_title=row.title, module_id=module_id,
                provider=provider, model=model, style=style,
                keywords=keywords)
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)[:200]
            logger.warning("[RECOMBINE] 실패 | %s | %s", row.id, e)
            return None

        text = (result.recombined_title or "").strip()
        if not text or text == row.title:
            return None
        return self._store(row, text, style or result.__dict__.get("style"))

    def _store(self, origin: MainTitle, title: str,
               style: Optional[str]) -> Dict[str, Any]:
        """재조합 결과를 **같은 그룹**에 넣는다.

        대표(`is_group_representative`)는 원본이 유지한다. 목록에서는
        `recombined_from_id` 로 ♻ 배지를 단다 — 유사도 그룹과 필드로
        구분되므로 별도 그룹을 만들 필요가 없다.
        """
        row = MainTitle(
            title=title,
            category_id=origin.category_id,
            topic_id=origin.topic_id,
            subtopic_id=origin.subtopic_id,
            group_id=origin.group_id,
            is_group_representative=False,
            status="available",
            source="recombine",
            source_url=origin.source_url,
            candidate_id=origin.candidate_id,
            expires_at=origin.expires_at,
            recombined_from_id=origin.id,
            recombine_style=style,
            keywords=origin.keywords,
        )
        self.db.add(row)
        return {"title": title, "from_id": origin.id, "style": style}

    async def _question_axes(self, row: MainTitle) -> List[str]:
        """이 제목의 키워드가 답할 수 있는 **다른 질문들**.

        의도 분류가 이미 규칙으로 질문을 만든다(`keyword_lab.intent`).
        AI 호출 없이 축을 넓힐 수 있다. 정본 키워드가 없으면 빈 목록이다 —
        무엇으로 넓힐지 모르는 채로 확장하면 엉뚱한 제목이 나온다.
        """
        if not row.candidate_id:
            return []
        keyword = (await self.db.execute(
            select(KeywordCandidate.keyword).where(
                KeywordCandidate.id == row.candidate_id)
        )).scalar_one_or_none()
        if not keyword:
            return []
        try:
            from ..keyword_lab.intent import questions

            return [q for q in questions(keyword) if q][:3]
        except Exception as e:  # noqa: BLE001
            logger.warning("[RECOMBINE] 질문 축 생성 실패 | %s", e)
            return []

    async def _titles(self, ids: List[int]) -> List[MainTitle]:
        if not ids:
            return []
        return list((await self.db.execute(
            select(MainTitle).where(MainTitle.id.in_(ids))
        )).scalars().all())

    async def _keywords(self, row: MainTitle) -> List[str]:
        """지켜야 할 핵심어.

        정본 키워드(`candidate_id`)가 있으면 그것이 가장 정확하다. 없으면
        제목에서 뽑아 둔 `keywords` 를 쓴다.
        """
        out: List[str] = []
        if row.candidate_id:
            found = (await self.db.execute(
                select(KeywordCandidate.keyword).where(
                    KeywordCandidate.id == row.candidate_id)
            )).scalar_one_or_none()
            if found:
                out.append(found)
        if row.keywords:
            try:
                parsed = json.loads(row.keywords)
                if isinstance(parsed, list):
                    out.extend(str(k) for k in parsed if k)
            except (TypeError, ValueError):
                pass
        # 중복 제거하되 순서는 유지 — 정본 키워드가 앞에 와야 한다
        seen = set()
        return [k for k in out if not (k in seen or seen.add(k))]


async def stale_titles(db: AsyncSession, limit: int = 100) -> List[dict]:
    """최신성 갱신 후보. 화면이 "몇 건이 낡았다" 를 보여 준다."""
    rows = (await db.execute(
        select(MainTitle)
        .where(MainTitle.status == "available",
               MainTitle.recombined_from_id.is_(None))
        .order_by(MainTitle.created_at.asc())
        .limit(max(1, limit) * 5)
    )).scalars().all()

    now = datetime.now(timezone.utc)
    out = []
    for row in rows:
        decision = freshness_plan(row.title, row.created_at, now)
        if not decision["stale"]:
            continue
        out.append({"id": row.id, "title": row.title,
                    "suggestion": decision["rule_only"],
                    "needs_ai": decision["needs_ai"]})
        if len(out) >= limit:
            break
    return out
