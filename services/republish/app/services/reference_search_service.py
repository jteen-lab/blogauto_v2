"""
참조자료 검색 서비스

네이버 검색 API로 참조자료를 찾는다. **소스가 여러 개다.**

왜 웹문서 하나로는 부족한가: 법 근거가 필요한 글(원상회복·통상손모),
제도가 바뀐 글(공제 한도), 실제 겪은 사람 이야기가 필요한 글은 각각
찾아야 할 곳이 다르다. 웹문서 하나로 전부 덮으면 근거의 급이 떨어진다.

    law  → 법령·판례를 다루는 전문자료
    news → 시의성 확인
    kin  → 실제 사례·경험
    web  → 일반 설명

같은 자격증명으로 엔드포인트만 바꾸면 열린다.

참조자료 수집에 최적화: URL 목록 반환, 재시도 1회, 에러 시 빈 리스트 반환
계획서: docs/plans/topic_discovery_and_structure_plan.md §12
"""
import asyncio
import logging
import re
from email.utils import parsedate_to_datetime
from typing import List, Optional

import httpx

from ..models.user_settings import UserSettings
from ..schemas.reference_collection import SearchResult

logger = logging.getLogger(__name__)


class ReferenceSearchService:
    """참조자료 검색 서비스 (네이버 웹문서 API)"""

    API_URL = "https://openapi.naver.com/v1/search/webkr.json"
    TIMEOUT = 10
    MAX_RETRIES = 1

    # 체크리스트 항목의 `source` 값 → 네이버 엔드포인트.
    # `doc`(전문자료)가 법령·논문 쪽 문서를 물어온다. 국가법령정보센터는
    # 공개 검색 API 가 없어 여기로 대신한다.
    BASE = "https://openapi.naver.com/v1/search"
    ENDPOINTS = {
        "web": f"{BASE}/webkr.json",
        "news": f"{BASE}/news.json",
        "kin": f"{BASE}/kin.json",
        "cafe": f"{BASE}/cafearticle.json",
        "encyc": f"{BASE}/encyc.json",
        "law": f"{BASE}/doc.json",
    }

    # 소스별 기본 정렬. 시의성이 중요한 곳만 날짜순으로 본다.
    SORT = {"news": "date", "kin": "sim", "cafe": "date",
            "web": "sim", "encyc": "sim", "law": "sim"}

    def __init__(self, settings: UserSettings):
        self._settings = settings

    @property
    def client_id(self) -> Optional[str]:
        return getattr(self._settings, 'naver_search_client_id', None)

    @property
    def client_secret(self) -> Optional[str]:
        return getattr(self._settings, 'naver_search_client_secret', None)

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.client_id and self.client_secret)

    def _get_headers(self) -> dict:
        return {
            "X-Naver-Client-Id": self.client_id or "",
            "X-Naver-Client-Secret": self.client_secret or "",
        }

    async def search_webdoc(self, query: str, count: int = 30) -> List[SearchResult]:
        """
        네이버 웹문서 검색 API 호출

        Args:
            query: 검색어
            count: 결과 개수 (기본 30, 최대 100)

        Returns:
            SearchResult 리스트 (에러 시 빈 리스트)
        """
        return await self.search("web", query, count)

    async def search(self, source: str, query: str,
                     count: int = 30) -> List[SearchResult]:
        """소스를 지정해 검색한다.

        Args:
            source: web | news | kin | cafe | encyc | law
            query: 검색어
            count: 결과 개수 (최대 100)

        Returns:
            SearchResult 리스트 (모르는 소스·에러 시 빈 리스트)
        """
        endpoint = self.ENDPOINTS.get(source)
        if endpoint is None:
            logger.warning(f"[REF_SEARCH] 모르는 소스: {source}")
            return []

        # 법 근거는 원문에서 가져온다. 인증값이 없거나 조회가 비면
        # 아래 네이버 전문자료로 돌아간다 — 글이 막히지 않아야 한다.
        if source == "law":
            found = await self._search_law(query, count)
            if found:
                return found

        if not query or len(query.strip()) < 2:
            logger.warning("[REF_SEARCH] 검색어가 너무 짧습니다")
            return []

        # 일반 자료는 네이버와 Brave 를 함께 쓴다. 네이버가 한국 로컬을,
        # Brave 가 그 밖을 가져온다 — 어느 한쪽만으로는 덜 찬다.
        extra: List[SearchResult] = []
        if source == "web":
            extra = await self._search_brave(query, count)

        rows: List[SearchResult] = []
        if self.is_configured():
            logger.info(f"[REF_SEARCH] {source} 검색: '{query}' (count={count})")
            params = {"query": query.strip(), "display": min(count, 100),
                      "start": 1, "sort": self.SORT.get(source, "sim")}
            response_data = await self._call_api(endpoint, params)
            if response_data:
                rows = self._parse_response(response_data)
        elif not extra:
            logger.error("[REF_SEARCH] API 키가 설정되지 않았습니다")
            return []

        return _merge(rows, extra)

    async def search_many(self, plan: List[tuple],
                          count: int = 20) -> dict:
        """여러 (소스, 질의) 쌍을 **동시에** 던진다.

        체크리스트 항목마다 찾아야 할 곳이 다르므로 한 번에 보낸다.
        하나가 실패해도 나머지는 쓴다.

        Args:
            plan: [(source, query), ...]
            count: 쌍당 결과 개수

        Returns:
            {(source, query): [SearchResult, ...]}
        """
        if not plan:
            return {}
        tasks = [self.search(src, q, count) for src, q in plan]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        out = {}
        for (src, q), result in zip(plan, done):
            if isinstance(result, Exception):
                logger.warning(f"[REF_SEARCH] {src}/{q} 실패: {result}")
                out[(src, q)] = []
            else:
                out[(src, q)] = result
        return out

    async def _search_brave(self, query: str,
                            count: int = 20) -> List[SearchResult]:
        """Brave 에서 찾는다. 키가 없으면 빈 목록."""
        key = getattr(self._settings, "brave_api_key", None)
        if not key:
            return []
        try:
            from .reference.brave_search import collect

            return await collect(key, query, count)
        except Exception as e:  # noqa: BLE001
            logger.warning("[REF_SEARCH] Brave 조회 실패 | %s", e)
            return []

    async def _search_law(self, query: str,
                          count: int = 30) -> List[SearchResult]:
        """법제처에서 판례와 법령을 함께 찾는다.

        판례가 법리를, 법령이 조문을 준다. 어느 쪽이 필요한지 미리
        알 수 없어 둘 다 던지고 나온 것을 합친다.
        """
        oc = getattr(self._settings, "law_api_oc", None)
        if not oc or not (query or "").strip():
            return []
        try:
            from .reference.law_api import (
                TARGET_LAW, TARGET_PREC, collect,
            )

            half = max(3, count // 2)
            got = await asyncio.gather(
                collect(oc, query, TARGET_PREC, half),
                collect(oc, query, TARGET_LAW, half),
                return_exceptions=True)
            out: List[SearchResult] = []
            for item in got:
                if isinstance(item, list):
                    out.extend(item)
            if out:
                logger.info("[REF_SEARCH] 법제처 '%s' | %d건", query, len(out))
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("[REF_SEARCH] 법제처 조회 실패 | %s", e)
            return []

    async def _call_api(self, endpoint: str, params: dict) -> Optional[dict]:
        """API 호출 (재시도 포함)"""
        headers = self._get_headers()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    response = await client.get(endpoint, headers=headers, params=params)

                    if response.status_code == 200:
                        return response.json()

                    if response.status_code == 429 and attempt < self.MAX_RETRIES:
                        logger.warning("[REF_SEARCH] Rate Limit - 1초 후 재시도")
                        await asyncio.sleep(1)
                        continue

                    logger.error(f"[REF_SEARCH] API 오류: HTTP {response.status_code}")
                    return None

            except httpx.TimeoutException:
                logger.warning(f"[REF_SEARCH] 타임아웃 (시도 {attempt + 1})")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue
                return None
            except Exception as e:
                logger.error(f"[REF_SEARCH] 예외 발생: {e}")
                return None

        return None

    @staticmethod
    def _read_postdate(item: dict) -> Optional[str]:
        """발행일을 YYYYMMDD 로. 못 읽으면 None.

        소스마다 칸 이름이 다르다. 뉴스는 `pubDate`(RFC 822)를 주고,
        블로그는 `postdate`(YYYYMMDD)를 준다. 웹문서·지식iN·백과는 날짜를
        아예 주지 않는다. `postdate` 만 읽던 탓에 **뉴스 날짜까지 버려져**
        모든 자료가 "발행일 없음" 이 됐고, 근거 판정이 최신 자료를 한 건도
        못 세어 YMYL 글이 전부 보류됐다(2026-09-24 확인).
        """
        raw = (item.get("postdate") or "").strip()
        if len(raw) == 8 and raw.isdigit():
            return raw
        pub = (item.get("pubDate") or "").strip()
        if pub:
            try:
                return parsedate_to_datetime(pub).strftime("%Y%m%d")
            except (TypeError, ValueError):
                logger.debug(f"[REF_SEARCH] 날짜를 못 읽음: {pub!r}")
        return None

    def _parse_response(self, response: dict) -> List[SearchResult]:
        """응답 파싱하여 SearchResult 리스트 반환"""
        items = response.get("items", [])
        results = []

        for item in items:
            try:
                results.append(SearchResult(
                    title=self._clean_html(item.get("title", "")),
                    link=item.get("link", ""),
                    description=self._clean_html(item.get("description", "")),
                    bloggername=item.get("bloggername"),
                    bloggerlink=item.get("bloggerlink"),
                    postdate=self._read_postdate(item)
                ))
            except Exception as e:
                logger.warning(f"[REF_SEARCH] 결과 파싱 실패: {e}")

        logger.info(f"[REF_SEARCH] 검색 결과: {len(results)}건")
        return results

    def _clean_html(self, text: str) -> str:
        """HTML 태그 및 엔티티 정리"""
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        for entity, char in [("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                             ("&gt;", ">"), ("&apos;", "'"), ("&nbsp;", " ")]:
            text = text.replace(entity, char)
        return re.sub(r'\s+', ' ', text).strip()

    async def test_connection(self) -> dict:
        """API 연결 테스트"""
        if not self.is_configured():
            return {"success": False, "error": "API 키가 설정되지 않았습니다"}

        try:
            results = await self.search_webdoc("테스트", count=1)
            if results:
                return {"success": True, "message": "네이버 웹문서 API 연결 성공"}
            return {"success": False, "error": "검색 결과가 없습니다"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def _merge(*groups: List[SearchResult]) -> List[SearchResult]:
    """여러 곳의 결과를 합친다. 같은 주소는 하나만 남긴다.

    앞에 온 묶음이 이긴다 — 먼저 넣은 쪽의 설명이 대개 더 길다.
    """
    seen = set()
    out: List[SearchResult] = []
    for group in groups:
        for row in group or []:
            key = (row.link or "").rstrip("/")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out
