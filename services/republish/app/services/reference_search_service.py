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
import re
import logging
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

        if not self.is_configured():
            logger.error("[REF_SEARCH] API 키가 설정되지 않았습니다")
            return []

        if not query or len(query.strip()) < 2:
            logger.warning("[REF_SEARCH] 검색어가 너무 짧습니다")
            return []

        logger.info(f"[REF_SEARCH] {source} 검색: '{query}' (count={count})")
        params = {"query": query.strip(), "display": min(count, 100),
                  "start": 1, "sort": self.SORT.get(source, "sim")}
        response_data = await self._call_api(endpoint, params)

        return self._parse_response(response_data) if response_data else []

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
                    postdate=item.get("postdate")
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
