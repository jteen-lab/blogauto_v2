"""커뮤니티 질문 수집 — 지식iN·카페.

**왜 필요한가**: 자동완성 팬아웃은 *검색창에 치는 쿼리*를 준다. 짧고 상황이
없다. 「이사 견적」에서 팬아웃이 주는 건 "이사 견적 어떻게" 까지고, 여기서
"같은 건물 2층에서 3층, 엘리베이터 없음, 장롱 3짝"은 나오지 않는다.
**조건을 붙이는 건 사람이다.** 그 문장이 있는 곳이 지식iN과 카페다.

    주제 = 니치 × 상황
           ↑        ↑
       우리가 보유   여기서만 나온다

**제약**: 검색 API는 제목과 짧은 설명만 준다. 본문은 링크를 크롤링해야
읽을 수 있다(2단계에서 `reference_crawling_service` 재사용).

**카페가 더 까다롭다**: 업체가 쓴 홍보글이 질문처럼 보인다. 그래서 판정을
지식iN보다 엄격하게 건다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §9
순서도: docs/flowcharts/topic_discovery.md §1
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ....core.logger import get_logger
from .base import SRC_NAVER_CAFE, SRC_NAVER_KIN, KeywordIdea, normalize

logger = get_logger("keyword_community", "app.log")

KIN_URL = "https://openapi.naver.com/v1/search/kin.json"
CAFE_URL = "https://openapi.naver.com/v1/search/cafearticle.json"

ENDPOINT = {SRC_NAVER_KIN: KIN_URL, SRC_NAVER_CAFE: CAFE_URL}

TIMEOUT = 10.0
CALL_DELAY = 0.3
PER_SEED_LIMIT = 30

# 질문으로 볼 신호. 하나라도 있어야 한다.
QUESTION_MARKS = (
    "?", "？", "어떻게", "어떤", "어디", "얼마", "언제", "왜", "무엇", "뭐",
    "인가요", "일까요", "할까요", "될까요", "있나요", "없나요", "하나요",
    "맞나요", "가능한가요", "괜찮을까요", "궁금", "알려주세요", "문의드",
    "조언", "추천해", "차이", "비교",
)

# 홍보글 신호. 하나라도 있으면 버린다. 카페에서 특히 많다.
PROMO_MARKS = (
    "최저가", "무료견적", "이벤트", "할인가", "특가", "상담문의", "견적문의",
    "카톡", "카카오톡 ", "오픈채팅", "공식홈", "바로가기", "신청하기",
    "010-", "1588", "1544", "1600-", "문의주세요", "연락주세요", "DM",
    "체험단", "협찬", "광고", "홍보", "모집합니다", "판매합니다",
)

# 상황이 실려 있다는 신호. 숫자+단위, 조건 접속어.
SITUATION_UNITS = ("평", "층", "cm", "mm", "m²", "만원", "천원", "원",
                   "kg", "km", "개월", "년차", "인승", "톤", "인치")
# "는데" 하나로 하는데·없는데·있는데·했는데를 다 덮는다. 조건을 붙여
# 말하는 어미라 상황이 실려 있다는 신호로 충분하다.
SITUATION_JOINTS = ("는데", "인데", "이라서", "라서", "예정", "상황",
                    "경우인데", "중입니다", "해야 하나", "해야 할지")

MIN_TITLE_LEN = 8
# 키워드 칸에 넣을 구절 상한. base.normalize 의 60자보다 먼저 자른다.
PHRASE_LIMIT = 58


@dataclass
class CommunityQuestion:
    """수집한 질문 하나. 2단계 상황 추출의 입력이 된다."""

    title: str
    link: str
    description: str
    source: str
    seed: str
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """판정·추출에 쓰는 합본."""
        return f"{self.title} {self.description}".strip()


def _clean(text: str) -> str:
    """HTML 태그·엔티티를 걷어낸다. 네이버 검색 API는 <b> 를 섞어 준다."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&apos;", "'"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def is_promo(text: str) -> bool:
    """홍보글인가. 하나라도 걸리면 버린다."""
    return any(mark in text for mark in PROMO_MARKS)


def is_question(text: str, strict: bool = False) -> bool:
    """질문으로 볼 수 있는가.

    Args:
        text: 제목+설명 합본
        strict: 카페용. 질문 신호에 더해 **상황 신호까지** 요구한다.
    """
    if not text or len(text) < MIN_TITLE_LEN:
        return False
    if not any(mark in text for mark in QUESTION_MARKS):
        return False
    return has_situation(text) if strict else True


def has_situation(text: str) -> bool:
    """상황이 실려 있는가.

    숫자에 단위가 붙었거나 조건 접속어가 있으면 구체적인 이야기다.
    """
    if any(joint in text for joint in SITUATION_JOINTS):
        return True
    return bool(re.search(
        r"\d+\s*(?:" + "|".join(map(re.escape, SITUATION_UNITS)) + ")", text))


def to_phrase(title: str, seed: str) -> str:
    """긴 질문 제목을 키워드 칸에 넣을 구절로 줄인다.

    원문은 `extra` 에 남는다. 여기서는 풀에 넣을 짧은 형태만 만든다.
    """
    text = _clean(title)
    text = re.sub(r"^(안녕하세요[.,!]?\s*|안녕하십니까[.,!]?\s*)", "", text)
    text = re.sub(r"[\[\(][^\]\)]{0,20}[\]\)]\s*", "", text).strip()
    if len(text) <= PHRASE_LIMIT:
        return normalize(text)
    # 문장 경계에서 자른다. 없으면 어절 경계.
    head = re.split(r"[.?!。]\s*", text)[0]
    if MIN_TITLE_LEN <= len(head) <= PHRASE_LIMIT:
        return normalize(head)
    cut = text[:PHRASE_LIMIT]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return normalize(cut or seed)


def _headers(user_settings: Any) -> Dict[str, str]:
    return {
        "X-Naver-Client-Id":
            getattr(user_settings, "naver_search_client_id", "") or "",
        "X-Naver-Client-Secret":
            getattr(user_settings, "naver_search_client_secret", "") or "",
    }


def is_configured(user_settings: Any) -> bool:
    """네이버 검색 API 자격증명이 있는가. 참조 검색과 같은 키를 쓴다."""
    head = _headers(user_settings)
    return bool(head["X-Naver-Client-Id"] and head["X-Naver-Client-Secret"])


async def fetch(user_settings: Any, seed: str, source: str,
                limit: int = PER_SEED_LIMIT,
                client: Optional[httpx.AsyncClient] = None,
                ) -> List[CommunityQuestion]:
    """시드 하나로 질문을 긁는다. 실패는 빈 목록 — 회차를 죽이지 않는다."""
    url = ENDPOINT.get(source)
    if not url or not is_configured(user_settings):
        return []

    params = {"query": seed.strip(), "display": min(limit, 100),
              "start": 1, "sort": "date"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        response = await client.get(url, headers=_headers(user_settings),
                                    params=params)
        if response.status_code != 200:
            logger.warning("[COMMUNITY] %s | HTTP %s", source,
                           response.status_code)
            return []
        items = (response.json() or {}).get("items") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("[COMMUNITY] %s | %s", source, e)
        return []
    finally:
        if own:
            await client.aclose()

    return _to_questions(items, seed, source)


def _to_questions(items: List[dict], seed: str,
                  source: str) -> List[CommunityQuestion]:
    """응답 항목을 질문으로. 홍보글과 비질문을 여기서 버린다."""
    strict = source == SRC_NAVER_CAFE
    out: List[CommunityQuestion] = []
    for item in items or []:
        title = _clean(item.get("title", ""))
        desc = _clean(item.get("description", ""))
        blob = f"{title} {desc}".strip()
        if is_promo(blob) or not is_question(blob, strict=strict):
            continue
        out.append(CommunityQuestion(
            title=title, link=item.get("link", ""), description=desc,
            source=source, seed=seed,
            extra={"cafename": item.get("cafename"),
                   "cafeurl": item.get("cafeurl")}))
    return out


async def collect_questions(user_settings: Any, seeds: List[str], source: str,
                            limit_per_seed: int = PER_SEED_LIMIT,
                            ) -> List[CommunityQuestion]:
    """시드 목록에서 질문을 모은다(2단계 상황 추출의 입력)."""
    out: List[CommunityQuestion] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for seed in seeds:
            out.extend(await fetch(user_settings, seed, source,
                                   limit_per_seed, client))
            await asyncio.sleep(CALL_DELAY)
    logger.info("[COMMUNITY] %s | 시드 %d개 → 질문 %d개",
                source, len(seeds), len(out))
    return out


async def collect(user_settings: Any, seeds: List[str], source: str,
                  limit_per_seed: int = PER_SEED_LIMIT) -> List[KeywordIdea]:
    """레지스트리용 — 다른 소스와 같은 모양으로 돌려준다.

    원문 질문은 `extra` 에 남긴다. 검색량은 붙지 않는다(질문은 쿼리가
    아니라 문장이라 검색광고 조회 대상이 아니다).
    """
    questions = await collect_questions(user_settings, seeds, source,
                                        limit_per_seed)
    out: List[KeywordIdea] = []
    seen: set = set()
    for q in questions:
        phrase = to_phrase(q.title, q.seed)
        if not phrase or phrase.lower() in seen:
            continue
        seen.add(phrase.lower())
        out.append(KeywordIdea(
            keyword=phrase, source=source, engine="naver", seed=q.seed,
            extra={"question": q.title, "link": q.link,
                   "description": q.description,
                   "has_situation": has_situation(q.text)}))
    logger.info("[COMMUNITY] %s | 질문 %d개 → 구절 %d개",
                source, len(questions), len(out))
    return out
