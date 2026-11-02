"""4단계 검색량 재기 — 후보 전부를 네이버 검색광고 API 로 잰다(0원).

한 번에 5개까지 묻는다. 응답에 딸려 오는 연관어 검색량도 기억해 다음 묻기를 줄인다.
같은 말은 회차 안에서 한 번만, 채택 검색어 창고에 이미 잰 값이 있으면 그 값을 쓴다.

순서도: docs/flowcharts/title_screen_d.md (4)
"""
from __future__ import annotations

import asyncio
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger

logger = get_logger("title_screen", "app.log")

PAUSE_SEC = 0.25        # 묻기 사이 쉼(검색광고 API 초당 한도 보호)
BACKOFF_SEC = 20.0      # 한도에 걸리면 이만큼 쉬고 한 번 더


def norm_col(col):
    """DB 쪽 열쇠(공백 뺀 소문자). 묶기(GROUP BY)가 같은 식으로 보이게 상수를 글자로 넣는다."""
    return func.replace(func.lower(col), literal_column("' '"), literal_column("''"))


def key(text: str) -> str:
    """비교용 열쇠 — 공백 뺀 소문자(네이버도 공백을 떼고 돌려준다)."""
    return "".join((text or "").split()).lower()


class VolumeMeter:
    """검색량 기억 + 묶어 묻기."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.cache: Dict[str, int] = {}
        self.calls = 0
        self.failed = 0
        self._service = None

    async def _client(self):
        """검색광고 서비스(설정 없으면 None)."""
        if self._service is None:
            from ...models.user_settings import UserSettings
            from ..naver_ads_service import NaverAdsService

            settings = (await self.db.execute(select(UserSettings).where(
                UserSettings.user_id == self.user_id))).scalar_one_or_none()
            service = NaverAdsService(settings)
            self._service = service if settings and service.is_configured() else False
        return self._service or None

    async def warm(self, words: Iterable[str]) -> None:
        """창고(keyword_candidates)에 이미 잰 값을 먼저 담는다."""
        from ...models.keyword_candidate import KeywordCandidate

        want = {key(w) for w in words if w} - set(self.cache)
        if not want:
            return
        norm = norm_col(KeywordCandidate.keyword)
        rows = (await self.db.execute(
            select(norm, func.max(KeywordCandidate.search_volume))
            .where(norm.in_(list(want)), KeywordCandidate.search_volume.is_not(None))
            .group_by(norm))).all()
        for k, vol in rows:
            self.cache[k] = int(vol or 0)

    async def measure(self, words: Iterable[str]) -> Dict[str, int]:
        """말 목록 → {열쇠: 한 달 검색량}. 못 잰 말은 결과에 없다."""
        words = [w for w in dict.fromkeys(w.strip() for w in words if w and w.strip())]
        await self.warm(words)
        todo = [w for w in words if key(w) not in self.cache]
        service = await self._client()
        if service:
            for i in range(0, len(todo), 5):
                await self._ask(service, [w for w in todo[i:i + 5] if key(w) not in self.cache])
        return {key(w): self.cache[key(w)] for w in words if key(w) in self.cache}

    async def _ask(self, service, chunk: List[str]) -> None:
        """5개 묶음 한 번. 한도(429)면 쉬고 한 번 더."""
        if not chunk:
            return
        for attempt in range(2):
            self.calls += 1
            res = await service.get_keyword_stats(chunk, include_related=False)
            await asyncio.sleep(PAUSE_SEC)
            if res.get("success"):
                self._store(res, chunk)
                return
            if res.get("status_code") == 429 and attempt == 0:
                await asyncio.sleep(BACKOFF_SEC)
                continue
            self.failed += 1
            logger.warning("[TITLE_SCREEN] 검색량 실패 | %s | %s", chunk, res.get("error"))
            return

    def _store(self, res: dict, chunk: List[str]) -> None:
        """응답을 기억한다. 응답에 없는 입력어는 0(검색 거의 없음)."""
        for row in res.get("keywords") or []:
            k = key(row.get("keyword") or "")
            if k:
                self.cache[k] = max(self.cache.get(k, 0), int(row.get("total_search_volume") or 0))
        for w in chunk:
            self.cache.setdefault(key(w), 0)


def biggest(cands: List[str], vols: Dict[str, int]) -> Optional[tuple]:
    """후보 중 검색량이 가장 큰 (말, 검색량). 잰 것이 없으면 None."""
    scored = [(vols[key(c)], c) for c in cands if key(c) in vols]
    if not scored:
        return None
    vol, word = max(scored, key=lambda x: x[0])
    return word, vol
