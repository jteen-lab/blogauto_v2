"""생성된 제목을 **기존 관문**에 태워 재고에 넣는다.

지금까지 키워드 모듈은 `main_titles` 에 직접 꽂았다. 그래서 금지어 필터도,
유사도 그룹핑도, 중복 검사도 거치지 않은 제목이 재고에 들어갔다.
분류에 실패한 제목은 카테고리가 비어 어느 블로그도 꺼내 쓸 수 없는
**사장 재고**가 됐다(검토서 D-5·D-7).

여기서는 기존 수집이 쓰는 길을 그대로 쓴다.

    제목 → 금지어 필터 → 카테고리 분류 → temp_titles
         → (분류 성공분만) TitleTransferService.move_to_main
         → 중복 검사 + 유사도 그룹핑 → main_titles

분류에 실패한 제목은 **temp_titles 에 남긴다.** 버리지 않는 이유는 그것이
곧 회수 큐이기 때문이다 — 데이터 관리 화면에서 재분류해 다시 올릴 수 있고,
분류표에 무엇이 빠져 있는지도 알려 준다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.content_filter import ContentFilter
from ...models.keyword_candidate import KeywordCandidate
from ...models.title import MainTitle, TempTitle

logger = get_logger("keyword_title_gate", "app.log")

# 재고에 남는 출처 표시. 기존 수집(transfer)과 성과를 비교할 수 있게 한다.
SOURCE = "keyword_module"

# TempTitle.collection_stage — 어디서 온 제목인지
COLLECTION_STAGE = "keyword_module"

# 필터 대상 구분(ContentFilter.target_type)
FILTER_TARGET = "title"


def blocking_filter(filters: List[ContentFilter],
                    text: str) -> Optional[ContentFilter]:
    """금지어/패턴에 걸리는지. 걸리면 그 필터를 돌려준다.

    판정 규칙은 기존 수집(`keyword_collector_service._check_filter`)과 같다.
    target_type 이 'both' 인 필터는 모든 대상에 적용된다.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return None

    for row in filters:
        target = (row.target_type or "both").lower().strip()
        if target not in (FILTER_TARGET, "both"):
            continue
        value = (row.filter_value or "").lower().strip()
        if not value:
            continue

        kind = (row.filter_type or "keyword").lower().strip()
        if kind == "pattern":
            try:
                hit = bool(re.search(value, lowered))
            except re.error:
                logger.warning("[TITLE_GATE] 잘못된 정규식 | %s", value)
                continue
        else:  # keyword / domain — 둘 다 포함 여부로 판정한다
            hit = value in lowered

        if hit:
            return row
    return None


class TitleGate:
    """제목을 관문에 태워 재고로 승격한다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self._filters: Optional[List[ContentFilter]] = None
        self._matcher: Any = "unset"

    async def admit(self, titles: List[str],
                    row: KeywordCandidate) -> Dict[str, int]:
        """제목 목록을 관문에 태운다.

        Args:
            titles: 생성된 제목 목록
            row: 이 제목들을 만든 키워드 후보(분류 폴백에 쓴다)

        Returns:
            {"admitted": 재고 진입 수, "blocked": 필터 차단 수,
             "queued": 미분류로 남긴 수, "duplicates": 중복 수}
        """
        staged, blocked, queued = [], 0, 0
        filters = await self._load_filters()

        for title in titles:
            hit = blocking_filter(filters, title)
            if hit:
                blocked += 1
                logger.info("[TITLE_GATE] 필터 차단 | %s | 필터=%s",
                            title[:40], hit.filter_value)
                continue

            topic_id, subtopic_id, kw_id = await self._classify(title, row)
            temp = self._build_temp(title, topic_id, subtopic_id, kw_id)
            self.db.add(temp)
            staged.append((temp, bool(topic_id or subtopic_id)))

        await self.db.flush()
        ready = [t.id for t, ok in staged if ok]
        queued = sum(1 for _, ok in staged if not ok)

        moved = await self._move(ready, row.keyword)
        logger.info(
            "[TITLE_GATE] 제목 %d편 | 재고 %d · 차단 %d · 미분류 %d · 중복 %d",
            len(titles), moved.get("moved", 0), blocked, queued,
            moved.get("duplicates", 0),
        )
        return {
            "admitted": moved.get("moved", 0),
            "blocked": blocked,
            "queued": queued,
            "duplicates": moved.get("duplicates", 0),
        }

    # ── 내부 ─────────────────────────────────────────────
    async def _move(self, temp_ids: List[int],
                    keyword: str) -> Dict[str, Any]:
        """분류된 임시 제목만 정식 재고로 옮긴다(중복·유사도 그룹핑 포함)."""
        if not temp_ids:
            await self.db.commit()
            return {"moved": 0, "duplicates": 0}

        from ..title_transfer_service import TitleTransferService

        service = TitleTransferService(self.db, user_id=self.user_id)
        result = await service.move_to_main(temp_ids, auto_group=True)
        await self._stamp(temp_ids, keyword)
        return result

    async def _stamp(self, temp_ids: List[int], keyword: str) -> None:
        """출처와 원본 키워드를 재고에 남긴다.

        이관 서비스는 source 를 'transfer' 로 적는다. 기존 수집분과 성과를
        비교하려면 어느 쪽에서 온 제목인지 구분이 남아 있어야 하고,
        어떤 키워드로 만든 제목인지도 남아야 나중에 되먹임에 쓸 수 있다.
        """
        rows = (await self.db.execute(
            select(MainTitle).where(
                MainTitle.source_temp_title_id.in_(temp_ids))
        )).scalars().all()
        for row in rows:
            row.source = SOURCE
            row.keywords = json.dumps([keyword], ensure_ascii=False)
        if rows:
            await self.db.commit()

    def _build_temp(self, title: str, topic_id: Optional[int],
                    subtopic_id: Optional[int],
                    matched_keyword_id: Optional[int]) -> TempTitle:
        """임시 제목 행을 만든다. 분류 성공 여부를 status 로 남긴다."""
        classified = bool(topic_id or subtopic_id)
        return TempTitle(
            title=title,
            source_blog_url="",
            source_post_url="",
            collection_stage=COLLECTION_STAGE,
            status="categorized" if classified else "new",
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            matched_keyword_id=matched_keyword_id,
        )

    async def _classify(
        self, title: str, row: KeywordCandidate,
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """제목을 분류한다. 실패하면 **키워드 자신의 분류**로 폴백한다.

        제목에는 키워드가 들어 있으므로 보통 같은 카테고리가 나온다. 폴백은
        시드 카테고리를 물려주는 것과 다르다 — 이미 검증된 그 키워드의
        분류를 쓰는 것이라 엉뚱한 카테고리로 새지 않는다.
        """
        matcher = await self._get_matcher()
        if matcher:
            try:
                topic_id, subtopic_id, kw_id = \
                    await matcher.match_and_apply_to_title(title)
                if topic_id or subtopic_id:
                    return topic_id, subtopic_id, kw_id
            except Exception as e:  # noqa: BLE001
                logger.warning("[TITLE_GATE] 분류 실패 | %s | %s", title[:30], e)
        return row.topic_id, row.subtopic_id, None

    async def _get_matcher(self):
        if self._matcher == "unset":
            try:
                from ..category_matcher_service import CategoryMatcherService

                self._matcher = CategoryMatcherService(self.db, self.user_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("[TITLE_GATE] 분류기 초기화 실패 | %s", e)
                self._matcher = None
        return self._matcher

    async def _load_filters(self) -> List[ContentFilter]:
        """활성 금지어 필터. 한 회차에 한 번만 읽는다."""
        if self._filters is None:
            self._filters = list((await self.db.execute(
                select(ContentFilter).where(ContentFilter.is_active.is_(True))
            )).scalars().all())
            logger.info("[TITLE_GATE] 활성 필터 %d개", len(self._filters))
        return self._filters
