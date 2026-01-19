"""
네이버 데이터랩 API 서비스

Features:
- 검색어 트렌드 조회
- 키워드 상대적 검색량 비교
- 기간별/성별/연령별 검색 트렌드 분석

API Docs:
- https://developers.naver.com/docs/serviceapi/datalab/search/search.md
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import httpx

from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)


@dataclass
class TrendData:
    """트렌드 데이터"""
    period: str  # 날짜
    ratio: float  # 상대적 검색량 (0-100)


@dataclass
class KeywordTrend:
    """키워드 트렌드"""
    keyword: str
    data: List[TrendData]
    avg_ratio: float  # 평균 상대 검색량


class NaverDatalabService:
    """네이버 데이터랩 API 서비스"""

    BASE_URL = "https://openapi.naver.com/v1/datalab/search"

    def __init__(self, settings: UserSettings = None):
        """
        Args:
            settings: UserSettings 객체 (미리 조회된 설정)
        """
        self._settings = settings

    @property
    def settings(self) -> Optional[UserSettings]:
        """사용자 설정"""
        return self._settings

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        if not self.settings:
            return False
        return self.settings.has_naver_datalab_api

    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        if not self.settings:
            raise ValueError("API 설정이 없습니다")

        return {
            "X-Naver-Client-Id": self.settings.naver_datalab_client_id,
            "X-Naver-Client-Secret": self.settings.naver_datalab_client_secret,
            "Content-Type": "application/json"
        }

    async def get_search_trend(
        self,
        keywords: List[str],
        start_date: str = None,
        end_date: str = None,
        time_unit: str = "week",
        device: str = None,
        gender: str = None,
        ages: List[str] = None
    ) -> Dict[str, Any]:
        """
        검색어 트렌드 조회

        Args:
            keywords: 검색 키워드 목록 (최대 5개)
            start_date: 시작일 (YYYY-MM-DD), 기본값 1년 전
            end_date: 종료일 (YYYY-MM-DD), 기본값 오늘
            time_unit: 구간 단위 (date, week, month)
            device: 기기 (None=전체, pc, mo=모바일)
            gender: 성별 (None=전체, m=남성, f=여성)
            ages: 연령대 목록 (1~11, None=전체)

        Returns:
            검색어 트렌드 데이터
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "네이버 데이터랩 API가 설정되지 않았습니다",
                "trends": []
            }

        # 키워드 개수 제한
        if len(keywords) > 5:
            keywords = keywords[:5]
            logger.warning(f"[NAVER_DATALAB] 키워드가 5개로 제한됨: {keywords}")

        # 기본 날짜 설정
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        try:
            # 키워드 그룹 생성 (각 키워드를 개별 그룹으로)
            keyword_groups = []
            for kw in keywords:
                keyword_groups.append({
                    "groupName": kw,
                    "keywords": [kw]
                })

            # 요청 바디
            body = {
                "startDate": start_date,
                "endDate": end_date,
                "timeUnit": time_unit,
                "keywordGroups": keyword_groups
            }

            # 선택적 필터
            if device:
                body["device"] = device
            if gender:
                body["gender"] = gender
            if ages:
                body["ages"] = ages

            headers = self._get_headers()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=body
                )

                if response.status_code != 200:
                    error_msg = response.text
                    logger.error(
                        f"[NAVER_DATALAB] API 오류: {response.status_code} - {error_msg}"
                    )
                    return {
                        "success": False,
                        "error": f"API 오류: {response.status_code}",
                        "trends": []
                    }

                data = response.json()
                return self._parse_trend_response(data)

        except httpx.TimeoutException:
            logger.error("[NAVER_DATALAB] API 타임아웃")
            return {
                "success": False,
                "error": "API 요청 타임아웃",
                "trends": []
            }
        except Exception as e:
            logger.error(f"[NAVER_DATALAB] API 예외: {e}")
            return {
                "success": False,
                "error": str(e),
                "trends": []
            }

    def _parse_trend_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """API 응답 파싱"""
        results = data.get("results", [])
        trends = []

        for result in results:
            keyword = result.get("title", "")
            data_points = result.get("data", [])

            # 평균 검색량 계산
            ratios = [d.get("ratio", 0) for d in data_points]
            avg_ratio = sum(ratios) / len(ratios) if ratios else 0

            trend_data = []
            for point in data_points:
                trend_data.append({
                    "period": point.get("period", ""),
                    "ratio": point.get("ratio", 0)
                })

            trends.append({
                "keyword": keyword,
                "avg_ratio": round(avg_ratio, 2),
                "data": trend_data
            })

        # 평균 검색량 기준 정렬
        trends.sort(key=lambda x: x["avg_ratio"], reverse=True)

        logger.info(f"[NAVER_DATALAB] 트렌드 조회 완료: {len(trends)}개 키워드")

        return {
            "success": True,
            "trends": trends,
            "start_date": data.get("startDate"),
            "end_date": data.get("endDate"),
            "time_unit": data.get("timeUnit")
        }

    async def compare_keywords(
        self,
        keywords: List[str],
        time_unit: str = "month"
    ) -> Dict[str, Any]:
        """
        키워드 검색량 비교

        Args:
            keywords: 비교할 키워드 목록 (최대 5개)
            time_unit: 구간 단위

        Returns:
            키워드별 상대적 검색량 비교
        """
        result = await self.get_search_trend(
            keywords=keywords,
            time_unit=time_unit
        )

        if not result.get("success"):
            return result

        # 최신 데이터 기준 순위 매기기
        trends = result.get("trends", [])
        comparison = []

        for i, trend in enumerate(trends):
            latest_ratio = trend["data"][-1]["ratio"] if trend["data"] else 0
            comparison.append({
                "rank": i + 1,
                "keyword": trend["keyword"],
                "avg_ratio": trend["avg_ratio"],
                "latest_ratio": latest_ratio
            })

        return {
            "success": True,
            "comparison": comparison,
            "period": f"{result.get('start_date')} ~ {result.get('end_date')}"
        }

    async def collect_trending_keywords(
        self,
        seed_keywords: List[str],
        max_keywords: int = 50
    ) -> Dict[str, Any]:
        """
        시드 키워드 기반 트렌드 키워드 수집

        네이버 데이터랩은 연관 키워드를 제공하지 않으므로
        시드 키워드의 트렌드 데이터만 반환합니다.

        Args:
            seed_keywords: 시드 키워드 목록
            max_keywords: 최대 수집 키워드 수

        Returns:
            수집된 트렌드 키워드 목록
        """
        if not seed_keywords:
            return {
                "success": False,
                "error": "시드 키워드가 없습니다",
                "keywords": []
            }

        all_keywords = []

        # 5개씩 나눠서 조회 (API 제한)
        for i in range(0, len(seed_keywords), 5):
            batch = seed_keywords[i:i + 5]
            result = await self.get_search_trend(
                keywords=batch,
                time_unit="month"
            )

            if result.get("success"):
                for trend in result.get("trends", []):
                    all_keywords.append({
                        "keyword": trend["keyword"],
                        "trend_score": int(trend["avg_ratio"]),
                        "source": "naver_datalab",
                        "type": "trend"
                    })

        # 점수 기준 정렬
        all_keywords.sort(key=lambda x: x["trend_score"], reverse=True)
        all_keywords = all_keywords[:max_keywords]

        logger.info(
            f"[NAVER_DATALAB] 트렌드 키워드 수집 완료: {len(all_keywords)}개"
        )

        return {
            "success": True,
            "total_count": len(all_keywords),
            "keywords": all_keywords
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        API 연결 테스트

        Returns:
            연결 테스트 결과
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "API 설정이 되어 있지 않습니다"
            }

        try:
            result = await self.get_search_trend(
                keywords=["테스트"],
                time_unit="month"
            )

            if result.get("success"):
                return {
                    "success": True,
                    "message": "네이버 데이터랩 연결 성공"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "알 수 없는 오류")
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
