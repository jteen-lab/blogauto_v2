"""채택 키워드로 제목을 미리 만들어 재고에 넣는다.

지금은 발행 시점에 AI 가 제목을 만든다. 실패하면 그 회차를 통째로
건너뛴다(수작남이 3회 연속 그랬다). 미리 만들어 두면 발행 시점에는
**꺼내 쓰기만** 하므로 시간도 실패도 늘지 않는다.

기존 재고 구조를 그대로 쓴다 — main_titles, status='available'.
source 로 구분해 기존 수집(transfer)과 성과를 비교할 수 있게 한다.

순서도: docs/flowcharts/keyword_module.md
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate, VERDICT_ADOPT
from ...models.title import MainTitle
from .settings import KeywordModuleSettings

logger = get_logger("keyword_title_maker", "app.log")

SOURCE = "keyword_module"

PROMPT = """다음 키워드로 한국어 블로그 글 제목을 {count}개 지어 주세요.

키워드: {keyword}
월간 검색량: {volume}

지켜야 할 것
- 키워드를 제목에 자연스럽게 넣습니다.
- {count}개가 **서로 다른 질문**에 답해야 합니다. 같은 내용을 말만 바꾸지 마세요.
- 검색한 사람이 무엇을 알고 싶어 하는지 생각해 그 답을 예고하는 제목으로.
- 낚시성 표현("충격", "이것만 알면")과 과장을 쓰지 마세요.
- 25~45자.
- 번호·따옴표·군더더기 없이 제목만 한 줄에 하나씩 출력하세요."""


class TitleMaker:
    """키워드 하나에서 제목 여러 개를 만든다."""

    def __init__(self, db: AsyncSession, ai_service, user_id: int):
        self.db = db
        self.ai = ai_service
        self.user_id = user_id

    async def run(
        self, cfg: KeywordModuleSettings, blog, limit: int = 20,
    ) -> Dict[str, Any]:
        """채택됐고 아직 제목을 안 만든 키워드를 처리한다."""
        rows = await self._targets(blog, limit)
        if not rows:
            return {"success": True, "made": 0, "keywords": 0,
                    "message": "제목을 만들 키워드가 없습니다"}

        made, failed = 0, 0
        for row in rows:
            titles = await self._generate(row, cfg, blog)
            if not titles:
                failed += 1
                continue
            made += await self._save(titles, row)
            # 다시 만들지 않도록 표시. promoted 는 시드 재사용 표시와
            # 겸용이다 — 둘 다 "이미 썼다" 는 뜻이라 같은 칸을 쓴다.
            row.promoted = True

        await self.db.commit()
        logger.info("[TITLE_MAKER] 키워드 %d개 → 제목 %d편 | 실패 %d",
                    len(rows), made, failed)
        return {"success": True, "made": made, "keywords": len(rows),
                "failed": failed}

    async def _targets(self, blog, limit: int) -> List[KeywordCandidate]:
        q = (select(KeywordCandidate)
             .where(KeywordCandidate.user_id == self.user_id,
                    KeywordCandidate.verdict == VERDICT_ADOPT,
                    KeywordCandidate.promoted.is_(False))
             .order_by(KeywordCandidate.search_volume.desc().nullslast())
             .limit(limit))
        if blog is not None:
            q = q.where(KeywordCandidate.blog_id == blog.id)
        return list((await self.db.execute(q)).scalars().all())

    async def _generate(self, row: KeywordCandidate,
                        cfg: KeywordModuleSettings, blog) -> List[str]:
        prompt = PROMPT.format(
            keyword=row.keyword, count=cfg.titles_per_keyword,
            volume=row.search_volume or "알 수 없음")
        writing = (getattr(blog, "ai_config", None) or {}).get("writing_ai", {}) \
            if blog is not None else {}
        try:
            result = await self.ai.generate(
                prompt=prompt,
                provider=writing.get("provider"),
                model=writing.get("model"),
                max_tokens=600,
                temperature=0.9,   # 제목은 다양해야 한다
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[TITLE_MAKER] 생성 실패 | %s | %s", row.keyword, e)
            return []

        text = ((result or {}).get("content") or "").strip()
        return self._parse(text, cfg.titles_per_keyword)

    @staticmethod
    def _parse(text: str, count: int) -> List[str]:
        """모델이 붙이는 번호·따옴표·군더더기를 걷어낸다."""
        out, seen = [], set()
        for line in (text or "").splitlines():
            t = line.strip()
            t = re.sub(r"^[-*•]\s*", "", t)
            t = re.sub(r"^\d+[.)]\s*", "", t)
            t = t.strip(" \"'“”‘’")
            if len(t) < 8 or len(t) > 120:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= count:
                break
        return out

    async def _save(self, titles: List[str], row: KeywordCandidate) -> int:
        """재고에 넣는다. 이미 있는 제목은 건너뛴다."""
        saved = 0
        for title in titles:
            exists = (await self.db.execute(
                select(MainTitle.id).where(MainTitle.title == title).limit(1)
            )).first()
            if exists:
                continue
            self.db.add(MainTitle(
                title=title,
                status="available",
                source=SOURCE,
                topic_id=row.topic_id,
                subtopic_id=row.subtopic_id,
                keywords=json.dumps([row.keyword], ensure_ascii=False),
            ))
            saved += 1
        return saved
