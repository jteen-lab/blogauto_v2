"""
네이버 검색 API 서비스

네이버 블로그 검색 결과를 조회하여 제목을 수집합니다.
API 문서: https://developers.naver.com/docs/serviceapi/search/blog/blog.md
"""
import httpx
from typing import Optional, List, Dict, Any
from ..models.user_settings import UserSettings


class NaverSearchService:
    """네이버 검색 API 서비스"""

    BASE_URL = "https://openapi.naver.com/v1/search/blog.json"

    def __init__(self, settings: UserSettings):
        """
        Args:
            settings: 사용자 설정 (API 키 포함)
        """
        self.settings = settings
        self.client_id = settings.naver_search_client_id
        self.client_secret = settings.naver_search_client_secret

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.client_id and self.client_secret)

    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        return {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        API 연결 테스트

        Returns:
            성공 여부와 메시지
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    headers=self._get_headers(),
                    params={
                        "query": "테스트",
                        "display": 1
                    }
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "연결 성공"
                    }
                else:
                    error_data = response.json()
                    return {
                        "success": False,
                        "error": error_data.get("errorMessage", f"HTTP {response.status_code}")
                    }

        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "연결 시간 초과"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def search_blog(
        self,
        query: str,
        display: int = 10,
        start: int = 1,
        sort: str = "sim"
    ) -> Dict[str, Any]:
        """
        블로그 검색

        Args:
            query: 검색어
            display: 검색 결과 개수 (1~100, 기본값 10)
            start: 검색 시작 위치 (1~1000, 기본값 1)
            sort: 정렬 옵션 (sim: 정확도순, date: 날짜순)

        Returns:
            검색 결과
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    headers=self._get_headers(),
                    params={
                        "query": query,
                        "display": min(display, 100),
                        "start": min(start, 1000),
                        "sort": sort
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "total": data.get("total", 0),
                        "start": data.get("start", 1),
                        "display": data.get("display", 0),
                        "items": data.get("items", [])
                    }
                else:
                    error_data = response.json()
                    return {
                        "success": False,
                        "error": error_data.get("errorMessage", f"HTTP {response.status_code}")
                    }

        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "연결 시간 초과"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def collect_titles_by_keyword(
        self,
        keyword: str,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        키워드로 블로그 제목 수집

        Args:
            keyword: 검색 키워드
            max_results: 최대 수집 개수 (최대 1000)

        Returns:
            수집된 제목 목록
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "API 키가 설정되지 않았습니다"
            }

        titles = []
        start = 1
        display = min(100, max_results)

        try:
            while len(titles) < max_results and start <= 1000:
                result = await self.search_blog(
                    query=keyword,
                    display=display,
                    start=start,
                    sort="date"
                )

                if not result.get("success"):
                    break

                items = result.get("items", [])
                if not items:
                    break

                for item in items:
                    # HTML 태그 제거
                    title = item.get("title", "")
                    title = title.replace("<b>", "").replace("</b>", "")

                    titles.append({
                        "title": title,
                        "link": item.get("link", ""),
                        "blogger_name": item.get("bloggername", ""),
                        "blogger_link": item.get("bloggerlink", ""),
                        "post_date": item.get("postdate", ""),
                        "description": item.get("description", "").replace("<b>", "").replace("</b>", "")
                    })

                start += display

                # API 호출 제한 방지
                if start <= 1000 and len(titles) < max_results:
                    import asyncio
                    await asyncio.sleep(0.1)

            return {
                "success": True,
                "keyword": keyword,
                "count": len(titles),
                "titles": titles[:max_results]
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
