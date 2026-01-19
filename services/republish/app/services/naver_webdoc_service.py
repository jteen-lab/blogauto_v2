"""
네이버 웹문서 검색 API 서비스

네이버 검색 API를 사용하여 웹문서 제목을 수집합니다.
수집된 웹문서 제목은 임시제목 테이블에 저장됩니다.

API 문서: https://developers.naver.com/docs/serviceapi/search/web/web.md
일일 한도: 25,000건 (무료)

Features:
- 카테고리별 웹문서 제목 수집
- 수량 제한 적용
- Rate Limit 대응 (지수 백오프)
"""
import asyncio
import logging
import random
import re
from typing import List, Dict, Any, Optional

import httpx

from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)


# 웹문서 검색용 카테고리 키워드 (정보성 블로그에 적합)
WEBDOC_CATEGORIES = {
    "lifestyle": ["꿀팁", "생활정보", "노하우", "방법", "가이드"],
    "health": ["건강정보", "운동방법", "다이어트", "영양제", "건강관리"],
    "beauty": ["뷰티팁", "화장법", "스킨케어", "헤어관리", "메이크업"],
    "finance": ["재테크", "절약방법", "투자정보", "저축방법", "경제상식"],
    "food": ["맛집추천", "레시피", "요리방법", "음식정보", "식당추천"],
    "travel": ["여행정보", "여행팁", "국내여행", "해외여행", "관광지"],
    "tech": ["IT정보", "앱추천", "가전제품", "스마트폰", "컴퓨터"],
    "parenting": ["육아정보", "육아팁", "아이교육", "임신출산", "유아용품"],
}


class NaverWebdocService:
    """네이버 웹문서 검색 API 서비스"""

    API_URL = "https://openapi.naver.com/v1/search/webkr.json"

    # 재시도 설정
    MAX_RETRIES = 3
    BASE_DELAY = 1.0
    MAX_RETRY_DELAY = 10.0

    def __init__(self, settings: UserSettings):
        """
        Args:
            settings: UserSettings 객체 (naver_client_id, naver_client_secret 필요)
        """
        self._settings = settings

    @property
    def settings(self) -> UserSettings:
        return self._settings

    def is_configured(self) -> bool:
        """API 사용 가능 여부 확인"""
        return bool(
            self._settings and
            self._settings.naver_search_client_id and
            self._settings.naver_search_client_secret
        )

    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        return {
            "X-Naver-Client-Id": self._settings.naver_search_client_id,
            "X-Naver-Client-Secret": self._settings.naver_search_client_secret,
        }

    async def search_webdoc(
        self,
        query: str,
        display: int = 100,
        start: int = 1
    ) -> Dict[str, Any]:
        """
        웹문서 검색 API 호출

        Args:
            query: 검색어
            display: 한 번에 가져올 결과 수 (최대 100)
            start: 검색 시작 위치 (1~1000)

        Returns:
            검색 결과 (items 배열 포함)
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "네이버 API 키가 설정되지 않았습니다",
                "items": []
            }

        params = {
            "query": query,
            "display": min(display, 100),
            "start": start
        }

        headers = self._get_headers()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        self.API_URL,
                        headers=headers,
                        params=params
                    )

                    if response.status_code == 429:
                        if attempt < self.MAX_RETRIES:
                            delay = min(
                                self.BASE_DELAY * (2 ** attempt),
                                self.MAX_RETRY_DELAY
                            )
                            logger.warning(
                                f"[NAVER_WEBDOC] Rate Limit - {delay:.1f}초 후 재시도 "
                                f"({attempt + 1}/{self.MAX_RETRIES})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        return {
                            "success": False,
                            "error": "Rate Limit 초과",
                            "items": []
                        }

                    if response.status_code != 200:
                        logger.warning(
                            f"[NAVER_WEBDOC] API 오류: {response.status_code}"
                        )
                        return {
                            "success": False,
                            "error": f"API 오류: {response.status_code}",
                            "items": []
                        }

                    data = response.json()
                    items = data.get("items", [])

                    return {
                        "success": True,
                        "total": data.get("total", 0),
                        "items": items
                    }

            except httpx.TimeoutException:
                logger.warning(f"[NAVER_WEBDOC] 타임아웃 (시도 {attempt + 1})")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BASE_DELAY)
                    continue
                return {
                    "success": False,
                    "error": "요청 타임아웃",
                    "items": []
                }

            except Exception as e:
                logger.error(f"[NAVER_WEBDOC] 검색 예외: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "items": []
                }

        return {
            "success": False,
            "error": "알 수 없는 오류",
            "items": []
        }

    async def collect_webdoc_titles(
        self,
        categories: Optional[List[str]] = None,
        limit: int = 100,
        delay_between_queries: float = 0.5,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        카테고리별 웹문서 제목 수집

        Args:
            categories: 수집할 카테고리 목록 (None이면 전체)
            limit: 최대 수집 제목 수
            delay_between_queries: 쿼리 간 딜레이 (초)
            use_random: True면 랜덤 카테고리에서 20개씩 수집

        Returns:
            수집된 제목 목록
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "네이버 API 키가 설정되지 않았습니다",
                "titles": [],
                "total_count": 0
            }

        if categories is None:
            categories = list(WEBDOC_CATEGORIES.keys())

        # 랜덤 모드: 카테고리 랜덤 선택 후 20개씩 수집 반복
        if use_random:
            return await self._collect_random_titles(
                categories, limit, delay_between_queries
            )

        logger.info(
            f"[NAVER_WEBDOC] 웹문서 제목 수집 시작 "
            f"(카테고리 {len(categories)}개, limit={limit})"
        )

        all_titles = []
        collected_count = 0

        for cat_key in categories:
            if collected_count >= limit:
                break

            keywords = WEBDOC_CATEGORIES.get(cat_key, [cat_key])

            for keyword in keywords:
                if collected_count >= limit:
                    break

                # 남은 수량만큼만 요청
                remaining = limit - collected_count
                display = min(100, remaining)

                result = await self.search_webdoc(
                    query=keyword,
                    display=display
                )

                if not result.get("success"):
                    logger.warning(
                        f"[NAVER_WEBDOC] '{keyword}' 검색 실패: {result.get('error')}"
                    )
                    continue

                items = result.get("items", [])

                for item in items:
                    if collected_count >= limit:
                        break

                    title = item.get("title", "")
                    # HTML 태그 제거
                    title = self._clean_title(title)

                    if title and len(title) >= 10:
                        all_titles.append({
                            "title": title,
                            "source": "naver_webdoc",
                            "category": cat_key,
                            "keyword": keyword,
                            "link": item.get("link", ""),
                            "description": self._clean_title(
                                item.get("description", "")
                            )[:100]
                        })
                        collected_count += 1

                # 쿼리 간 딜레이
                await asyncio.sleep(delay_between_queries)

        logger.info(
            f"[NAVER_WEBDOC] 웹문서 제목 수집 완료: {collected_count}개"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def _collect_random_titles(
        self,
        categories: List[str],
        limit: int,
        delay_between_queries: float
    ) -> Dict[str, Any]:
        """
        랜덤 카테고리에서 20개씩 수집 (키워드 탭 데이터 없을 때 사용)

        수집 방식:
        1. 카테고리 랜덤 선택
        2. 해당 카테고리의 키워드 랜덤 선택
        3. 첫 페이지에서 랜덤 20개 수집
        4. limit 충족까지 반복
        """
        logger.info(
            f"[NAVER_WEBDOC] 랜덤 수집 시작 "
            f"(카테고리 {len(categories)}개, limit={limit}, 20개씩)"
        )

        all_titles = []
        collected_count = 0
        used_keywords = set()
        max_attempts = limit * 2
        attempts = 0

        while collected_count < limit and attempts < max_attempts:
            attempts += 1

            # 1. 카테고리 랜덤 선택
            cat_key = random.choice(categories)
            keywords = WEBDOC_CATEGORIES.get(cat_key, [cat_key])

            # 2. 키워드 랜덤 선택 (사용하지 않은 것 우선)
            available_keywords = [kw for kw in keywords if kw not in used_keywords]
            if not available_keywords:
                available_keywords = keywords

            keyword = random.choice(available_keywords)
            used_keywords.add(keyword)

            # 3. 첫 페이지에서 100개 가져오기
            result = await self.search_webdoc(
                query=keyword,
                display=100
            )

            if not result.get("success"):
                logger.warning(
                    f"[NAVER_WEBDOC] 랜덤 수집 '{keyword}' 검색 실패"
                )
                continue

            items = result.get("items", [])
            if not items:
                continue

            # 4. 랜덤하게 20개 선택
            sample_size = min(20, len(items), limit - collected_count)
            selected_items = random.sample(items, sample_size)

            for item in selected_items:
                title = item.get("title", "")
                title = self._clean_title(title)

                if title and len(title) >= 10:
                    all_titles.append({
                        "title": title,
                        "source": "naver_webdoc",
                        "category": cat_key,
                        "keyword": keyword,
                        "link": item.get("link", ""),
                        "description": self._clean_title(
                            item.get("description", "")
                        )[:100]
                    })
                    collected_count += 1

                    if collected_count >= limit:
                        break

            logger.debug(
                f"[NAVER_WEBDOC] 랜덤 수집 '{keyword}': {sample_size}개 추가 "
                f"(총 {collected_count}/{limit})"
            )

            # 쿼리 간 딜레이
            await asyncio.sleep(delay_between_queries)

        logger.info(
            f"[NAVER_WEBDOC] 랜덤 수집 완료: {collected_count}개 "
            f"(시도 {attempts}회)"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    def _clean_title(self, title: str) -> str:
        """HTML 태그 및 특수문자 정리"""
        # HTML 태그 제거
        title = re.sub(r'<[^>]+>', '', title)
        # HTML 엔티티 변환
        title = title.replace("&quot;", '"')
        title = title.replace("&amp;", "&")
        title = title.replace("&lt;", "<")
        title = title.replace("&gt;", ">")
        title = title.replace("&apos;", "'")
        # 연속 공백 제거
        title = re.sub(r'\s+', ' ', title)
        return title.strip()

    async def search_by_keyword(
        self,
        keyword: str,
        limit: int = 50,
        delay_between_requests: float = 0.3
    ) -> Dict[str, Any]:
        """
        단일 키워드로 웹문서 제목 검색

        키워드 기반 제목 수집에서 사용됩니다.

        Args:
            keyword: 검색할 키워드
            limit: 최대 수집 제목 수
            delay_between_requests: 요청 간 딜레이 (초)

        Returns:
            {
                "success": bool,
                "titles": [{"title": str, "source": str, "keyword": str, ...}],
                "total_count": int,
                "error": str (실패 시)
            }
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "네이버 API 키가 설정되지 않았습니다",
                "titles": [],
                "total_count": 0
            }

        logger.info(f"[NAVER_WEBDOC] 키워드 검색 시작: '{keyword}' (limit={limit})")

        all_titles = []
        collected_count = 0
        start = 1

        # 네이버 API는 start가 최대 1000까지
        while collected_count < limit and start <= 1000:
            remaining = limit - collected_count
            display = min(100, remaining)

            result = await self.search_webdoc(
                query=keyword,
                display=display,
                start=start
            )

            if not result.get("success"):
                logger.warning(
                    f"[NAVER_WEBDOC] '{keyword}' 검색 실패: {result.get('error')}"
                )
                if collected_count > 0:
                    # 일부 수집 성공한 경우 결과 반환
                    break
                return {
                    "success": False,
                    "error": result.get("error", "검색 실패"),
                    "titles": [],
                    "total_count": 0
                }

            items = result.get("items", [])

            if not items:
                # 더 이상 결과가 없음
                break

            for item in items:
                if collected_count >= limit:
                    break

                title = item.get("title", "")
                title = self._clean_title(title)

                # 최소 길이 체크 (10자 이상)
                if title and len(title) >= 10:
                    all_titles.append({
                        "title": title,
                        "source": "naver_webdoc",
                        "keyword": keyword,
                        "link": item.get("link", ""),
                        "description": self._clean_title(
                            item.get("description", "")
                        )[:100]
                    })
                    collected_count += 1

            # 다음 페이지로
            start += display

            # Rate Limit 방지를 위한 딜레이
            if start <= 1000 and collected_count < limit:
                await asyncio.sleep(delay_between_requests)

        logger.info(
            f"[NAVER_WEBDOC] 키워드 '{keyword}' 검색 완료: {collected_count}개 수집"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count,
            "keyword": keyword
        }

    async def test_connection(self) -> Dict[str, Any]:
        """API 연결 테스트"""
        try:
            result = await self.search_webdoc(query="정보", display=1)

            if result.get("success"):
                return {
                    "success": True,
                    "message": f"네이버 웹문서 API 연결 성공 (총 {result.get('total', 0)}건)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "연결 실패")
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
