"""
구글 뉴스 RSS 수집 서비스

구글 뉴스 RSS 피드를 사용하여 뉴스 제목을 수집합니다.
API 키 없이 무료로 사용 가능합니다.

RSS URL 형식:
- 토픽별: https://news.google.com/rss/topics/{topic_id}?hl=ko&gl=KR&ceid=KR:ko
- 검색: https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko

Features:
- 토픽별 뉴스 제목 수집
- 키워드 검색 기반 수집
- API 키 불필요 (완전 무료)
- 수량 제한 적용
"""
import asyncio
import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


# 구글 뉴스 토픽 ID (한국어)
GOOGLE_NEWS_TOPICS = {
    "headlines": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtdHZHZ0pMVWlnQVAB",  # 헤드라인
    "nation": "CAAqIggKIhxDQkFTRHdvSkwyMHZNRGxqTjNjd0VnSnJieWdBUAE",  # 국내
    "world": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtdHZHZ0pMVWlnQVAB",  # 세계
    "business": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtdHZHZ0pMVWlnQVAB",  # 비즈니스
    "technology": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtdHZHZ0pMVWlnQVAB",  # 기술
    "entertainment": "CAAqJggKIiBDQkFTRWdvSUwyMHZNREpxYW5RU0FtdHZHZ0pMVWlnQVAB",  # 엔터테인먼트
    "sports": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtdHZHZ0pMVWlnQVAB",  # 스포츠
    "science": "CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp0Y1RjU0FtdHZHZ0pMVWlnQVAB",  # 과학
    "health": "CAAqIQgKIhtDQkFTRGdvSUwyMHZNR3QwTlRFU0FtdHZLQUFQAQ",  # 건강
}

# 검색용 카테고리 키워드 (정보성 블로그에 적합)
SEARCH_CATEGORIES = {
    "finance": ["재테크", "주식 투자", "부동산 전망"],
    "health": ["건강 관리", "다이어트 방법", "운동 효과"],
    "tech": ["AI 기술", "스마트폰 리뷰", "IT 트렌드"],
    "lifestyle": ["생활 꿀팁", "인테리어", "자기계발"],
    "travel": ["국내 여행", "맛집 추천", "여행 팁"],
}


class GoogleNewsRssService:
    """구글 뉴스 RSS 수집 서비스"""

    BASE_URL = "https://news.google.com/rss"

    # 재시도 설정
    MAX_RETRIES = 3
    BASE_DELAY = 2.0

    def __init__(self):
        """API 키 불필요"""
        pass

    def is_configured(self) -> bool:
        """항상 사용 가능 (API 키 불필요)"""
        return True

    def _get_headers(self) -> Dict[str, str]:
        """요청 헤더"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

    async def fetch_rss(self, url: str) -> Dict[str, Any]:
        """
        RSS 피드 가져오기

        Args:
            url: RSS URL

        Returns:
            파싱된 RSS 아이템 목록
        """
        headers = self._get_headers()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 429:
                        if attempt < self.MAX_RETRIES:
                            delay = self.BASE_DELAY * (2 ** attempt)
                            logger.warning(
                                f"[GOOGLE_NEWS_RSS] Rate Limit - {delay:.1f}초 후 재시도"
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
                            f"[GOOGLE_NEWS_RSS] HTTP 오류: {response.status_code}"
                        )
                        return {
                            "success": False,
                            "error": f"HTTP {response.status_code}",
                            "items": []
                        }

                    # XML 파싱
                    items = self._parse_rss(response.text)

                    return {
                        "success": True,
                        "items": items
                    }

            except httpx.TimeoutException:
                logger.warning(f"[GOOGLE_NEWS_RSS] 타임아웃 (시도 {attempt + 1})")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BASE_DELAY)
                    continue
                return {
                    "success": False,
                    "error": "요청 타임아웃",
                    "items": []
                }

            except Exception as e:
                logger.error(f"[GOOGLE_NEWS_RSS] 요청 예외: {e}")
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

    def _parse_rss(self, xml_content: str) -> List[Dict[str, str]]:
        """RSS XML 파싱"""
        items = []

        try:
            root = ET.fromstring(xml_content)
            channel = root.find("channel")

            if channel is None:
                return items

            for item in channel.findall("item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                pub_date_elem = item.find("pubDate")
                source_elem = item.find("source")

                if title_elem is not None and title_elem.text:
                    title = self._clean_title(title_elem.text)
                    # 띄어쓰기 포함 10자 이하 제목은 수집하지 않음
                    if title and len(title) > 10:
                        items.append({
                            "title": title,
                            "link": link_elem.text if link_elem is not None else "",
                            "pub_date": pub_date_elem.text if pub_date_elem is not None else "",
                            "source_name": source_elem.text if source_elem is not None else ""
                        })

        except ET.ParseError as e:
            logger.error(f"[GOOGLE_NEWS_RSS] XML 파싱 오류: {e}")

        return items

    def _clean_title(self, title: str) -> str:
        """제목 정리"""
        # 언론사 표시 제거 (예: "제목 - 조선일보")
        title = re.sub(r'\s*[-–—]\s*[^-–—]+$', '', title)
        # 연속 공백 제거
        title = re.sub(r'\s+', ' ', title)
        return title.strip()

    async def collect_from_topics(
        self,
        topics: Optional[List[str]] = None,
        limit: int = 100,
        delay_between_topics: float = 1.0,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        토픽별 뉴스 제목 수집

        Args:
            topics: 수집할 토픽 목록 (None이면 전체 토픽)
            limit: 최대 수집 제목 수
            delay_between_topics: 토픽 간 딜레이 (초)
            use_random: True면 랜덤 토픽에서 20개씩 수집

        Returns:
            수집된 제목 목록
        """
        if topics is None:
            # 전체 토픽 사용
            topics = list(GOOGLE_NEWS_TOPICS.keys())

        # 랜덤 모드: 토픽 랜덤 선택 후 20개씩 수집 반복
        if use_random:
            return await self._collect_random_from_topics(
                topics, limit, delay_between_topics
            )

        logger.info(
            f"[GOOGLE_NEWS_RSS] 토픽별 수집 시작 "
            f"(토픽 {len(topics)}개, limit={limit})"
        )

        all_titles = []
        collected_count = 0

        for topic in topics:
            if collected_count >= limit:
                break

            topic_id = GOOGLE_NEWS_TOPICS.get(topic)
            if not topic_id:
                logger.warning(f"[GOOGLE_NEWS_RSS] 알 수 없는 토픽: {topic}")
                continue

            url = f"{self.BASE_URL}/topics/{topic_id}?hl=ko&gl=KR&ceid=KR:ko"
            result = await self.fetch_rss(url)

            if not result.get("success"):
                logger.warning(
                    f"[GOOGLE_NEWS_RSS] '{topic}' 수집 실패: {result.get('error')}"
                )
                continue

            items = result.get("items", [])

            for item in items:
                if collected_count >= limit:
                    break

                all_titles.append({
                    "title": item["title"],
                    "source": "google_news_rss",
                    "category": topic,
                    "link": item.get("link", ""),
                    "pub_date": item.get("pub_date", ""),
                    "source_name": item.get("source_name", "")
                })
                collected_count += 1

            logger.info(
                f"[GOOGLE_NEWS_RSS] '{topic}' 토픽: {len(items)}개 수집"
            )

            # 토픽 간 딜레이
            if collected_count < limit:
                await asyncio.sleep(delay_between_topics)

        logger.info(
            f"[GOOGLE_NEWS_RSS] 토픽별 수집 완료: {collected_count}개"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def _collect_random_from_topics(
        self,
        topics: List[str],
        limit: int,
        delay_between_topics: float
    ) -> Dict[str, Any]:
        """
        랜덤 토픽에서 20개씩 수집 (키워드 탭 데이터 없을 때 사용)

        수집 방식:
        1. 토픽 랜덤 선택
        2. 해당 토픽 RSS에서 전체 가져오기
        3. 랜덤 20개 수집
        4. limit 충족까지 반복
        """
        logger.info(
            f"[GOOGLE_NEWS_RSS] 랜덤 수집 시작 "
            f"(토픽 {len(topics)}개, limit={limit}, 20개씩)"
        )

        all_titles = []
        collected_count = 0
        used_topics = set()
        max_attempts = limit * 2
        attempts = 0

        while collected_count < limit and attempts < max_attempts:
            attempts += 1

            # 1. 토픽 랜덤 선택 (사용하지 않은 것 우선)
            available_topics = [t for t in topics if t not in used_topics]
            if not available_topics:
                # 모든 토픽 사용했으면 전체에서 랜덤
                available_topics = topics

            topic = random.choice(available_topics)
            used_topics.add(topic)

            topic_id = GOOGLE_NEWS_TOPICS.get(topic)
            if not topic_id:
                continue

            # 2. RSS 가져오기
            url = f"{self.BASE_URL}/topics/{topic_id}?hl=ko&gl=KR&ceid=KR:ko"
            result = await self.fetch_rss(url)

            if not result.get("success"):
                logger.warning(
                    f"[GOOGLE_NEWS_RSS] 랜덤 수집 '{topic}' 실패"
                )
                continue

            items = result.get("items", [])
            if not items:
                continue

            # 3. 랜덤하게 20개 선택
            sample_size = min(20, len(items), limit - collected_count)
            selected_items = random.sample(items, sample_size)

            for item in selected_items:
                all_titles.append({
                    "title": item["title"],
                    "source": "google_news_rss",
                    "category": topic,
                    "link": item.get("link", ""),
                    "pub_date": item.get("pub_date", ""),
                    "source_name": item.get("source_name", "")
                })
                collected_count += 1

                if collected_count >= limit:
                    break

            logger.debug(
                f"[GOOGLE_NEWS_RSS] 랜덤 수집 '{topic}': {sample_size}개 추가 "
                f"(총 {collected_count}/{limit})"
            )

            # 토픽 간 딜레이
            await asyncio.sleep(delay_between_topics)

        logger.info(
            f"[GOOGLE_NEWS_RSS] 랜덤 수집 완료: {collected_count}개 "
            f"(시도 {attempts}회)"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def collect_from_search(
        self,
        categories: Optional[List[str]] = None,
        limit: int = 100,
        delay_between_queries: float = 1.5,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        검색 기반 뉴스 제목 수집

        Args:
            categories: 검색 카테고리 목록 (None이면 전체)
            limit: 최대 수집 제목 수
            delay_between_queries: 쿼리 간 딜레이 (초)
            use_random: True면 랜덤 카테고리에서 20개씩 수집

        Returns:
            수집된 제목 목록
        """
        if categories is None:
            categories = list(SEARCH_CATEGORIES.keys())

        # 랜덤 모드: 카테고리 랜덤 선택 후 20개씩 수집 반복
        if use_random:
            return await self._collect_random_from_search(
                categories, limit, delay_between_queries
            )

        logger.info(
            f"[GOOGLE_NEWS_RSS] 검색 기반 수집 시작 "
            f"(카테고리 {len(categories)}개, limit={limit})"
        )

        all_titles = []
        collected_count = 0

        for cat_key in categories:
            if collected_count >= limit:
                break

            keywords = SEARCH_CATEGORIES.get(cat_key, [cat_key])

            for keyword in keywords:
                if collected_count >= limit:
                    break

                encoded_query = quote(keyword)
                url = f"{self.BASE_URL}/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
                result = await self.fetch_rss(url)

                if not result.get("success"):
                    logger.warning(
                        f"[GOOGLE_NEWS_RSS] '{keyword}' 검색 실패: {result.get('error')}"
                    )
                    continue

                items = result.get("items", [])

                for item in items:
                    if collected_count >= limit:
                        break

                    all_titles.append({
                        "title": item["title"],
                        "source": "google_news_rss",
                        "category": cat_key,
                        "keyword": keyword,
                        "link": item.get("link", ""),
                        "pub_date": item.get("pub_date", ""),
                        "source_name": item.get("source_name", "")
                    })
                    collected_count += 1

                # 쿼리 간 딜레이
                await asyncio.sleep(delay_between_queries)

        logger.info(
            f"[GOOGLE_NEWS_RSS] 검색 기반 수집 완료: {collected_count}개"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def _collect_random_from_search(
        self,
        categories: List[str],
        limit: int,
        delay_between_queries: float
    ) -> Dict[str, Any]:
        """
        랜덤 카테고리/키워드에서 20개씩 수집 (키워드 탭 데이터 없을 때 사용)

        수집 방식:
        1. 카테고리 랜덤 선택
        2. 해당 카테고리의 키워드 랜덤 선택
        3. 검색 결과에서 랜덤 20개 수집
        4. limit 충족까지 반복
        """
        logger.info(
            f"[GOOGLE_NEWS_RSS] 검색 랜덤 수집 시작 "
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
            keywords = SEARCH_CATEGORIES.get(cat_key, [cat_key])

            # 2. 키워드 랜덤 선택 (사용하지 않은 것 우선)
            available_keywords = [kw for kw in keywords if kw not in used_keywords]
            if not available_keywords:
                available_keywords = keywords

            keyword = random.choice(available_keywords)
            used_keywords.add(keyword)

            # 3. RSS 검색
            encoded_query = quote(keyword)
            url = f"{self.BASE_URL}/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
            result = await self.fetch_rss(url)

            if not result.get("success"):
                logger.warning(
                    f"[GOOGLE_NEWS_RSS] 검색 랜덤 수집 '{keyword}' 실패"
                )
                continue

            items = result.get("items", [])
            if not items:
                continue

            # 4. 랜덤하게 20개 선택
            sample_size = min(20, len(items), limit - collected_count)
            selected_items = random.sample(items, sample_size)

            for item in selected_items:
                all_titles.append({
                    "title": item["title"],
                    "source": "google_news_rss",
                    "category": cat_key,
                    "keyword": keyword,
                    "link": item.get("link", ""),
                    "pub_date": item.get("pub_date", ""),
                    "source_name": item.get("source_name", "")
                })
                collected_count += 1

                if collected_count >= limit:
                    break

            logger.debug(
                f"[GOOGLE_NEWS_RSS] 검색 랜덤 수집 '{keyword}': {sample_size}개 추가 "
                f"(총 {collected_count}/{limit})"
            )

            # 쿼리 간 딜레이
            await asyncio.sleep(delay_between_queries)

        logger.info(
            f"[GOOGLE_NEWS_RSS] 검색 랜덤 수집 완료: {collected_count}개 "
            f"(시도 {attempts}회)"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def collect_news_titles(
        self,
        limit: int = 100,
        use_topics: bool = True,
        use_search: bool = True,
        delay_between_requests: float = 1.0,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        뉴스 제목 통합 수집 (토픽 + 검색)

        Args:
            limit: 최대 수집 제목 수
            use_topics: 토픽 기반 수집 여부
            use_search: 검색 기반 수집 여부
            delay_between_requests: 요청 간 딜레이 (초)
            use_random: True면 랜덤 수집 모드

        Returns:
            수집된 제목 목록
        """
        all_titles = []
        collected_count = 0
        remaining = limit

        if use_topics and remaining > 0:
            topic_limit = remaining // 2 if use_search else remaining
            result = await self.collect_from_topics(
                limit=topic_limit,
                delay_between_topics=delay_between_requests,
                use_random=use_random
            )
            if result.get("success"):
                all_titles.extend(result.get("titles", []))
                collected_count += result.get("total_count", 0)
                remaining = limit - collected_count

        if use_search and remaining > 0:
            result = await self.collect_from_search(
                limit=remaining,
                delay_between_queries=delay_between_requests,
                use_random=use_random
            )
            if result.get("success"):
                all_titles.extend(result.get("titles", []))
                collected_count += result.get("total_count", 0)

        logger.info(
            f"[GOOGLE_NEWS_RSS] 통합 수집 완료: {collected_count}개"
        )

        return {
            "success": True,
            "titles": all_titles,
            "total_count": collected_count
        }

    async def test_connection(self) -> Dict[str, Any]:
        """연결 테스트"""
        try:
            # 헤드라인 토픽으로 테스트
            topic_id = GOOGLE_NEWS_TOPICS["headlines"]
            url = f"{self.BASE_URL}/topics/{topic_id}?hl=ko&gl=KR&ceid=KR:ko"
            result = await self.fetch_rss(url)

            if result.get("success") and result.get("items"):
                return {
                    "success": True,
                    "message": f"구글 뉴스 RSS 연결 성공 ({len(result['items'])}개 항목 확인)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "항목을 가져오지 못했습니다")
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
