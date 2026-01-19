"""
네이버 쇼핑인사이트 인기검색어 수집 서비스

Features:
- 카테고리별 인기 검색어 TOP 500 수집 (getCategoryKeywordRank API)
- 분야별 트렌드 조회
- 페이지네이션 처리 (25페이지 x 20개 = 500개)
- 429 에러 대응: 지수 백오프 재시도

API Endpoints:
- 카테고리 조회: https://datalab.naver.com/shoppingInsight/getCategory.naver
- 인기검색어: https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver

Note:
- 이 API는 공식 Open API가 아닌 데이터랩 웹사이트 내부 API입니다.
- 과도한 요청 시 429 에러(Rate Limit) 발생 → 지수 백오프로 재시도
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import httpx

from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)


# 네이버 쇼핑 주요 카테고리 코드
# https://datalab.naver.com/shoppingInsight/sCategory.naver 에서 확인 가능
SHOPPING_CATEGORIES = {
    # 대분류 카테고리 (1차 카테고리)
    "50000000": "패션의류",
    "50000001": "패션잡화",
    "50000002": "화장품/미용",
    "50000003": "디지털/가전",
    "50000004": "가구/인테리어",
    "50000005": "출산/육아",
    "50000006": "식품",
    "50000007": "스포츠/레저",
    "50000008": "생활/건강",
    "50000009": "여가/생활편의",
    "50000010": "면세점",
    "50000011": "도서",
}


class NaverShoppingInsightService:
    """네이버 쇼핑인사이트 인기검색어 수집 서비스"""

    # 데이터랩 내부 API 엔드포인트
    DATALAB_BASE_URL = "https://datalab.naver.com/shoppingInsight"
    CATEGORY_API = f"{DATALAB_BASE_URL}/getCategory.naver"
    KEYWORD_RANK_API = f"{DATALAB_BASE_URL}/getCategoryKeywordRank.naver"

    # 페이지당 키워드 수 및 최대 페이지
    KEYWORDS_PER_PAGE = 20
    MAX_PAGES = 25  # 25페이지 x 20개 = 500개

    # 재시도 설정 (429 에러 대응)
    MAX_RETRIES = 3
    BASE_DELAY = 5.0  # 재시도 기본 딜레이 (초)
    MAX_RETRY_DELAY = 60.0  # 최대 재시도 딜레이 (초)

    def __init__(self, settings: UserSettings = None):
        """
        Args:
            settings: UserSettings 객체 (API 키 불필요, 웹 스크래핑 방식)
        """
        self._settings = settings

    @property
    def settings(self) -> Optional[UserSettings]:
        """사용자 설정"""
        return self._settings

    def is_configured(self) -> bool:
        """서비스 사용 가능 여부 (항상 True, API 키 불필요)"""
        return True

    def _get_headers(self) -> Dict[str, str]:
        """웹 요청 헤더 생성"""
        return {
            "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def get_category_keyword_rank(
        self,
        category_code: str,
        start_date: str = None,
        end_date: str = None,
        page: int = 1,
        age: str = "",
        gender: str = "",
        device: str = ""
    ) -> Dict[str, Any]:
        """
        카테고리별 인기검색어 랭킹 조회 (단일 페이지, 재시도 로직 포함)

        Args:
            category_code: 카테고리 ID (예: "50000000")
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            page: 페이지 번호 (1~25)
            age: 연령대 필터 (빈문자열=전체)
            gender: 성별 필터 (빈문자열=전체)
            device: 디바이스 필터 (빈문자열=전체)

        Returns:
            인기검색어 목록
        """
        # 기본 날짜 설정 (최근 7일)
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        # POST 요청 데이터
        form_data = {
            "cid": category_code,
            "timeUnit": "date",
            "startDate": start_date,
            "endDate": end_date,
            "page": str(page),
            "count": str(self.KEYWORDS_PER_PAGE),
            "age": age,
            "gender": gender,
            "device": device,
        }

        headers = self._get_headers()

        # 재시도 로직 (지수 백오프)
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.KEYWORD_RANK_API,
                        headers=headers,
                        data=form_data
                    )

                    # 429 에러 (Rate Limit) 처리
                    if response.status_code == 429:
                        if attempt < self.MAX_RETRIES:
                            # 지수 백오프: 5초 → 10초 → 20초 + 랜덤 지터
                            delay = min(
                                self.BASE_DELAY * (2 ** attempt) + random.uniform(1, 3),
                                self.MAX_RETRY_DELAY
                            )
                            logger.warning(
                                f"[SHOPPING_INSIGHT] 429 Rate Limit - "
                                f"{delay:.1f}초 후 재시도 ({attempt + 1}/{self.MAX_RETRIES})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(
                                f"[SHOPPING_INSIGHT] 429 Rate Limit - "
                                f"최대 재시도 횟수 초과"
                            )
                            return {
                                "success": False,
                                "error": "Rate Limit 초과 (429)",
                                "keywords": [],
                                "rate_limited": True
                            }

                    # 기타 에러
                    if response.status_code != 200:
                        logger.warning(
                            f"[SHOPPING_INSIGHT] API 오류: {response.status_code}"
                        )
                        return {
                            "success": False,
                            "error": f"API 오류: {response.status_code}",
                            "keywords": []
                        }

                    data = response.json()
                    keywords = []

                    # ranks 배열에서 키워드 추출
                    ranks = data.get("ranks", [])
                    for rank_data in ranks:
                        keyword = rank_data.get("keyword", "")
                        if keyword:
                            keywords.append({
                                "keyword": keyword,
                                "rank": rank_data.get("rank", 0),
                                "linkId": rank_data.get("linkId", ""),
                            })

                    return {
                        "success": True,
                        "page": page,
                        "keywords": keywords,
                        "total_count": len(keywords)
                    }

            except httpx.TimeoutException:
                logger.warning(f"[SHOPPING_INSIGHT] 타임아웃 (시도 {attempt + 1})")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BASE_DELAY)
                    continue
                return {
                    "success": False,
                    "error": "요청 타임아웃",
                    "keywords": []
                }

            except Exception as e:
                logger.error(f"[SHOPPING_INSIGHT] 인기검색어 조회 예외: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "keywords": []
                }

        return {
            "success": False,
            "error": "알 수 없는 오류",
            "keywords": []
        }

    async def collect_category_top_keywords(
        self,
        category_code: str,
        max_keywords: int = 500,
        start_date: str = None,
        end_date: str = None,
        delay_between_pages: float = 2.0
    ) -> Dict[str, Any]:
        """
        카테고리별 인기검색어 TOP N 수집 (페이지네이션 처리)

        Args:
            category_code: 카테고리 ID
            max_keywords: 최대 수집 키워드 수 (기본 500)
            start_date: 시작일
            end_date: 종료일
            delay_between_pages: 페이지 간 딜레이 (초, 기본 2초)

        Returns:
            수집된 키워드 목록
        """
        category_name = SHOPPING_CATEGORIES.get(
            category_code, f"카테고리_{category_code}"
        )
        logger.info(
            f"[SHOPPING_INSIGHT] '{category_name}' 인기검색어 수집 시작 "
            f"(최대 {max_keywords}개)"
        )

        all_keywords = []
        pages_needed = min(
            (max_keywords + self.KEYWORDS_PER_PAGE - 1) // self.KEYWORDS_PER_PAGE,
            self.MAX_PAGES
        )
        rate_limited = False

        for page in range(1, pages_needed + 1):
            result = await self.get_category_keyword_rank(
                category_code=category_code,
                start_date=start_date,
                end_date=end_date,
                page=page
            )

            if not result.get("success"):
                logger.warning(
                    f"[SHOPPING_INSIGHT] '{category_name}' 페이지 {page} 실패: "
                    f"{result.get('error')}"
                )
                # Rate Limit 초과 시 플래그 설정
                if result.get("rate_limited"):
                    rate_limited = True
                break

            keywords = result.get("keywords", [])
            if not keywords:
                # 더 이상 키워드가 없음
                break

            all_keywords.extend(keywords)

            # 최대 수 도달 시 중단
            if len(all_keywords) >= max_keywords:
                all_keywords = all_keywords[:max_keywords]
                break

            # 요청 간 딜레이 (2초 기본)
            if page < pages_needed:
                await asyncio.sleep(delay_between_pages)

        logger.info(
            f"[SHOPPING_INSIGHT] '{category_name}' 인기검색어 수집 완료: "
            f"{len(all_keywords)}개"
        )

        return {
            "success": len(all_keywords) > 0,
            "category": category_name,
            "category_code": category_code,
            "total_count": len(all_keywords),
            "keywords": all_keywords,
            "rate_limited": rate_limited
        }

    async def collect_all_categories_keywords(
        self,
        categories: List[str] = None,
        max_keywords_per_category: int = 100,
        delay_between_categories: float = 5.0
    ) -> Dict[str, Any]:
        """
        여러 카테고리에서 인기검색어 수집

        Args:
            categories: 수집할 카테고리 코드 목록 (None이면 대분류 전체)
            max_keywords_per_category: 카테고리당 최대 수집 키워드 수
            delay_between_categories: 카테고리 간 딜레이 (초, 기본 5초)

        Returns:
            수집된 전체 키워드 목록
        """
        if categories is None:
            # 대분류 카테고리만 사용
            categories = list(SHOPPING_CATEGORIES.keys())

        logger.info(
            f"[SHOPPING_INSIGHT] 전체 카테고리 인기검색어 수집 시작: "
            f"{len(categories)}개 카테고리"
        )

        all_keywords = []
        category_results = {}
        consecutive_rate_limits = 0
        max_consecutive_rate_limits = 3  # 연속 3번 Rate Limit 시 중단

        for i, cat_code in enumerate(categories):
            cat_name = SHOPPING_CATEGORIES.get(cat_code, f"카테고리_{cat_code}")

            result = await self.collect_category_top_keywords(
                category_code=cat_code,
                max_keywords=max_keywords_per_category
            )

            if result.get("success"):
                keywords = result.get("keywords", [])
                # 소스 정보 추가
                for kw in keywords:
                    kw["category_code"] = cat_code
                    kw["category_name"] = cat_name
                    kw["source"] = "naver_shopping_insight"

                all_keywords.extend(keywords)
                category_results[cat_code] = {
                    "name": cat_name,
                    "count": len(keywords)
                }
                # 성공 시 연속 Rate Limit 카운터 리셋
                consecutive_rate_limits = 0
            else:
                # 실패 시에도 결과 기록
                category_results[cat_code] = {
                    "name": cat_name,
                    "count": 0,
                    "error": result.get("error", "수집 실패")
                }

            # Rate Limit 발생 시 처리
            if result.get("rate_limited"):
                consecutive_rate_limits += 1
                logger.warning(
                    f"[SHOPPING_INSIGHT] Rate Limit 발생 "
                    f"(연속 {consecutive_rate_limits}회)"
                )

                # 연속 Rate Limit 시 중단
                if consecutive_rate_limits >= max_consecutive_rate_limits:
                    logger.error(
                        f"[SHOPPING_INSIGHT] 연속 {max_consecutive_rate_limits}회 "
                        f"Rate Limit - 수집 중단"
                    )
                    break

                # Rate Limit 후 추가 대기 (30초)
                logger.info("[SHOPPING_INSIGHT] Rate Limit 복구 대기 30초...")
                await asyncio.sleep(30.0)

            # 카테고리 간 딜레이 (마지막 제외)
            if i < len(categories) - 1:
                await asyncio.sleep(delay_between_categories)

        logger.info(
            f"[SHOPPING_INSIGHT] 전체 수집 완료: "
            f"{len(all_keywords)}개 키워드 ({len(category_results)}개 카테고리)"
        )

        return {
            "success": len(all_keywords) > 0,
            "total_count": len(all_keywords),
            "categories_collected": len(category_results),
            "category_results": category_results,
            "keywords": all_keywords
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        API 연결 테스트

        Returns:
            연결 테스트 결과
        """
        try:
            # 패션의류 카테고리에서 1페이지만 테스트
            result = await self.get_category_keyword_rank(
                category_code="50000000",
                page=1
            )

            if result.get("success") and result.get("keywords"):
                return {
                    "success": True,
                    "message": f"네이버 쇼핑인사이트 연결 성공 "
                               f"({len(result['keywords'])}개 키워드 확인)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "키워드를 가져오지 못했습니다")
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


def get_all_category_codes() -> Dict[str, str]:
    """
    모든 카테고리 코드 반환

    Returns:
        카테고리 코드와 이름 딕셔너리
    """
    return SHOPPING_CATEGORIES.copy()


def get_main_category_codes() -> Dict[str, str]:
    """
    대분류 카테고리 코드만 반환

    Returns:
        대분류 카테고리 코드와 이름 딕셔너리
    """
    return SHOPPING_CATEGORIES.copy()
