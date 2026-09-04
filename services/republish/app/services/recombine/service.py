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

# 중복 검사에서 훑을 기존 제목 수. 전량을 비교하면 한 건당 수천 번
# 비교하게 된다. 최근 것부터 본다 — 오래된 제목과 겹치는 일은 드물다.
SIMILARITY_SCAN = 500


def _similarity():
    """유사도 서비스. 못 불러오면 검사를 건너뛴다(재조합은 계속한다)."""
    import os
    import sys

    for path in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
    try:
        from services.similarity_service import SimilarityService

        return SimilarityService()
    except Exception as e:  # noqa: BLE001
        logger.warning("[RECOMBINE] 유사도 서비스 없음 | %s", e)
        return None


class RecombineService:
    """정식제목을 재조합해 같은 그룹에 넣는다."""

    def __init__(self, db: AsyncSession, user_id: int, recombiner: Any = None):
        self.db = db
        self.user_id = user_id
        self.recombiner = recombiner
        self.last_error: Optional[str] = None
        # 왜 안 만들어졌는지. 0건일 때 화면이 이걸로 설명한다.
        self.reasons: Dict[str, int] = {}

    def _count(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    async def run(self, title_ids: List[int], module_id: int,
                  style: Optional[str] = None,
                  provider: Optional[str] = None,
                  model: Optional[str] = None,
                  freshness: bool = False,
                  expand: bool = False) -> Dict[str, Any]:  # noqa: C901
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

        # AI 제공자가 없으면 재조합기는 **원본을 그대로 돌려준다.** 그러면
        # "같은 제목" 이라 저장되지 않고 0건으로 끝난다 — 사유도 안 보인다.
        # 화면에서 안 골랐으면 등록된 활성 키에서 찾는다.
        provider = provider or await self._default_provider()
        if not provider:
            return {"made": 0, "items": [],
                    "error": "AI 제공자를 고르세요 — 등록된 활성 AI 키가 없습니다"}

        made: List[Dict[str, Any]] = []
        skipped = 0
        # 왜 안 만들어졌는지 센다. 숫자만 0 으로 두면 화면이 아무것도
        # 말해 주지 못한다 — 실제로 "0건" 만 보이고 끝난 적이 있다.
        self.reasons = {}

        for row in rows:
            if row.recombined_from_id:
                # 재조합 결과를 또 재조합하면 원문에서 두 단계 멀어진다
                skipped += 1
                self._count("already")
                continue
            result = await self._one(row, module_id, style, provider, model,
                                     freshness, expand)
            if result:
                made.append(result)

        await self.db.commit()
        error = self.last_error or (
            _explain(self.reasons, len(rows)) if not made else None)
        logger.info("[RECOMBINE] %d건 생성 · %d건 건너뜀 | 사유 %s",
                    len(made), skipped, self.reasons)
        return {"made": len(made), "items": made, "skipped": skipped,
                "reasons": dict(self.reasons), "error": error}

    async def _one(self, row: MainTitle, module_id: int,
                   style: Optional[str], provider: Optional[str],
                   model: Optional[str], freshness: bool,
                   expand: bool = False) -> Optional[Dict[str, Any]]:
        """제목 하나. 규칙으로 끝나면 AI 를 부르지 않는다."""
        if freshness:
            decision = freshness_plan(row.title, row.created_at)
            row.freshness_checked_at = func.now()
            if not decision["stale"]:
                # 최신성 모드는 **낡은 제목만** 손본다. 고른 제목이 낡지
                # 않았으면 할 일이 없다 — 그 사실을 말해 줘야 한다.
                self._count("not_stale")
                return None
            if decision["rule_only"]:
                # 연도만 바꾸면 되는 경우가 가장 흔하다. AI 비용 0.
                return self._store(row, decision["rule_only"], "freshness")

        if self.recombiner is None:
            self.last_error = "재조합 AI 가 지정되지 않았습니다"
            self._count("no_ai")
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
            self._count("ai_error")
            return None

        text = (result.recombined_title or "").strip()
        if not text or text == row.title:
            # 재조합기는 실패해도 예외를 던지지 않고 원본을 돌려준다.
            # 사유를 남기지 않으면 화면에 "0건" 만 뜨고 끝난다.
            if not self.last_error:
                self.last_error = (
                    f"제목이 바뀌지 않았습니다 — 프롬프트 모듈의 "
                    f"'제목 재조합' 이 켜져 있는지, AI 키가 살아 있는지 "
                    f"확인하세요 (provider={result.ai_provider})")
            self._count("unchanged")
            return None

        # 재조합은 관문 밖이다. 이미 있는 제목과 겹치면 재고만 늘고
        # 같은 글이 두 번 나간다(계획서 §4-5 C).
        clash = await self._too_similar(text, row)
        if clash:
            retry = await self._retry_distinct(row, module_id, style,
                                               provider, model, clash)
            if not retry:
                logger.info("[RECOMBINE] 유사 제목이라 건너뜀 | %s", text[:30])
                self._count("duplicate")
                return None
            text = retry

        return self._store(row, text, style or result.__dict__.get("style"))

    async def _too_similar(self, text: str,
                           origin: MainTitle) -> Optional[str]:
        """이미 있는 제목과 겹치는가. 겹치면 그 제목을 돌려준다.

        같은 그룹 안은 원래 비슷한 것들이라 검사에서 뺀다 — 재조합 결과가
        원본과 닮은 것은 정상이다. 그룹 **밖**과 겹치는 것이 문제다.
        """
        service = _similarity()
        if service is None:
            return None

        rows = (await self.db.execute(
            select(MainTitle.title, MainTitle.group_id)
            .where(MainTitle.status.in_(["available", "used"]))
            .order_by(MainTitle.id.desc())
            .limit(SIMILARITY_SCAN)
        )).all()

        for title, group_id in rows:
            if origin.group_id and group_id == origin.group_id:
                continue
            if not title or title == origin.title:
                continue
            try:
                verdict = service.calculate_similarity_v3(text, title)
            except Exception:  # noqa: BLE001
                continue
            if verdict.get("groupable"):
                return title
        return None

    async def _retry_distinct(self, row: MainTitle, module_id: int,
                              style: Optional[str], provider: Optional[str],
                              model: Optional[str],
                              clash: str) -> Optional[str]:
        """**한 번만** 다시 만든다.

        무한히 재시도하면 AI 호출이 통제를 벗어난다. 한 번 더 해서도
        겹치면 만들지 않는 편이 낫다.
        """
        if self.recombiner is None:
            return None
        keywords = await self._keywords(row)
        try:
            result = await self.recombiner.recombine(
                original_title=f"{row.title}\n\n(주의: \"{clash}\" 와 겹치지 "
                               f"않는 각도로 쓰세요)",
                module_id=module_id, provider=provider, model=model,
                style=style, keywords=keywords)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RECOMBINE] 재시도 실패 | %s", e)
            return None

        text = (result.recombined_title or "").strip()
        if not text or text == row.title:
            return None
        return None if await self._too_similar(text, row) else text

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

    async def _default_provider(self) -> Optional[str]:
        """등록된 활성 AI 키에서 제공자를 고른다.

        수동 재조합에는 블로그가 없어 `blog.ai_config` 를 쓸 수 없다.
        고르지 않았다고 조용히 0건을 돌려주는 것보다, 쓸 수 있는 키를
        찾아 돌리는 편이 낫다.
        """
        from ...models.ai_api_key import AIApiKey

        try:
            return (await self.db.execute(
                select(AIApiKey.provider)
                .where(AIApiKey.user_id == self.user_id,
                       AIApiKey.is_active.is_(True),
                       AIApiKey.status == "active")
                .order_by(AIApiKey.priority.asc())
                .limit(1)
            )).scalar_one_or_none()
        except Exception as e:  # noqa: BLE001
            logger.warning("[RECOMBINE] 기본 AI 조회 실패 | %s", e)
            return None

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


REASON_LABEL = {
    "not_stale": "낡지 않아 갱신할 것이 없습니다(최신성 갱신 모드)",
    "already": "이미 재조합된 제목입니다",
    "duplicate": "기존 제목과 겹쳐 건너뛰었습니다",
    "no_ai": "재조합 AI 가 없습니다",
    "ai_error": "AI 호출이 실패했습니다",
    "unchanged": "제목이 바뀌지 않았습니다",
}


def _explain(reasons: Dict[str, int], total: int) -> Optional[str]:
    """0건일 때 사람이 읽을 사유. 가장 많은 것을 앞에 둔다."""
    if not reasons:
        return None
    ordered = sorted(reasons.items(), key=lambda x: -x[1])
    parts = [f"{REASON_LABEL.get(code, code)} {count}건"
             for code, count in ordered]
    return f"{total}건 중 — " + " · ".join(parts)


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
