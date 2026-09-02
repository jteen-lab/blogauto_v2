"""질문 팬아웃 — 채택 키워드에서 **사람이 실제로 치는 질문**을 뽑는다.

배경:
    옛 파이프라인은 제목을 긁어 재고로 썼다. 니치 무관·저품질이 섞여
    통과율이 2% 였다. 소재를 제목이 아니라 **질문**으로 바꾼다. 질문은
    니치 판정이 쉬워, 이미 있는 분류·필터를 그대로 통과시킬 수 있다.

방식:
    키워드에 의문사·조사를 붙여 자동완성에 되묻는다. 돌아오는 것은
    **실제 검색량이 있는 질문형 쿼리**다.

        "전기기사 실기" + "왜"     → "전기기사 실기 왜 어려운가"
        "전기기사 실기" + "어떻게" → "전기기사 실기 어떻게 준비"

PAA(People Also Ask)를 쓰지 않는 이유:
    구글이 공식 API 로 제공하지 않는다. 가져오려면 검색 결과 페이지
    스크래핑이 필요한데 약관 위반이고, 차단되면 파이프라인이 멈춘다.
    자동완성으로 대체 가능하므로 감수할 이유가 없다.

계획서: docs/plans/title_pipeline_redesign_plan.md §2-2
순서도: docs/flowcharts/title_pipeline.md §2
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

import httpx

from ....core.logger import get_logger
from .base import SRC_QUESTION_FANOUT, KeywordIdea
from .suggest import CALL_DELAY, TIMEOUT, google_suggest, naver_suggest

logger = get_logger("keyword_questions", "app.log")

# 붙일 의문사. 검색창에 실제로 이어 치는 말들이다.
# 많이 붙일수록 호출이 선형으로 늘어난다 — 축이 겹치지 않는 것만 고른다.
PROBES = ("왜", "어떻게", "언제", "얼마", "어디", "뭐")

# 키워드 하나에서 가져올 최대 질문 수. 팬아웃은 8~10개로 수렴한다.
PER_KEYWORD_LIMIT = 10

# 질문으로 볼 최소 길이. 시드에 한 글자 붙은 것은 질문이 아니다.
MIN_LENGTH = 6


def is_question(text: str, seed: str) -> bool:
    """질문형으로 볼 수 있는가.

    의문사가 들어 있고 시드보다 충분히 길어야 한다. 자동완성은 시드를
    그대로 되돌려 주기도 하는데 그것은 질문이 아니다.
    """
    if not text or len(text) < MIN_LENGTH:
        return False
    if text.strip().lower() == (seed or "").strip().lower():
        return False
    return any(probe in text for probe in PROBES)


async def fan_out(keyword: str, engine: str = "naver",
                  limit: int = PER_KEYWORD_LIMIT,
                  client: Optional[httpx.AsyncClient] = None,
                  ) -> List[KeywordIdea]:
    """키워드 하나를 질문들로 펼친다.

    실패한 의문사는 조용히 건너뛴다 — 하나가 막혀도 나머지는 쓸 수 있다.
    """
    suggest = google_suggest if engine == "google" else naver_suggest
    out: List[KeywordIdea] = []
    seen = {keyword.strip().lower()}

    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        for probe in PROBES:
            if len(out) >= limit:
                break
            ideas = await suggest(f"{keyword} {probe}", limit, client)
            for idea in ideas:
                text = idea.keyword.strip()
                if text.lower() in seen or not is_question(text, keyword):
                    continue
                seen.add(text.lower())
                out.append(KeywordIdea(
                    keyword=text, source=SRC_QUESTION_FANOUT, engine=engine,
                    seed=keyword))
                if len(out) >= limit:
                    break
            await asyncio.sleep(CALL_DELAY)
    finally:
        if own:
            await client.aclose()

    logger.info("[QUESTIONS] %s | %s → 질문 %d개", engine, keyword, len(out))
    return out


async def collect(seeds: List[str], engine: str = "naver",
                  limit_per_seed: int = PER_KEYWORD_LIMIT,
                  ) -> List[KeywordIdea]:
    """시드 목록을 질문으로 펼친다. 다른 소스와 같은 모양을 돌려준다."""
    out: List[KeywordIdea] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for seed in seeds:
            out.extend(await fan_out(seed, engine, limit_per_seed, client))
    logger.info("[QUESTIONS] 시드 %d개 → 질문 %d개", len(seeds), len(out))
    return out
