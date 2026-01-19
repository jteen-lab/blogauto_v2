"""
네이버 검색광고 API 서비스

Features:
- 키워드 검색량 조회
- 연관 키워드 수집
- API 인증 및 요청 처리

API Docs:
- https://naver.github.io/searchad-apidoc/
"""
import hashlib
import hmac
import base64
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx

from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)


@dataclass
class KeywordData:
    """키워드 데이터"""
    keyword: str
    monthly_pc_qc_cnt: int  # PC 월간 검색량
    monthly_mobile_qc_cnt: int  # 모바일 월간 검색량
    total_qc_cnt: int  # 총 월간 검색량
    competition_level: str  # 경쟁 수준 (높음/중간/낮음)
    avg_cpc: Optional[int] = None  # 평균 클릭 비용


class NaverAdsService:
    """네이버 검색광고 API 서비스"""

    BASE_URL = "https://api.searchad.naver.com"
    KEYWORD_TOOL_PATH = "/keywordstool"

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
        return self.settings.has_naver_ads_api

    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        path: str,
        secret_key: str
    ) -> str:
        """
        API 서명 생성

        Args:
            timestamp: 타임스탬프 (밀리초)
            method: HTTP 메서드
            path: API 경로
            secret_key: Secret 키

        Returns:
            Base64 인코딩된 서명
        """
        message = f"{timestamp}.{method}.{path}"
        signature = hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _get_headers(self, method: str, path: str) -> Dict[str, str]:
        """
        API 요청 헤더 생성

        Args:
            method: HTTP 메서드
            path: API 경로

        Returns:
            요청 헤더 딕셔너리
        """
        if not self.settings:
            raise ValueError("API 설정이 없습니다")

        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(
            timestamp,
            method,
            path,
            self.settings.naver_ads_secret_key
        )

        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.settings.naver_ads_api_key,
            "X-Customer": self.settings.naver_ads_customer_id,
            "X-Signature": signature
        }

    async def get_keyword_stats(
        self,
        keywords: List[str],
        include_related: bool = True
    ) -> Dict[str, Any]:
        """
        키워드 검색량 및 연관 키워드 조회

        Args:
            keywords: 조회할 키워드 목록 (최대 5개)
            include_related: 연관 키워드 포함 여부

        Returns:
            키워드 통계 정보
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "네이버 검색광고 API가 설정되지 않았습니다",
                "keywords": []
            }

        # 키워드 개수 제한
        if len(keywords) > 5:
            keywords = keywords[:5]
            logger.warning(f"키워드가 5개로 제한되었습니다: {keywords}")

        try:
            headers = self._get_headers("GET", self.KEYWORD_TOOL_PATH)
            params = {
                "hintKeywords": ",".join(keywords),
                "showDetail": "1"  # 상세 정보 포함
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}{self.KEYWORD_TOOL_PATH}",
                    headers=headers,
                    params=params
                )

                if response.status_code != 200:
                    logger.error(
                        f"[NAVER_ADS] API 오류: {response.status_code} - "
                        f"{response.text}"
                    )
                    return {
                        "success": False,
                        "error": f"API 오류: {response.status_code}",
                        "keywords": []
                    }

                data = response.json()
                return self._parse_keyword_response(data, include_related)

        except httpx.TimeoutException:
            logger.error("[NAVER_ADS] API 타임아웃")
            return {
                "success": False,
                "error": "API 요청 타임아웃",
                "keywords": []
            }
        except Exception as e:
            logger.error(f"[NAVER_ADS] API 예외: {e}")
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }

    def _parse_keyword_response(
        self,
        data: Dict[str, Any],
        include_related: bool
    ) -> Dict[str, Any]:
        """
        API 응답 파싱

        Args:
            data: API 응답 데이터
            include_related: 연관 키워드 포함 여부

        Returns:
            파싱된 키워드 데이터
        """
        keyword_list = data.get("keywordList", [])
        result = {
            "success": True,
            "keywords": [],
            "related_keywords": []
        }

        for item in keyword_list:
            keyword_data = KeywordData(
                keyword=item.get("relKeyword", ""),
                monthly_pc_qc_cnt=self._parse_count(
                    item.get("monthlyPcQcCnt", "< 10")
                ),
                monthly_mobile_qc_cnt=self._parse_count(
                    item.get("monthlyMobileQcCnt", "< 10")
                ),
                total_qc_cnt=0,
                competition_level=self._parse_competition(
                    item.get("compIdx", "")
                ),
                avg_cpc=item.get("plAvgDepth")
            )

            # 총 검색량 계산
            keyword_data.total_qc_cnt = (
                keyword_data.monthly_pc_qc_cnt +
                keyword_data.monthly_mobile_qc_cnt
            )

            # 입력 키워드와 연관 키워드 분리
            result["keywords"].append({
                "keyword": keyword_data.keyword,
                "pc_search_volume": keyword_data.monthly_pc_qc_cnt,
                "mobile_search_volume": keyword_data.monthly_mobile_qc_cnt,
                "total_search_volume": keyword_data.total_qc_cnt,
                "competition": keyword_data.competition_level,
                "avg_cpc": keyword_data.avg_cpc
            })

        # 연관 키워드 분리 (검색량 기준 정렬)
        if include_related and len(result["keywords"]) > 1:
            # 첫 번째 키워드는 원본, 나머지는 연관 키워드
            result["related_keywords"] = sorted(
                result["keywords"][1:],
                key=lambda x: x["total_search_volume"],
                reverse=True
            )
            result["keywords"] = result["keywords"][:1]

        return result

    def _parse_count(self, value: Any) -> int:
        """
        검색량 파싱 (< 10 형태 처리)

        Args:
            value: 검색량 값

        Returns:
            정수 검색량
        """
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            if value.startswith("< "):
                return int(value.replace("< ", "")) - 1
            try:
                return int(value.replace(",", ""))
            except ValueError:
                return 0
        return 0

    def _parse_competition(self, value: str) -> str:
        """
        경쟁도 파싱

        Args:
            value: 경쟁도 값

        Returns:
            한글 경쟁도
        """
        competition_map = {
            "HIGH": "높음",
            "MEDIUM": "중간",
            "LOW": "낮음"
        }
        return competition_map.get(value, "알 수 없음")

    async def collect_keywords(
        self,
        seed_keywords: List[str],
        max_related: int = 50
    ) -> Dict[str, Any]:
        """
        시드 키워드로 연관 키워드 수집

        Args:
            seed_keywords: 시드 키워드 목록
            max_related: 최대 연관 키워드 수

        Returns:
            수집된 키워드 목록
        """
        all_keywords = []
        seen_keywords = set()

        for keyword in seed_keywords:
            result = await self.get_keyword_stats([keyword], include_related=True)

            if not result.get("success"):
                continue

            # 원본 키워드 추가
            for kw in result.get("keywords", []):
                if kw["keyword"] not in seen_keywords:
                    all_keywords.append(kw)
                    seen_keywords.add(kw["keyword"])

            # 연관 키워드 추가
            for kw in result.get("related_keywords", []):
                if kw["keyword"] not in seen_keywords:
                    all_keywords.append(kw)
                    seen_keywords.add(kw["keyword"])

                    if len(all_keywords) >= max_related:
                        break

            if len(all_keywords) >= max_related:
                break

        # 검색량 기준 정렬
        all_keywords.sort(key=lambda x: x["total_search_volume"], reverse=True)

        return {
            "success": True,
            "total_count": len(all_keywords),
            "keywords": all_keywords[:max_related]
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
            result = await self.get_keyword_stats(["테스트"])

            if result.get("success"):
                return {
                    "success": True,
                    "message": "API 연결 성공"
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
