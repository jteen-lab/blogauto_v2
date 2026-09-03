"""L3 시의성 생성 — 뉴스 요지 + 우리 니치 키워드.

**L1(키워드 기반 AI 생성)이 못 하는 자리를 메운다.** AI 는 이번 주에 무슨
일이 있었는지 모른다. 뉴스는 그것을 안다.

**원문 제목을 재고에 넣지 않는다.** L2(각도 신호)와 같은 원칙이다. 옛
`news_collect` 가 원문을 그대로 임시제목에 넣어 18,315건이 쌓였고, 대부분
최신성이 만료된 남의 제목이었다.

    [옛] 뉴스 제목 ──────────────────→ 임시제목(재고)
    [새] 뉴스 → 요지 추출 → 니치 키워드와 결합 → AI 제목 → 관문

예: "전기요금 개편안 발표"(뉴스) + "전기기사"(니치)
  → "전기요금 개편이 전기기사 수요에 미치는 영향"

만든 제목에는 **만료일**을 박는다. 뉴스 소재는 2주 뒤면 낡는다. L1 제목에
없는 성질이라 `expires_at` 을 따로 둔다.

계획서: docs/plans/title_tab_workplan.md §3-2
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.keyword_candidate import KeywordCandidate

logger = get_logger("title_news_gen", "app.log")

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&[a-z#0-9]+;")

DEFAULT_DAYS = 3
DEFAULT_LIMIT = 10
DEFAULT_EXPIRES_DAYS = 14

# 뉴스 하나에서 뽑을 요지 길이 상한. 문장을 통째로 넣으면 AI 가 원문을
# 따라 쓴다.
GIST_MAX = 60


def clean(text: str) -> str:
    """태그·엔티티를 걷어낸다."""
    out = TAG_RE.sub("", text or "")
    out = ENTITY_RE.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


def gist(title: str, description: str = "") -> str:
    """'무슨 일이 있었나' 만 남긴다.

    원문을 그대로 쓰지 않는다는 원칙을 여기서 지킨다. 제목을 짧게 자르고
    수식어를 덜어 **사건만** 남긴다.
    """
    text = clean(title) or clean(description)
    if not text:
        return ""
    # 언론사 관용구·꾸밈말을 덜어낸다
    text = re.sub(r"^\[[^\]]{1,12}\]\s*", "", text)
    text = re.sub(r"\s*[\|·]\s*[^|·]{0,20}$", "", text)
    return text[:GIST_MAX].strip()


def expires_at(days: int = DEFAULT_EXPIRES_DAYS) -> datetime:
    """만료 시각. 지나면 재고 선택에서 빠진다(삭제는 안 한다)."""
    return datetime.now(timezone.utc) + timedelta(days=max(1, days))


class NewsTitleGenerator:
    """뉴스 요지와 니치 키워드를 엮어 제목을 만든다."""

    def __init__(self, db: AsyncSession, user_id: int, news_service: Any,
                 ask: Any = None):
        self.db = db
        self.user_id = user_id
        self.news = news_service
        # ask(prompt) -> str. 없으면 규칙 결합만 한다.
        self.ask = ask
        self.last_error: Optional[str] = None

    async def run(self, days: int = DEFAULT_DAYS, limit: int = DEFAULT_LIMIT,
                  ) -> Dict[str, Any]:
        """한 회차. 채택 키워드마다 관련 뉴스를 찾아 제목을 만든다."""
        keywords = await self._keywords(limit)
        if not keywords:
            self.last_error = "채택된 키워드가 없습니다"
            return {"made": 0, "titles": [], "error": self.last_error}

        made: List[Dict[str, Any]] = []
        for row in keywords:
            gists = await self._gists(row.keyword, days)
            if not gists:
                continue
            title = await self._compose(row.keyword, gists[0])
            if title:
                made.append({"title": title, "keyword": row.keyword,
                             "candidate_id": row.id, "gist": gists[0]})
            if len(made) >= limit:
                break

        logger.info("[NEWS_GEN] 키워드 %d개 → 제목 %d개",
                    len(keywords), len(made))
        return {"made": len(made), "titles": made, "error": self.last_error}

    async def _keywords(self, limit: int) -> List[KeywordCandidate]:
        """채택 키워드. 시의성은 검색량이 큰 쪽이 유리하다."""
        from ..keyword_lab.scoring import VERDICT_ADOPT

        return list((await self.db.execute(
            select(KeywordCandidate)
            .where(KeywordCandidate.user_id == self.user_id,
                   KeywordCandidate.verdict == VERDICT_ADOPT)
            .order_by(KeywordCandidate.search_volume.desc().nullslast())
            .limit(max(1, limit) * 2)
        )).scalars().all())

    async def _gists(self, keyword: str, days: int) -> List[str]:
        """이 키워드로 최근 무슨 일이 있었나. 실패는 빈 목록."""
        try:
            result = await self.news.search_news(keyword, display=10,
                                                 sort="date")
        except Exception as e:  # noqa: BLE001
            logger.warning("[NEWS_GEN] 뉴스 조회 실패 | %s | %s", keyword, e)
            return []
        if not result.get("success"):
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        out = []
        for item in result.get("items") or []:
            if not _within(item.get("pubDate"), cutoff):
                continue
            text = gist(item.get("title", ""), item.get("description", ""))
            if text and text not in out:
                out.append(text)
        return out

    async def _compose(self, keyword: str, news_gist: str) -> Optional[str]:
        """요지와 키워드를 엮는다. AI 가 없으면 규칙으로 붙인다."""
        if self.ask is None:
            return f"{news_gist}, {keyword}에는 어떤 영향이 있을까"

        prompt = (
            f"최근 이런 일이 있었습니다: \"{news_gist}\"\n"
            f"우리 블로그 주제는 \"{keyword}\" 입니다.\n\n"
            "이 사건이 우리 주제에 어떤 의미인지 다루는 블로그 제목을 "
            "**하나만** 쓰세요.\n"
            "- 뉴스 제목을 그대로 옮기지 마세요\n"
            "- 우리 주제와의 연결이 제목에서 보여야 합니다\n"
            "- 제목만 출력하세요")
        try:
            answer = await self.ask(prompt)
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)[:150]
            logger.warning("[NEWS_GEN] 생성 실패 | %s", e)
            return None
        text = clean(answer or "").strip().strip('"').split("\n")[0]
        return text[:200] or None


def _within(pub_date: Optional[str], cutoff: datetime) -> bool:
    """발행 시각이 기간 안인가. 파싱 실패는 통과시킨다 — 뉴스를 통째로
    버리는 것보다 낫다."""
    if not pub_date:
        return True
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(pub_date, fmt) >= cutoff
        except (ValueError, TypeError):
            continue
    return True
