"""
참조자료 검색 서비스

네이버 웹문서 검색 API를 사용하여 참조자료를 검색합니다.
참조자료 수집에 최적화: URL 목록 반환, 재시도 1회, 에러 시 빈 리스트 반환
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
        if not self.is_configured():
            logger.error("[REF_SEARCH] API 키가 설정되지 않았습니다")
            return []

        if not query or len(query.strip()) < 2:
            logger.warning("[REF_SEARCH] 검색어가 너무 짧습니다")
            return []

        logger.info(f"[REF_SEARCH] 검색 시작: '{query}' (count={count})")
        params = {"query": query.strip(), "display": min(count, 100), "start": 1, "sort": "sim"}
        response_data = await self._call_api(self.API_URL, params)

        return self._parse_response(response_data) if response_data else []

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
