"""자동완성 수집 — 구글·네이버.

자동완성은 **실제 검색 행동**에서 나온다. 검색광고 연관키워드보다 최신성이
강하고, 질문형·롱테일이 그대로 잡힌다. 국내외 키워드 도구들이 공통으로 쓰는
1차 확장 수단이다.

주의: 두 곳 다 **공식 API 가 아니다.** 차단·구조 변경에 대비해
    - 실패는 조용히 빈 목록으로 돌린다(회차 전체를 죽이지 않는다)
    - 호출 사이에 간격을 둔다
    - 응답 구조를 방어적으로 읽는다

확장 방식: 시드 뒤에 자모/숫자를 붙여 여러 번 부르면 더 많이 긁을 수 있지만,
    호출이 시드당 수십 배가 된다. 여기서는 시드 그대로 1회만 부른다.
    깊게 파는 것은 클러스터 단계에서 유망 시드에만 적용한다.

계획서: docs/plans/keyword_module_redesign_plan.md §4-1
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional

import httpx

from ....core.logger import get_logger
from .base import (
    SRC_GOOGLE_SUGGEST, SRC_NAVER_SUGGEST, KeywordIdea, normalize,
)

logger = get_logger("keyword_suggest", "app.log")

GOOGLE_URL = "https://suggestqueries.google.com/complete/search"
NAVER_URL = "https://ac.search.naver.com/nx/ac"

TIMEOUT = 8.0

# 호출 간격(초). 상대 서비스에 부담을 주지 않는다.
CALL_DELAY = 0.3

# 시드 하나에서 가져올 최대 제안 수
PER_SEED_LIMIT = 10


async def google_suggest(seed: str, limit: int = PER_SEED_LIMIT,
                         client: Optional[httpx.AsyncClient] = None,
                         ) -> List[KeywordIdea]:
    """구글 자동완성 제안.

    `client=firefox` 응답은 [질의, [제안...]] 형태의 JSON 배열이다.
    """
    params = {"client": "firefox", "hl": "ko", "gl": "kr", "q": seed}
    data = await _get_json(GOOGLE_URL, params, client)
    if not isinstance(data, list) or len(data) < 2:
        return []
    return _to_ideas(data[1], seed, SRC_GOOGLE_SUGGEST, "google", limit)


async def naver_suggest(seed: str, limit: int = PER_SEED_LIMIT,
                        client: Optional[httpx.AsyncClient] = None,
                        ) -> List[KeywordIdea]:
    """네이버 자동완성 제안.

    응답의 `items` 는 [[["키워드", ...], ...]] 처럼 중첩돼 있다. 구조가
    바뀌어도 죽지 않도록 첫 문자열만 방어적으로 꺼낸다.
    """
    params = {"q": seed, "st": "100", "r_format": "json",
              "r_enc": "UTF-8", "r_unicode": "0", "t_koreng": "1", "ans": "2"}
    data = await _get_json(NAVER_URL, params, client)
    if not isinstance(data, dict):
        return []

    words: List[str] = []
    for group in data.get("items") or []:
        for row in group or []:
            word = row[0] if isinstance(row, list) and row else row
            if isinstance(word, str):
                words.append(word)
    return _to_ideas(words, seed, SRC_NAVER_SUGGEST, "naver", limit)


async def collect(seeds: List[str], engine: str,
                  limit_per_seed: int = PER_SEED_LIMIT) -> List[KeywordIdea]:
    """시드 목록에서 자동완성을 모은다.

    Args:
        seeds: 시드 키워드 목록
        engine: "google" | "naver"
        limit_per_seed: 시드당 최대 제안 수

    Returns:
        키워드 아이디어 목록(실패한 시드는 조용히 건너뛴다)
    """
    fetch = google_suggest if engine == "google" else naver_suggest
    out: List[KeywordIdea] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for seed in seeds:
            out.extend(await fetch(seed, limit_per_seed, client))
            await asyncio.sleep(CALL_DELAY)
    logger.info("[SUGGEST] %s | 시드 %d개 → 제안 %d개",
                engine, len(seeds), len(out))
    return out


def _to_ideas(words: Any, seed: str, source: str, engine: str,
              limit: int) -> List[KeywordIdea]:
    """문자열 목록을 아이디어로 바꾼다. 시드 자신은 뺀다."""
    out: List[KeywordIdea] = []
    seen = {seed.strip().lower()}
    for word in words or []:
        text = normalize(word if isinstance(word, str) else "")
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(KeywordIdea(keyword=text, source=source, engine=engine,
                               seed=seed))
        if len(out) >= limit:
            break
    return out


async def _get_json(url: str, params: dict,
                    client: Optional[httpx.AsyncClient]) -> Any:
    """공식 API 가 아니다 — 실패는 빈 값으로 돌리고 회차를 죽이지 않는다."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            logger.warning("[SUGGEST] %s | HTTP %s", url, response.status_code)
            return None
        return response.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("[SUGGEST] %s | %s", url, e)
        return None
    finally:
        if own:
            await client.aclose()
