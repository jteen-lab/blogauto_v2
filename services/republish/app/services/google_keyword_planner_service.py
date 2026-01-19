"""
Google Keyword Planner API 서비스

Features:
- Google Ads API를 통한 키워드 아이디어 조회
- 키워드 검색량 및 경쟁도 조회
- OAuth2 인증 기반

Requirements:
- google-ads 패키지 설치 필요
- Google Ads 개발자 토큰 필요
- OAuth2 인증 정보 필요 (client_id, client_secret, refresh_token)
- Google Ads 고객 ID 필요

API Docs:
- https://developers.google.com/google-ads/api/docs/keyword-planning/overview
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)


@dataclass
class KeywordIdea:
    """키워드 아이디어 데이터"""
    keyword: str
    avg_monthly_searches: int
    competition: str  # LOW, MEDIUM, HIGH
    competition_index: int  # 0-100
    low_top_of_page_bid: int  # 마이크로 단위 (1,000,000 = 1원)
    high_top_of_page_bid: int


class GoogleKeywordPlannerService:
    """Google Keyword Planner API 서비스"""

    def __init__(self, settings: UserSettings = None):
        """
        Args:
            settings: UserSettings 객체 (미리 조회된 설정)
        """
        self._settings = settings
        self._client = None

    @property
    def settings(self) -> Optional[UserSettings]:
        """사용자 설정"""
        return self._settings

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        if not self.settings:
            return False
        return self.settings.has_google_keyword_planner_api

    def _get_client(self):
        """Google Ads 클라이언트 생성"""
        if self._client:
            return self._client

        if not self.is_configured():
            raise ValueError("Google Keyword Planner API 설정이 없습니다")

        try:
            from google.ads.googleads.client import GoogleAdsClient

            # 설정 딕셔너리로 클라이언트 생성
            credentials = {
                "developer_token": self.settings.google_ads_developer_token,
                "client_id": self.settings.google_ads_client_id,
                "client_secret": self.settings.google_ads_client_secret,
                "refresh_token": self.settings.google_ads_refresh_token,
                "use_proto_plus": True
            }

            self._client = GoogleAdsClient.load_from_dict(credentials)
            return self._client

        except ImportError:
            logger.error("[GOOGLE_PLANNER] google-ads 패키지가 설치되지 않았습니다")
            raise ImportError(
                "google-ads 패키지가 설치되지 않았습니다. "
                "'pip install google-ads'로 설치해주세요."
            )
        except Exception as e:
            logger.error(f"[GOOGLE_PLANNER] 클라이언트 생성 실패: {e}")
            raise

    def _get_customer_id(self) -> str:
        """고객 ID 반환 (하이픈 제거)"""
        customer_id = self.settings.google_ads_customer_id or ""
        return customer_id.replace("-", "")

    async def get_keyword_ideas(
        self,
        keywords: List[str],
        page_url: str = None,
        language_id: str = "1012",  # 한국어
        location_ids: List[str] = None,
        include_adult_keywords: bool = False
    ) -> Dict[str, Any]:
        """
        키워드 아이디어 조회

        Args:
            keywords: 시드 키워드 목록
            page_url: 참조 URL (선택)
            language_id: 언어 ID (기본: 1012=한국어)
            location_ids: 지역 ID 목록 (기본: 2410=한국)
            include_adult_keywords: 성인 키워드 포함 여부

        Returns:
            키워드 아이디어 목록
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "Google Keyword Planner API가 설정되지 않았습니다",
                "keywords": []
            }

        if location_ids is None:
            location_ids = ["2410"]  # 한국

        try:
            client = self._get_client()
            customer_id = self._get_customer_id()

            keyword_plan_idea_service = client.get_service(
                "KeywordPlanIdeaService"
            )
            keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

            # 지역 및 언어 리소스 이름 생성
            location_rns = [
                client.get_service("GeoTargetConstantService").geo_target_constant_path(loc)
                for loc in location_ids
            ]
            language_rn = client.get_service(
                "GoogleAdsService"
            ).language_constant_path(language_id)

            # 요청 생성
            request = client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = customer_id
            request.language = language_rn
            request.geo_target_constants.extend(location_rns)
            request.include_adult_keywords = include_adult_keywords
            request.keyword_plan_network = keyword_plan_network

            # 키워드 시드 설정
            if keywords:
                request.keyword_seed.keywords.extend(keywords)

            # URL 시드 설정
            if page_url:
                request.url_seed.url = page_url

            # API 호출
            keyword_ideas = keyword_plan_idea_service.generate_keyword_ideas(
                request=request
            )

            results = []
            for idea in keyword_ideas:
                keyword_idea = {
                    "keyword": idea.text,
                    "avg_monthly_searches": idea.keyword_idea_metrics.avg_monthly_searches,
                    "competition": idea.keyword_idea_metrics.competition.name,
                    "competition_index": idea.keyword_idea_metrics.competition_index,
                    "source": "google_planner"
                }

                # 입찰가 정보 (마이크로 단위를 원 단위로 변환)
                if idea.keyword_idea_metrics.low_top_of_page_bid_micros:
                    keyword_idea["low_bid"] = (
                        idea.keyword_idea_metrics.low_top_of_page_bid_micros / 1_000_000
                    )
                if idea.keyword_idea_metrics.high_top_of_page_bid_micros:
                    keyword_idea["high_bid"] = (
                        idea.keyword_idea_metrics.high_top_of_page_bid_micros / 1_000_000
                    )

                results.append(keyword_idea)

            # 검색량 기준 정렬
            results.sort(key=lambda x: x.get("avg_monthly_searches", 0), reverse=True)

            logger.info(f"[GOOGLE_PLANNER] 키워드 아이디어 조회 완료: {len(results)}개")

            return {
                "success": True,
                "total_count": len(results),
                "keywords": results
            }

        except ImportError as e:
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }
        except Exception as e:
            logger.error(f"[GOOGLE_PLANNER] API 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }

    async def get_keyword_stats(
        self,
        keywords: List[str],
        language_id: str = "1012",
        location_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        키워드 검색량 통계 조회

        Args:
            keywords: 조회할 키워드 목록
            language_id: 언어 ID
            location_ids: 지역 ID 목록

        Returns:
            키워드별 검색량 통계
        """
        return await self.get_keyword_ideas(
            keywords=keywords,
            language_id=language_id,
            location_ids=location_ids
        )

    async def collect_keywords(
        self,
        seed_keywords: List[str],
        max_keywords: int = 100
    ) -> Dict[str, Any]:
        """
        시드 키워드 기반 키워드 수집

        Args:
            seed_keywords: 시드 키워드 목록
            max_keywords: 최대 수집 키워드 수

        Returns:
            수집된 키워드 목록
        """
        if not seed_keywords:
            return {
                "success": False,
                "error": "시드 키워드가 없습니다",
                "keywords": []
            }

        result = await self.get_keyword_ideas(keywords=seed_keywords)

        if not result.get("success"):
            return result

        keywords = result.get("keywords", [])[:max_keywords]

        # 수집용 데이터 형식으로 변환
        collected = []
        for kw in keywords:
            collected.append({
                "keyword": kw["keyword"],
                "search_volume": kw.get("avg_monthly_searches", 0),
                "competition": kw.get("competition", "UNKNOWN"),
                "source": "google_planner",
                "type": "keyword"
            })

        logger.info(f"[GOOGLE_PLANNER] 키워드 수집 완료: {len(collected)}개")

        return {
            "success": True,
            "total_count": len(collected),
            "keywords": collected
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
            # google-ads 패키지 확인
            try:
                from google.ads.googleads.client import GoogleAdsClient
            except ImportError:
                return {
                    "success": False,
                    "error": "google-ads 패키지가 설치되지 않았습니다"
                }

            # 클라이언트 생성 테스트
            client = self._get_client()
            customer_id = self._get_customer_id()

            # 간단한 API 호출로 연결 확인
            ga_service = client.get_service("GoogleAdsService")
            query = "SELECT customer.id FROM customer LIMIT 1"

            response = ga_service.search(customer_id=customer_id, query=query)

            # 응답 확인
            for row in response:
                logger.info(
                    f"[GOOGLE_PLANNER] 연결 테스트 성공: customer_id={row.customer.id}"
                )

            return {
                "success": True,
                "message": "Google Keyword Planner 연결 성공"
            }

        except ImportError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"[GOOGLE_PLANNER] 연결 테스트 실패: {e}")
            return {
                "success": False,
                "error": str(e)
            }
