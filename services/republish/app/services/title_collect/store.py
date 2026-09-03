"""수집한 제목을 임시제목으로 저장한다 — 기존 관문을 그대로 탄다.

새 검사를 만들지 않는다. 이미 쓰던 길을 쓴다.

    제목 → 금지어 필터 → 카테고리 분류 → **니치 대조(신규)** → temp_titles

금지어 필터와 분류는 이미 있던 것이다(`blocking_filter`·`CategoryMatcherService`).
니치 대조 하나만 새로 붙는다 — "분류는 됐지만 그 주제를 쓰는 블로그가
없는" 제목을 가려내기 위해서다.

중복은 제목 문자열로 막는다. 같은 글이 여러 키워드로 잡히는 일이 흔하다.

계획서: docs/plans/title_tab_workplan.md §2-4
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.content_filter import ContentFilter
from ...models.title import TempTitle
from ..keyword_lab.title_gate import blocking_filter
from .niche_gate import NicheGate, VERDICT_OFF, VERDICT_UNKNOWN

logger = get_logger("title_collect_store", "app.log")

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&[a-z]+;")

# 제목으로 볼 최소 길이. 잘린 조각은 재고가 못 된다.
MIN_LENGTH = 6


def clean(title: str) -> str:
    """검색 결과 제목의 태그·엔티티를 걷어낸다."""
    text = TAG_RE.sub("", title or "")
    text = ENTITY_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


class TitleStore:
    """제목 하나를 관문에 태워 저장한다. 회차 동안 상태를 재사용한다."""

    def __init__(self, db: AsyncSession, user_id: int, gate: NicheGate):
        self.db = db
        self.user_id = user_id
        self.gate = gate
        self.samples: List[str] = []
        self._filters: Optional[List[ContentFilter]] = None
        self._matcher = None
        self._seen: Set[str] = set()

    async def add(self, title: str, url: str, keyword: str,
                  candidate_id: Optional[int], source: str,
                  expires_at: Any = None) -> Dict[str, Any]:
        """제목 하나를 저장 시도.

        Returns:
            {"stored": bool, "reason": str, "domain": str|None}
        """
        from ..title_gen.niche import host_of

        # 도메인은 저장 여부와 무관하게 돌려준다. 걸러진 제목이 있던
        # 도메인에도 쓸 만한 글이 있을 수 있고, 추출은 도메인 단위로 돈다.
        host = host_of(url)

        text = clean(title)
        if len(text) < MIN_LENGTH:
            return {"stored": False, "reason": "too_short", "domain": host}

        key = text.lower()
        if key in self._seen:
            return {"stored": False, "reason": "duplicate", "domain": host}

        if await self._is_duplicate(text):
            self._seen.add(key)
            return {"stored": False, "reason": "duplicate", "domain": host}

        if blocking_filter(await self._load_filters(), text, "title"):
            self._seen.add(key)
            return {"stored": False, "reason": "filtered", "domain": host}

        topic_id, subtopic_id, matched_id = await self._classify(text)
        if not await self.gate.should_store(topic_id):
            self._seen.add(key)
            return {"stored": False, "reason": "off_niche", "domain": host}

        verdict = await self.gate.judge(topic_id)
        self.db.add(TempTitle(
            title=text, source_blog_url=url or "", source_post_url=url or "",
            collection_stage=source,
            status="categorized" if topic_id else "new",
            topic_id=topic_id, subtopic_id=subtopic_id,
            matched_keyword_id=matched_id, candidate_id=candidate_id,
            expires_at=expires_at,
            filter_reason=_reason(verdict)))
        self._seen.add(key)
        if len(self.samples) < 100:
            self.samples.append(text)
        return {"stored": True, "reason": "ok", "domain": host}

    async def _load_filters(self) -> List[ContentFilter]:
        """활성 필터. 조회가 실패해도 회차를 죽이지 않는다."""
        if self._filters is None:
            try:
                self._filters = list((await self.db.execute(
                    select(ContentFilter).where(
                        ContentFilter.is_active.is_(True))
                )).scalars().all())
            except Exception as e:  # noqa: BLE001
                logger.warning("[TITLE_STORE] 필터 로드 실패 | %s", e)
                self._filters = []
        return self._filters

    async def _classify(self, title: str):
        """카테고리 분류. 실패는 미분류(회수 큐)로 둔다."""
        if self._matcher is None:
            from ..category_matcher_service import CategoryMatcherService

            self._matcher = CategoryMatcherService(self.db, self.user_id)
        try:
            matched = await self._matcher.match_category(title)
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_STORE] 분류 실패 | %s", e)
            return None, None, None
        if not matched:
            return None, None, None
        return (matched.get("topic_id"), matched.get("subtopic_id"),
                matched.get("matched_keyword_id"))

    async def _is_duplicate(self, title: str) -> bool:
        """이미 있는 제목인가. 같은 글이 여러 키워드로 잡히는 일이 흔하다."""
        found = (await self.db.execute(
            select(TempTitle.id).where(TempTitle.title == title).limit(1)
        )).scalar_one_or_none()
        return found is not None


def _reason(verdict: str) -> Optional[str]:
    """화면이 왜 걸렸는지 말할 수 있게 사유를 적는다."""
    if verdict == VERDICT_OFF:
        return "니치 무관"
    if verdict == VERDICT_UNKNOWN:
        return "미분류"
    return None
