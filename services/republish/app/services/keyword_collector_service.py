"""
키워드/제목 자동 수집 서비스

각 API에서 트렌딩/인기 키워드를 자동으로 수집하여 데이터 관리 테이블에 저장합니다.
뉴스 제목은 키워드 추출 없이 그대로 TempTitle 테이블에 저장됩니다.

수집 소스:
- 구글 트렌드: 실시간 인기 검색어 → SeedKeyword
- 네이버 데이터랩: 인기 검색어 트렌드 → SeedKeyword
- 네이버 광고 도구: 연관 키워드 → SeedKeyword
- 네이버 뉴스: 뉴스 제목 → TempTitle (신규)
- 구글 뉴스 RSS: 뉴스 제목 → TempTitle (신규)

수집 모드:
- 일반 수집: API 검색 결과 기반, 수량 제한 적용
- 대량 수집: 블로그/사이트 전체 포스트 제목 수집, 수량 제한 없음

Features:
- 자동 트렌딩 키워드 수집
- 뉴스 제목 수집 (정보성 블로그에 적합)
- 대량 제목 수집 (블로그/사이트 전체 포스트)
- 중복 제거
- 수량 제한 엄격 적용 (일반 수집만)
- 도메인 필터 적용 (대량 수집)
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import re
from ..models.user_settings import UserSettings
from ..models.keyword import SeedKeyword
from ..models.title import TempTitle
from ..models.content_filter import ContentFilter
from ..core.logger import get_logger

logger = get_logger("keyword_collector", "keyword_collector.log")


class KeywordCollectorService:
    """키워드/제목 자동 수집 서비스"""

    def __init__(self, db: AsyncSession, settings: UserSettings):
        """
        Args:
            db: 데이터베이스 세션
            settings: 사용자 설정
        """
        self.db = db
        self.settings = settings
        self._filters_cache: Optional[List[ContentFilter]] = None
        # ★ 수집 세션 내 중복 체크 캐시 (1차 중복 제거용)
        self._seen_keywords: set = set()  # 이미 처리된 키워드 (소문자)
        self._seen_titles: set = set()  # 이미 처리된 제목 (소문자)
        # ★ 카테고리 매칭 서비스 (수집 시 자동 카테고리 할당)
        self._category_matcher = None

    def _init_category_matcher(self) -> None:
        """카테고리 매칭 서비스 초기화 (lazy)"""
        if self._category_matcher is None:
            try:
                from .category_matcher_service import CategoryMatcherService
                self._category_matcher = CategoryMatcherService(self.db)
                logger.info("[COLLECTOR] 카테고리 매칭 서비스 초기화 완료")
            except Exception as e:
                logger.warning(f"[COLLECTOR] 카테고리 매칭 서비스 초기화 실패: {e}")
                self._category_matcher = None

    async def _load_filters(self, force_reload: bool = False) -> List[ContentFilter]:
        """
        활성 필터 로드

        Args:
            force_reload: True면 캐시 무시하고 DB에서 새로 로드

        Returns:
            활성 필터 목록
        """
        if force_reload or self._filters_cache is None:
            # 먼저 전체 필터 수 확인 (is_active 무관)
            from sqlalchemy import func
            total_count_query = select(func.count()).select_from(ContentFilter)
            total_count = (await self.db.execute(total_count_query)).scalar() or 0

            # 활성 필터만 조회
            query = select(ContentFilter).where(ContentFilter.is_active == True)
            result = await self.db.execute(query)
            self._filters_cache = list(result.scalars().all())

            logger.info(f"[COLLECTOR] 📊 필터 DB 조회: 전체 {total_count}개, 활성 {len(self._filters_cache)}개")

            if len(self._filters_cache) == 0:
                logger.warning(f"[COLLECTOR] ⚠️ 활성 필터가 없습니다! (is_active=True인 필터 0개)")
                # 비활성 필터가 있는지 확인
                if total_count > 0:
                    logger.warning(f"[COLLECTOR] ⚠️ 전체 필터 {total_count}개 중 활성화된 것이 없습니다!")
            else:
                logger.info(f"[COLLECTOR] ✅ 필터 {len(self._filters_cache)}개 로드 (force={force_reload})")
                # 필터 목록 출력 (디버깅용)
                for f in self._filters_cache:
                    logger.info(
                        f"[COLLECTOR]   - id={f.id}, '{f.filter_value}' "
                        f"(type={f.filter_type}, target={f.target_type}, active={f.is_active})"
                    )

        return self._filters_cache

    def _clear_filter_cache(self) -> None:
        """필터 캐시 초기화"""
        self._filters_cache = None

    async def _check_filter(self, text: str, target_type: str) -> Optional[ContentFilter]:
        """
        텍스트가 필터에 걸리는지 확인

        Args:
            text: 확인할 텍스트 (키워드 또는 제목)
            target_type: 'keyword' 또는 'title'

        Returns:
            매칭된 필터 객체 (없으면 None)
        """
        # 캐시된 필터 사용 (collect_all에서 이미 로드됨)
        filters = await self._load_filters()

        # 필터가 없으면 경고 후 통과
        if not filters:
            logger.warning(f"[FILTER] ⚠️ 활성 필터 0개 - '{text[:30]}' 필터링 스킵")
            return None

        # 디버그: 필터 체크 시작 로그
        logger.info(f"[FILTER] 🔍 체크 시작: '{text[:50]}' (target={target_type}, 필터 {len(filters)}개)")

        text_lower = text.lower().strip()

        for filter_obj in filters:
            # target_type 체크 (both는 모든 타입에 적용)
            filter_target = filter_obj.target_type.lower().strip() if filter_obj.target_type else "both"
            if filter_target not in [target_type, "both"]:
                continue

            filter_value = filter_obj.filter_value.lower().strip()
            if not filter_value:
                continue

            matched = False
            filter_type = filter_obj.filter_type.lower().strip() if filter_obj.filter_type else "keyword"

            if filter_type == "keyword":
                # 키워드 포함 여부 (대소문자 무시)
                if filter_value in text_lower:
                    matched = True
                    logger.info(f"[FILTER] ✓ 키워드 매칭: '{filter_value}' in '{text_lower[:50]}'")

            elif filter_type == "pattern":
                # 정규식 패턴 매칭
                try:
                    if re.search(filter_value, text_lower):
                        matched = True
                        logger.info(f"[FILTER] ✓ 패턴 매칭: '{filter_value}' in '{text_lower[:50]}'")
                except re.error:
                    logger.warning(f"[FILTER] 잘못된 정규식 패턴: {filter_value}")
                    continue

            elif filter_type == "domain":
                # 도메인 체크 (URL에서 사용)
                if filter_value in text_lower:
                    matched = True
                    logger.info(f"[FILTER] ✓ 도메인 매칭: '{filter_value}' in '{text_lower[:50]}'")

            if matched:
                # 매칭 횟수 증가
                filter_obj.increment_match()
                logger.info(
                    f"[FILTER] ❌ 필터링됨: '{text[:50]}' (target={target_type}) "
                    f"→ 필터 '{filter_obj.filter_value}' (target={filter_target})"
                )
                return filter_obj

        # 필터 통과 로그
        logger.info(f"[FILTER] ✅ 통과: '{text[:50]}' (target={target_type})")
        return None

    async def collect_from_google_trends(self, limit: int = 100) -> Dict[str, Any]:
        """
        구글 트렌드에서 실시간 인기 검색어 수집 → SeedKeyword 저장

        Args:
            limit: 최대 수집 수량

        Returns:
            수집 결과 (성공 여부, 키워드 수, 저장된 수)
        """
        from .google_trends_service import GoogleTrendsService

        logger.info(f"[COLLECTOR] 구글 트렌드 수집 시작 (limit={limit})")

        try:
            service = GoogleTrendsService()

            # 실시간 인기 검색어 조회
            result = await service.get_trending_searches(country="south_korea")

            if not result.get("success"):
                logger.warning(f"[COLLECTOR] 구글 트렌드 조회 실패: {result.get('error')}")
                return {
                    "success": False,
                    "source": "google_trends",
                    "error": result.get("error"),
                    "collected": 0,
                    "saved": 0
                }

            keywords = result.get("trending", [])
            saved_count = 0

            for kw_data in keywords:
                # 수량 제한 체크 (먼저!)
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 구글 트렌드 수량 제한 도달: {limit}개")
                    break

                keyword = kw_data.get("keyword", "") if isinstance(kw_data, dict) else str(kw_data)
                if not keyword:
                    continue

                # 중복 체크 및 저장
                if await self._save_keyword(
                    keyword=keyword,
                    source="google_trends",
                    search_volume=None,
                    competition=None
                ):
                    saved_count += 1

            await self.db.commit()

            logger.info(f"[COLLECTOR] 구글 트렌드 수집 완료: {len(keywords)}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "google_trends",
                "collected": len(keywords),
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 구글 트렌드 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "google_trends",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_from_naver_datalab(
        self,
        base_keywords: Optional[List[str]] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        네이버 데이터랩에서 트렌드 키워드 수집 → SeedKeyword 저장

        Args:
            base_keywords: 기준 키워드 (없으면 기본 키워드 사용)
            limit: 최대 수집 수량

        Returns:
            수집 결과
        """
        from .naver_datalab_service import NaverDatalabService

        if not self.settings.has_naver_datalab_api:
            return {
                "success": False,
                "source": "naver_datalab",
                "error": "API 키가 설정되지 않았습니다",
                "collected": 0,
                "saved": 0
            }

        logger.info(f"[COLLECTOR] 네이버 데이터랩 수집 시작 (limit={limit})")

        try:
            service = NaverDatalabService(self.settings)

            # 기본 키워드 설정 (일반적인 관심 주제)
            if not base_keywords:
                base_keywords = ["뉴스", "이슈", "트렌드", "인기", "화제"]

            saved_count = 0
            total_collected = 0

            for base_keyword in base_keywords:
                # 수량 제한 체크
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 네이버 데이터랩 수량 제한 도달: {limit}개")
                    break

                result = await service.collect_trending_keywords(base_keyword)

                if not result.get("success"):
                    continue

                keywords = result.get("keywords", [])
                total_collected += len(keywords)

                for kw_data in keywords:
                    # 수량 제한 체크
                    if saved_count >= limit:
                        break

                    keyword = kw_data.get("keyword", "")
                    if not keyword:
                        continue

                    avg_ratio = kw_data.get("avg_ratio", 0)

                    if await self._save_keyword(
                        keyword=keyword,
                        source="naver_datalab",
                        search_volume=int(avg_ratio * 100) if avg_ratio else None,
                        competition=None
                    ):
                        saved_count += 1

            await self.db.commit()

            logger.info(f"[COLLECTOR] 네이버 데이터랩 수집 완료: {total_collected}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "naver_datalab",
                "collected": total_collected,
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 네이버 데이터랩 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "naver_datalab",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_from_naver_ads(
        self,
        base_keywords: Optional[List[str]] = None,
        limit: int = 100,
        include_related: bool = True
    ) -> Dict[str, Any]:
        """
        네이버 광고 도구에서 연관 키워드 수집 → SeedKeyword 저장

        Args:
            base_keywords: 기준 키워드 (없으면 기본 키워드 사용)
            limit: 최대 수집 수량
            include_related: 연관 키워드 포함 여부 (enable_related_search 옵션)

        Returns:
            수집 결과
        """
        from .naver_ads_service import NaverAdsService

        if not self.settings.has_naver_ads_api:
            return {
                "success": False,
                "source": "naver_ads",
                "error": "API 키가 설정되지 않았습니다",
                "collected": 0,
                "saved": 0
            }

        logger.info(f"[COLLECTOR] 네이버 광고 도구 수집 시작 (limit={limit}, include_related={include_related})")

        try:
            service = NaverAdsService(self.settings)

            # 기본 키워드 설정 (더 다양한 카테고리 추가)
            if not base_keywords:
                base_keywords = [
                    "건강", "맛집", "여행", "쇼핑", "뷰티",
                    "육아", "재테크", "요리", "운동", "인테리어"
                ]

            saved_count = 0
            total_collected = 0

            for base_keyword in base_keywords:
                # 수량 제한 체크
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 네이버 광고 도구 수량 제한 도달: {limit}개")
                    break

                # include_related 옵션에 따라 연관 키워드 포함 여부 결정
                result = await service.get_keyword_stats([base_keyword], include_related=include_related)

                if not result.get("success"):
                    logger.warning(f"[COLLECTOR] 네이버 광고 '{base_keyword}' 조회 실패")
                    continue

                # 원본 키워드 처리
                keywords = result.get("keywords", [])
                # 연관 키워드도 함께 처리
                related_keywords = result.get("related_keywords", [])

                all_keywords = keywords + related_keywords
                total_collected += len(all_keywords)

                for kw_data in all_keywords:
                    # 수량 제한 체크
                    if saved_count >= limit:
                        break

                    keyword = kw_data.get("keyword", "")
                    if not keyword:
                        continue

                    # 새로운 응답 필드명에 맞춰 수정
                    pc_search = kw_data.get("pc_search_volume", 0) or kw_data.get("monthlyPcQcCnt", 0) or 0
                    mobile_search = kw_data.get("mobile_search_volume", 0) or kw_data.get("monthlyMobileQcCnt", 0) or 0
                    total_search = kw_data.get("total_search_volume", 0) or (pc_search + mobile_search)

                    competition = kw_data.get("competition", "") or kw_data.get("compIdx", "")
                    comp_score = self._parse_competition(competition)

                    if await self._save_keyword(
                        keyword=keyword,
                        source="naver_ads",
                        search_volume=total_search if total_search > 0 else None,
                        competition=comp_score
                    ):
                        saved_count += 1

                logger.debug(f"[COLLECTOR] '{base_keyword}': 원본 {len(keywords)}개, 연관 {len(related_keywords)}개 수집")

            await self.db.commit()

            logger.info(f"[COLLECTOR] 네이버 광고 도구 수집 완료: {total_collected}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "naver_ads",
                "collected": total_collected,
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 네이버 광고 도구 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "naver_ads",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_from_naver_news(
        self,
        limit: int = 100,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        네이버 뉴스에서 제목 수집 → TempTitle 저장

        Args:
            limit: 최대 수집 수량
            use_random: True면 랜덤 카테고리에서 20개씩 수집

        Returns:
            수집 결과
        """
        from .naver_news_service import NaverNewsService

        logger.info(f"[COLLECTOR] 네이버 뉴스 수집 시작 (limit={limit}, random={use_random})")

        try:
            service = NaverNewsService(self.settings)

            if not service.is_configured():
                return {
                    "success": False,
                    "source": "naver_news",
                    "error": "네이버 API 키가 설정되지 않았습니다",
                    "collected": 0,
                    "saved": 0
                }

            # 뉴스 제목 수집 (랜덤 모드 지원)
            result = await service.collect_news_titles(limit=limit, use_random=use_random)

            if not result.get("success"):
                return {
                    "success": False,
                    "source": "naver_news",
                    "error": result.get("error", "수집 실패"),
                    "collected": 0,
                    "saved": 0
                }

            titles = result.get("titles", [])
            saved_count = 0

            for title_data in titles:
                # 수량 제한 체크
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 네이버 뉴스 수량 제한 도달: {limit}개")
                    break

                if await self._save_title(
                    title=title_data["title"],
                    source="naver_news",
                    source_url=title_data.get("link", ""),
                    category=title_data.get("category", "")
                ):
                    saved_count += 1

            await self.db.commit()

            logger.info(f"[COLLECTOR] 네이버 뉴스 수집 완료: {len(titles)}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "naver_news",
                "collected": len(titles),
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 네이버 뉴스 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "naver_news",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_from_naver_webdoc(
        self,
        limit: int = 100,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        네이버 웹문서에서 제목 수집 → TempTitle 저장

        Args:
            limit: 최대 수집 수량
            use_random: True면 랜덤 카테고리에서 20개씩 수집

        Returns:
            수집 결과
        """
        from .naver_webdoc_service import NaverWebdocService

        logger.info(f"[COLLECTOR] 네이버 웹문서 수집 시작 (limit={limit}, random={use_random})")

        try:
            service = NaverWebdocService(self.settings)

            if not service.is_configured():
                return {
                    "success": False,
                    "source": "naver_webdoc",
                    "error": "네이버 API 키가 설정되지 않았습니다",
                    "collected": 0,
                    "saved": 0
                }

            # 웹문서 제목 수집 (랜덤 모드 지원)
            result = await service.collect_webdoc_titles(limit=limit, use_random=use_random)

            if not result.get("success"):
                return {
                    "success": False,
                    "source": "naver_webdoc",
                    "error": result.get("error", "수집 실패"),
                    "collected": 0,
                    "saved": 0
                }

            titles = result.get("titles", [])
            saved_count = 0

            for title_data in titles:
                # 수량 제한 체크
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 네이버 웹문서 수량 제한 도달: {limit}개")
                    break

                if await self._save_title(
                    title=title_data["title"],
                    source="naver_webdoc",
                    source_url=title_data.get("link", ""),
                    category=title_data.get("category", "")
                ):
                    saved_count += 1

            await self.db.commit()

            logger.info(f"[COLLECTOR] 네이버 웹문서 수집 완료: {len(titles)}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "naver_webdoc",
                "collected": len(titles),
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 네이버 웹문서 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "naver_webdoc",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_from_google_news(
        self,
        limit: int = 100,
        use_random: bool = False
    ) -> Dict[str, Any]:
        """
        구글 뉴스 RSS에서 제목 수집 → TempTitle 저장

        Args:
            limit: 최대 수집 수량
            use_random: True면 랜덤 토픽/카테고리에서 20개씩 수집

        Returns:
            수집 결과
        """
        from .google_news_rss_service import GoogleNewsRssService

        logger.info(f"[COLLECTOR] 구글 뉴스 RSS 수집 시작 (limit={limit}, random={use_random})")

        try:
            service = GoogleNewsRssService()

            # 뉴스 제목 수집 (토픽 + 검색 혼합, 랜덤 모드 지원)
            result = await service.collect_news_titles(limit=limit, use_random=use_random)

            if not result.get("success"):
                return {
                    "success": False,
                    "source": "google_news",
                    "error": result.get("error", "수집 실패"),
                    "collected": 0,
                    "saved": 0
                }

            titles = result.get("titles", [])
            saved_count = 0

            for title_data in titles:
                # 수량 제한 체크
                if saved_count >= limit:
                    logger.info(f"[COLLECTOR] 구글 뉴스 수량 제한 도달: {limit}개")
                    break

                if await self._save_title(
                    title=title_data["title"],
                    source="google_news",
                    source_url=title_data.get("link", ""),
                    category=title_data.get("category", "")
                ):
                    saved_count += 1

            await self.db.commit()

            logger.info(f"[COLLECTOR] 구글 뉴스 RSS 수집 완료: {len(titles)}개 중 {saved_count}개 저장")

            return {
                "success": True,
                "source": "google_news",
                "collected": len(titles),
                "saved": saved_count
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 구글 뉴스 RSS 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "google_news",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_bulk_titles(
        self,
        keywords: Optional[List[str]] = None,
        delay_between_sites: float = 0.5,
        urls_per_cycle: int = 3,
        max_titles_per_url: Optional[int] = None,
        keyword_limit: int = 20
    ) -> Dict[str, Any]:
        """
        대량 제목 수집 (2단계 분리 방식)

        수집 프로세스:
        1. Phase 1: 키워드로 검색 → URL 수집 및 저장 (CollectedUrl)
        2. Phase 2: 저장된 URL 중 1~3개에서만 제목 수집 (TempTitle)

        Args:
            keywords: 검색 키워드 목록 (없으면 SeedKeyword에서 조회)
            delay_between_sites: 사이트 간 딜레이 (초)
            urls_per_cycle: 주기당 처리할 URL 수 (기본 3개)
            max_titles_per_url: URL당 최대 제목 수집 수 (None=무제한, 사이트맵 전체)
            keyword_limit: 검색에 사용할 최대 키워드 수 (기본 20)

        Returns:
            수집 결과
        """
        from .bulk_title_collector_service import BulkTitleCollectorService

        logger.info(
            f"[COLLECTOR] 대량 제목 수집 시작 (2단계 방식) | "
            f"delay={delay_between_sites}s, urls_per_cycle={urls_per_cycle}, "
            f"max_titles_per_url={'무제한' if not max_titles_per_url else max_titles_per_url}, keyword_limit={keyword_limit}"
        )

        try:
            # 키워드가 없으면 SeedKeyword에서 조회 (keyword_limit 적용)
            if not keywords:
                available_keywords = await self.get_available_keywords_for_search(limit=keyword_limit)
                keywords = [kw.keyword for kw in available_keywords]

                if not keywords:
                    logger.warning("[BULK_COLLECTOR] 사용 가능한 키워드 없음")
                    return {
                        "success": False,
                        "source": "bulk_collect",
                        "error": "사용 가능한 키워드가 없습니다",
                        "collected": 0,
                        "saved": 0
                    }

            # 필터 로드
            filters = await self._load_filters()

            # 대량 수집 서비스 인스턴스 생성 (db 세션 전달)
            bulk_service = BulkTitleCollectorService(
                db=self.db,
                settings=self.settings,
                filters=filters
            )

            # 대량 수집 실행 (2단계 방식) - max_titles_per_url 전달
            result = await bulk_service.collect_bulk_titles(
                keywords=keywords,
                delay_between_sites=delay_between_sites,
                urls_per_cycle=urls_per_cycle,
                max_titles_per_url=max_titles_per_url
            )

            if not result.get("success"):
                return {
                    "success": False,
                    "source": "bulk_collect",
                    "error": result.get("error", "대량 수집 실패"),
                    "collected": 0,
                    "saved": 0,
                    "stats": result.get("stats", {})
                }

            # 수집된 제목 저장 (TempTitle)
            titles = result.get("titles", [])
            saved_count = 0

            for title_data in titles:
                title = title_data.get("title", "")
                if not title:
                    continue

                if await self._save_title(
                    title=title,
                    source="bulk_collect",
                    source_url=title_data.get("rss_url", "") or title_data.get("link", ""),
                    category=title_data.get("platform", "")
                ):
                    saved_count += 1

            await self.db.commit()

            stats = result.get("stats", {})
            logger.info(
                f"[BULK_COLLECTOR] 대량 수집 완료: "
                f"URL {stats.get('phase1_urls_saved', 0)}개 저장, "
                f"{stats.get('phase2_urls_processed', 0)}개 처리, "
                f"제목 {len(titles)}개 수집, {saved_count}개 저장"
            )

            return {
                "success": True,
                "source": "bulk_collect",
                "collected": len(titles),
                "saved": saved_count,
                "stats": stats,
                "filtered_domains": result.get("filtered_domains", [])
            }

        except Exception as e:
            logger.error(f"[BULK_COLLECTOR] 대량 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "bulk_collect",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def get_available_keywords_for_search(self, limit: int = 10) -> List[SeedKeyword]:
        """
        검색에 사용할 키워드 조회 (use_count 0~3, 우선순위: 0→1→2→3)

        use_count가 4 이상인 키워드는 비활성화됩니다.

        Args:
            limit: 최대 키워드 수

        Returns:
            사용 가능한 키워드 목록
        """
        # use_count 4 이상 키워드 비활성화
        deactivate_query = (
            select(SeedKeyword)
            .where(SeedKeyword.use_count >= 4)
            .where(SeedKeyword.is_active == True)
        )
        deactivate_result = await self.db.execute(deactivate_query)
        keywords_to_deactivate = deactivate_result.scalars().all()

        for kw in keywords_to_deactivate:
            kw.is_active = False
            logger.info(f"[COLLECTOR] 키워드 비활성화 (use_count>=4): {kw.keyword}")

        if keywords_to_deactivate:
            await self.db.commit()

        # use_count 0~3 키워드를 우선순위 순서로 조회
        available_keywords: List[SeedKeyword] = []

        for use_count in range(4):  # 0, 1, 2, 3 순서
            if len(available_keywords) >= limit:
                break

            remaining = limit - len(available_keywords)
            query = (
                select(SeedKeyword)
                .where(SeedKeyword.is_active == True)
                .where(SeedKeyword.use_count == use_count)
                .order_by(SeedKeyword.created_at.asc())
                .limit(remaining)
            )
            result = await self.db.execute(query)
            keywords = result.scalars().all()
            available_keywords.extend(keywords)

            if keywords:
                logger.info(f"[COLLECTOR] use_count={use_count} 키워드 {len(keywords)}개 선택")

        return available_keywords

    async def has_available_keywords(self) -> bool:
        """
        검색에 사용할 수 있는 키워드가 있는지 확인

        Returns:
            사용 가능한 키워드 존재 여부
        """
        query = (
            select(SeedKeyword)
            .where(SeedKeyword.is_active == True)
            .where(SeedKeyword.use_count < 4)
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalars().first() is not None

    async def collect_titles_by_keywords(self, limit: int = 100) -> Dict[str, Any]:
        """
        키워드 기반 제목 수집 (네이버 웹문서 검색)

        use_count 0~3인 키워드로 검색하여 제목을 수집합니다.
        검색에 사용된 키워드는 use_count가 1 증가합니다.

        Args:
            limit: 최대 수집 수량

        Returns:
            수집 결과
        """
        from .naver_webdoc_service import NaverWebdocService

        logger.info(f"[COLLECTOR] 키워드 기반 제목 수집 시작 (limit={limit})")

        try:
            service = NaverWebdocService(self.settings)

            if not service.is_configured():
                return {
                    "success": False,
                    "source": "keyword_search",
                    "error": "네이버 API 키가 설정되지 않았습니다",
                    "collected": 0,
                    "saved": 0
                }

            # 검색에 사용할 키워드 조회 (최대 20개)
            keywords = await self.get_available_keywords_for_search(limit=20)

            if not keywords:
                logger.info("[COLLECTOR] 사용 가능한 키워드 없음 - 직접 수집으로 전환")
                return {
                    "success": False,
                    "source": "keyword_search",
                    "error": "사용 가능한 키워드가 없습니다",
                    "collected": 0,
                    "saved": 0,
                    "fallback_required": True
                }

            total_collected = 0
            total_saved = 0
            per_keyword_limit = max(5, limit // len(keywords))

            for keyword in keywords:
                if total_saved >= limit:
                    break

                logger.info(f"[COLLECTOR] 키워드 '{keyword.keyword}' (use_count={keyword.use_count}) 검색 중...")

                # 네이버 웹문서 검색
                result = await service.search_by_keyword(
                    keyword=keyword.keyword,
                    limit=per_keyword_limit
                )

                if result.get("success"):
                    titles = result.get("titles", [])

                    for title_data in titles:
                        if total_saved >= limit:
                            break

                        if await self._save_title(
                            title=title_data["title"],
                            source="keyword_search",
                            source_url=title_data.get("link", ""),
                            category=keyword.keyword  # 검색 키워드를 카테고리로 저장
                        ):
                            total_saved += 1

                    total_collected += len(titles)

                    # 키워드 사용 횟수 증가
                    keyword.mark_used()
                    logger.info(f"[COLLECTOR] 키워드 '{keyword.keyword}' use_count 증가: {keyword.use_count}")
                else:
                    logger.warning(f"[COLLECTOR] 키워드 '{keyword.keyword}' 검색 실패: {result.get('error')}")

            await self.db.commit()

            logger.info(f"[COLLECTOR] 키워드 기반 제목 수집 완료: {total_collected}개 수집, {total_saved}개 저장")

            return {
                "success": True,
                "source": "keyword_search",
                "collected": total_collected,
                "saved": total_saved,
                "keywords_used": len(keywords)
            }

        except Exception as e:
            logger.error(f"[COLLECTOR] 키워드 기반 제목 수집 에러: {str(e)}", exc_info=True)
            return {
                "success": False,
                "source": "keyword_search",
                "error": str(e),
                "collected": 0,
                "saved": 0
            }

    async def collect_all(
        self,
        sources: Optional[List[str]] = None,
        keyword_limit: int = 100,
        title_limit: Optional[int] = None,
        enable_related_search: bool = True,
        enable_normal_collect: bool = True,
        enable_bulk_collect: bool = False,
        bulk_collect_delay: float = 0.5,
        bulk_urls_per_cycle: int = 3,
        module_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        모든 소스에서 키워드/제목 수집

        Args:
            sources: 수집할 소스 목록 (None이면 전체)
                    키워드: ['google_trends', 'naver_datalab', 'naver_ads']
                    제목: ['naver_news', 'google_news', 'naver_webdoc']
            keyword_limit: 키워드 최대 수집 수량 (기본 100, 최대 1000) - 일반 수집
            title_limit: 제목 최대 수집 수량 (None=무제한, 대량 수집용)
            enable_related_search: 연관 키워드 확장 여부 (기본 True)
            enable_normal_collect: 일반 수집 활성화 (기본 True)
            enable_bulk_collect: 대량 수집 활성화 (기본 False).
                DEPRECATED (Phase E, 2026-06-02): 대량 수집은 별도 모듈 타입
                ``bulk_collect`` 로 분리되었으며 본 인자는 레거시 호환을 위해
                유지된다. True 가 전달되면 ``logger.warning`` 으로 호출 사실을
                기록한다.
            bulk_collect_delay: 대량 수집 시 사이트 간 딜레이 (초). DEPRECATED.
            bulk_urls_per_cycle: 대량 수집 시 주기당 처리할 URL 수 (기본 3).
                DEPRECATED.
            module_id: 호출 모듈 ID(있을 때). DEPRECATED 로그에 식별자로 포함된다.

        Returns:
            수집 결과 요약
        """
        # 기본 소스 목록
        default_sources = [
            'google_trends', 'naver_datalab', 'naver_ads',
            'naver_news', 'google_news', 'naver_webdoc'
        ]

        if sources is None:
            sources = default_sources
        else:
            # 쇼핑인사이트 제거 (폐기됨)
            sources = [s for s in sources if s != 'naver_shopping_insight']

        # 수량 제한 검증 - keyword_limit만 적용 (10~1000)
        keyword_limit = max(10, min(1000, keyword_limit))
        # title_limit은 None이면 무제한, 값이 있으면 그대로 사용

        # ★ 수집 시작 시 캐시 초기화
        self._clear_filter_cache()
        await self._load_filters(force_reload=True)

        # ★ 카테고리 매칭 서비스 초기화
        self._init_category_matcher()

        # ★ 1차 중복 제거용 세션 캐시 초기화
        self._seen_keywords.clear()
        self._seen_titles.clear()

        logger.info(
            f"[COLLECTOR] 전체 수집 시작: sources={sources}, "
            f"keyword_limit={keyword_limit}, title_limit={'무제한' if not title_limit else title_limit}"
        )
        logger.info("[COLLECTOR] 1차 중복 제거 캐시 초기화 완료")

        results = {}
        total_collected = 0
        total_saved = 0

        # 키워드 소스 (SeedKeyword 테이블)
        keyword_source_list = ['google_trends', 'naver_datalab', 'naver_ads']
        # 제목 소스 (TempTitle 테이블)
        title_source_list = ['naver_news', 'google_news', 'naver_webdoc']

        # 활성 키워드 소스
        active_keyword_sources = [s for s in sources if s in keyword_source_list]
        # 활성 제목 소스
        active_title_sources = [s for s in sources if s in title_source_list]

        # 수집 유형 검증
        if not enable_normal_collect and not enable_bulk_collect:
            return {
                "success": False,
                "error": "최소 하나의 수집 유형을 선택해주세요 (일반 수집 또는 대량 수집)",
                "total_collected": 0,
                "total_saved": 0
            }

        if enable_normal_collect and not active_keyword_sources and not active_title_sources:
            return {
                "success": False,
                "error": "일반 수집을 위한 활성화된 수집 소스가 없습니다",
                "total_collected": 0,
                "total_saved": 0
            }

        # ====== 일반 수집 (enable_normal_collect가 True인 경우) ======
        # 키워드 소스별 수량 분배
        keyword_remaining = keyword_limit
        if enable_normal_collect and active_keyword_sources:
            per_keyword_source = keyword_limit // len(active_keyword_sources)

            # 구글 트렌드
            if 'google_trends' in sources and keyword_remaining > 0:
                source_limit = min(per_keyword_source, keyword_remaining)
                result = await self.collect_from_google_trends(limit=source_limit)
                results['google_trends'] = result
                total_collected += result.get('collected', 0)
                saved = result.get('saved', 0)
                total_saved += saved
                keyword_remaining -= saved

            # 네이버 데이터랩
            if 'naver_datalab' in sources and keyword_remaining > 0:
                source_limit = min(per_keyword_source, keyword_remaining)
                result = await self.collect_from_naver_datalab(limit=source_limit)
                results['naver_datalab'] = result
                total_collected += result.get('collected', 0)
                saved = result.get('saved', 0)
                total_saved += saved
                keyword_remaining -= saved

            # 네이버 광고 도구
            if 'naver_ads' in sources and keyword_remaining > 0:
                source_limit = min(per_keyword_source, keyword_remaining)
                # enable_related_search 옵션을 include_related 파라미터로 전달
                result = await self.collect_from_naver_ads(
                    limit=source_limit,
                    include_related=enable_related_search
                )
                results['naver_ads'] = result
                total_collected += result.get('collected', 0)
                saved = result.get('saved', 0)
                total_saved += saved
                keyword_remaining -= saved

        # 제목 수집: 키워드 기반 수집 → 직접 수집 (폴백) - 일반 수집일 때만
        title_remaining = title_limit
        if enable_normal_collect and active_title_sources:
            # 1. 키워드 기반 제목 수집 먼저 시도 (use_count 0~3 키워드 활용)
            has_keywords = await self.has_available_keywords()

            if has_keywords:
                logger.info("[COLLECTOR] 키워드 기반 제목 수집 시도...")
                keyword_result = await self.collect_titles_by_keywords(limit=title_limit)
                results['keyword_search'] = keyword_result

                if keyword_result.get('success'):
                    saved = keyword_result.get('saved', 0)
                    total_collected += keyword_result.get('collected', 0)
                    total_saved += saved
                    title_remaining -= saved
                    logger.info(f"[COLLECTOR] 키워드 기반 수집 성공: {saved}개 저장")

                    # 키워드 기반으로 충분히 수집했으면 직접 수집 스킵
                    if title_remaining <= 0:
                        logger.info("[COLLECTOR] 키워드 기반 수집으로 제목 수량 충족 - 직접 수집 스킵")
                        active_title_sources = []
            else:
                logger.info("[COLLECTOR] 사용 가능한 키워드 없음 - 직접 수집으로 진행")
                results['keyword_search'] = {
                    "success": False,
                    "source": "keyword_search",
                    "error": "사용 가능한 키워드 없음",
                    "collected": 0,
                    "saved": 0
                }

            # 2. 직접 수집 (폴백 또는 보충)
            # ★ 키워드 탭에 데이터가 없으면 랜덤 수집 모드 활성화
            use_random_mode = not has_keywords
            if use_random_mode:
                logger.info("[COLLECTOR] 🎲 랜덤 수집 모드 활성화 (키워드 탭 데이터 없음)")

            if active_title_sources and title_remaining > 0:
                per_title_source = title_remaining // len(active_title_sources)

                # 네이버 뉴스 (제목)
                if 'naver_news' in sources and title_remaining > 0:
                    source_limit = min(per_title_source, title_remaining)
                    result = await self.collect_from_naver_news(
                        limit=source_limit,
                        use_random=use_random_mode
                    )
                    results['naver_news'] = result
                    total_collected += result.get('collected', 0)
                    saved = result.get('saved', 0)
                    total_saved += saved
                    title_remaining -= saved

                # 구글 뉴스 RSS (제목)
                if 'google_news' in sources and title_remaining > 0:
                    source_limit = min(per_title_source, title_remaining)
                    result = await self.collect_from_google_news(
                        limit=source_limit,
                        use_random=use_random_mode
                    )
                    results['google_news'] = result
                    total_collected += result.get('collected', 0)
                    saved = result.get('saved', 0)
                    total_saved += saved
                    title_remaining -= saved

                # 네이버 웹문서 (제목)
                if 'naver_webdoc' in sources and title_remaining > 0:
                    source_limit = min(per_title_source, title_remaining)
                    result = await self.collect_from_naver_webdoc(
                        limit=source_limit,
                        use_random=use_random_mode
                    )
                    results['naver_webdoc'] = result
                    total_collected += result.get('collected', 0)
                    saved = result.get('saved', 0)
                    total_saved += saved
                    title_remaining -= saved

        # 일반 수집 완료 로그
        if enable_normal_collect:
            logger.info(
                f"[COLLECTOR] 일반 수집 완료: "
                f"총 {total_collected}개 수집, {total_saved}개 저장 "
                f"(키워드 제한: {keyword_limit}, 제목 제한: {title_limit})"
            )

        # ★ 대량 수집 실행 (enable_bulk_collect가 True인 경우)
        # DEPRECATED (Phase E, 2026-06-02):
        #     대량 수집은 별도 모듈 타입 ``bulk_collect`` 로 분리되었음.
        #     기존 collect 모듈의 enable_bulk_collect=True 옵션은 과도기 동안만
        #     동작을 유지한다 (옵션 C — 사용자 수동 마이그레이션 정책).
        #     사용자 마이그레이션 완료 후 별도 작업으로 이 분기 전체를 제거할
        #     예정이며, 호출 빈도를 운영자가 파악할 수 있도록 warning 로그를
        #     남긴다. 동작 자체는 변경하지 않는다.
        bulk_result = None
        if enable_bulk_collect:
            logger.warning(
                "[DEPRECATED:BULK_COLLECT] 레거시 collect 모듈의 대량 수집 분기 "
                "호출됨 | module_id=%s, urls_per_cycle=%s, delay=%s. "
                "새 bulk_collect 모듈로 마이그레이션 권장.",
                module_id,
                bulk_urls_per_cycle,
                bulk_collect_delay,
            )
            logger.info(
                f"[COLLECTOR] 🚀 대량 수집 시작 "
                f"(urls_per_cycle={bulk_urls_per_cycle}, max_titles_per_url=무제한)..."
            )
            bulk_result = await self.collect_bulk_titles(
                keywords=None,  # SeedKeyword에서 자동 조회
                delay_between_sites=bulk_collect_delay,
                urls_per_cycle=bulk_urls_per_cycle,
                max_titles_per_url=None,  # 대량 수집은 항상 무제한 (사이트맵 전체 크롤링)
                keyword_limit=keyword_limit  # 모듈 설정의 keyword_limit 적용
            )
            results['bulk_collect'] = bulk_result

            if bulk_result.get('success'):
                total_collected += bulk_result.get('collected', 0)
                total_saved += bulk_result.get('saved', 0)
                logger.info(
                    f"[COLLECTOR] 대량 수집 완료: "
                    f"{bulk_result.get('collected', 0)}개 수집, "
                    f"{bulk_result.get('saved', 0)}개 저장"
                )
            else:
                logger.warning(
                    f"[COLLECTOR] 대량 수집 실패: {bulk_result.get('error', '알 수 없는 오류')}"
                )

        # ★ 수집 완료 후 일괄 중복 제거 (2차 검증)
        dedup_result = await self._deduplicate_all()
        if dedup_result['keywords_removed'] > 0 or dedup_result['titles_removed'] > 0:
            logger.info(
                f"[COLLECTOR] 일괄 중복 제거 완료: "
                f"키워드 {dedup_result['keywords_removed']}개, "
                f"제목 {dedup_result['titles_removed']}개 제거"
            )
            results['deduplication'] = dedup_result

        return {
            "success": True,
            "results": results,
            "total_collected": total_collected,
            "total_saved": total_saved,
            "keywords_after_dedup": dedup_result.get('keywords_remaining', 0),
            "titles_after_dedup": dedup_result.get('titles_remaining', 0),
            "keyword_limit": keyword_limit,
            "title_limit": title_limit,
            "enable_normal_collect": enable_normal_collect,
            "enable_bulk_collect": enable_bulk_collect,
            "bulk_stats": bulk_result.get("stats", {}) if bulk_result else {},
            "collected_at": datetime.now().isoformat()
        }

    async def _save_keyword(
        self,
        keyword: str,
        source: str,
        search_volume: Optional[int] = None,
        competition: Optional[float] = None
    ) -> bool:
        """
        키워드를 SeedKeyword 테이블에 저장 (데이터 관리 페이지에 표시됨)

        1차 중복 제거:
        - 세션 내 캐시로 같은 수집에서 중복 방지
        - DB 조회로 기존 데이터와 중복 방지 (대소문자 무시)

        Args:
            keyword: 키워드
            source: 수집 소스 (source_type으로 저장)
            search_volume: 검색량 (미사용, 향후 확장용)
            competition: 경쟁도 (미사용, 향후 확장용)

        Returns:
            새로 저장되었으면 True, 필터에 걸리거나 중복이면 False
        """
        keyword = keyword.strip()
        if not keyword or len(keyword) < 2:
            return False

        # 정규화: 대소문자 무시를 위한 키
        keyword_lower = keyword.lower()

        # 1. 세션 내 중복 체크 (같은 수집에서 이미 처리됨)
        if keyword_lower in self._seen_keywords:
            logger.debug(f"[DEDUP-1] 세션 내 중복 키워드 스킵: '{keyword}'")
            return False

        # 2. 필터 체크 (키워드 타입)
        matched_filter = await self._check_filter(keyword, "keyword")
        if matched_filter:
            logger.info(
                f"[COLLECTOR] ❌ 키워드 필터링: '{keyword}' → "
                f"필터 '{matched_filter.filter_value}'"
            )
            return False

        # 3. DB 중복 체크 (대소문자 무시)
        from sqlalchemy import func
        query = select(SeedKeyword).where(
            func.lower(SeedKeyword.keyword) == keyword_lower
        ).limit(1)
        result = await self.db.execute(query)
        existing = result.scalars().first()

        if existing:
            # DB에 이미 존재 → 세션 캐시에 추가하고 스킵
            self._seen_keywords.add(keyword_lower)
            logger.debug(f"[DEDUP-1] DB 중복 키워드 스킵: '{keyword}'")
            return False

        # 4. 카테고리 매칭 (Topic > SubTopic > Keyword)
        topic_id, subtopic_id, matched_keyword_id = None, None, None
        try:
            if self._category_matcher:
                topic_id, subtopic_id, matched_keyword_id = await self._category_matcher.match_and_apply_to_keyword(keyword)
                if topic_id:
                    logger.debug(f"[CATEGORY] 키워드 카테고리 매칭: '{keyword}' → topic={topic_id}, subtopic={subtopic_id}")
        except Exception as cat_err:
            logger.warning(f"[CATEGORY] 키워드 카테고리 매칭 오류: {cat_err}")

        # 5. 새 키워드를 SeedKeyword 테이블에 저장
        new_keyword = SeedKeyword(
            keyword=keyword,
            source_type=source,
            is_active=True,
            use_count=0,
            priority=0,
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            matched_keyword_id=matched_keyword_id
        )
        self.db.add(new_keyword)

        # 6. 세션 캐시에 추가
        self._seen_keywords.add(keyword_lower)
        logger.debug(f"[DEDUP-1] 키워드 저장 및 캐시 추가: '{keyword}'")

        return True

    async def _save_title(
        self,
        title: str,
        source: str,
        source_url: str = "",
        category: str = ""
    ) -> bool:
        """
        뉴스 제목을 TempTitle 테이블에 저장

        1차 중복 제거:
        - 세션 내 캐시로 같은 수집에서 중복 방지
        - DB 조회로 기존 데이터와 중복 방지 (대소문자 무시)

        Args:
            title: 제목
            source: 수집 소스 (naver_news, google_news)
            source_url: 원본 URL
            category: 카테고리

        Returns:
            새로 저장되었으면 True, 필터에 걸리거나 중복이면 False
        """
        title = title.strip()
        if not title or len(title) < 10:
            return False

        # 정규화: 대소문자 무시를 위한 키
        title_lower = title.lower()

        # 1. 세션 내 중복 체크 (같은 수집에서 이미 처리됨)
        if title_lower in self._seen_titles:
            logger.debug(f"[DEDUP-1] 세션 내 중복 제목 스킵: '{title[:30]}...'")
            return False

        # 2. 필터 체크 (제목 타입)
        matched_filter = await self._check_filter(title, "title")
        if matched_filter:
            logger.info(
                f"[COLLECTOR] ❌ 제목 필터링: '{title[:30]}...' → "
                f"필터 '{matched_filter.filter_value}'"
            )
            return False

        # 3. DB 중복 체크 (대소문자 무시)
        from sqlalchemy import func
        query = select(TempTitle).where(
            func.lower(TempTitle.title) == title_lower
        ).limit(1)
        result = await self.db.execute(query)
        existing = result.scalars().first()

        if existing:
            # DB에 이미 존재 → 세션 캐시에 추가하고 스킵
            self._seen_titles.add(title_lower)
            logger.debug(f"[DEDUP-1] DB 중복 제목 스킵: '{title[:30]}...'")
            return False

        # 4. 카테고리 매칭 (Topic > SubTopic > Keyword)
        topic_id, subtopic_id, matched_keyword_id = None, None, None
        try:
            if self._category_matcher:
                topic_id, subtopic_id, matched_keyword_id = await self._category_matcher.match_and_apply_to_title(title)
                if topic_id:
                    logger.debug(f"[CATEGORY] 제목 카테고리 매칭: '{title[:30]}...' → topic={topic_id}, subtopic={subtopic_id}")
        except Exception as cat_err:
            logger.warning(f"[CATEGORY] 제목 카테고리 매칭 오류: {cat_err}")

        # 5. 새 제목을 TempTitle 테이블에 저장
        new_title = TempTitle(
            title=title,
            source_blog_url=source,
            source_post_url=source_url or source,
            collection_stage="news_collect",
            status="new",
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            matched_keyword_id=matched_keyword_id
        )
        self.db.add(new_title)

        # 5. 세션 캐시에 추가
        self._seen_titles.add(title_lower)
        logger.debug(f"[DEDUP-1] 제목 저장 및 캐시 추가: '{title[:30]}...'")

        return True

    def _parse_competition(self, comp_str: str) -> Optional[float]:
        """
        경쟁도 문자열을 숫자로 변환

        Args:
            comp_str: '높음', '중간', '낮음' 등

        Returns:
            0.0~1.0 사이 값
        """
        if not comp_str:
            return None

        comp_map = {
            "높음": 0.8,
            "중간": 0.5,
            "낮음": 0.2
        }
        return comp_map.get(comp_str, 0.5)

    async def _deduplicate_all(self) -> Dict[str, int]:
        """
        수집 완료 후 일괄 중복 제거 (2차 검증)

        키워드와 제목 테이블에서 중복된 항목을 찾아 제거합니다.
        동일 문자열이 여러 개 존재할 경우 가장 먼저 생성된 항목만 유지합니다.

        Returns:
            Dict with keys:
                - keywords_removed: 제거된 키워드 수
                - keywords_remaining: 남은 키워드 수
                - titles_removed: 제거된 제목 수
                - titles_remaining: 남은 제목 수
        """
        logger.info("[DEDUP-2] ========== 2차 중복 제거 시작 ==========")
        keywords_removed = 0
        titles_removed = 0

        try:
            # 1. 키워드 중복 제거
            keyword_query = select(SeedKeyword).order_by(SeedKeyword.created_at.asc())
            keyword_result = await self.db.execute(keyword_query)
            all_keywords = list(keyword_result.scalars().all())
            logger.info(f"[DEDUP-2] 키워드 중복 검사: 전체 {len(all_keywords)}개 스캔")

            seen_keywords: Dict[str, int] = {}  # keyword -> first_id
            keyword_ids_to_delete: List[int] = []

            for kw in all_keywords:
                kw_lower = kw.keyword.lower().strip()
                if kw_lower in seen_keywords:
                    # 중복 발견 - 삭제 대상
                    keyword_ids_to_delete.append(kw.id)
                    logger.info(f"[DEDUP-2] 중복 키워드 발견: '{kw.keyword}' (id={kw.id}, 원본 id={seen_keywords[kw_lower]})")
                else:
                    seen_keywords[kw_lower] = kw.id

            # 중복 키워드 삭제
            if keyword_ids_to_delete:
                from sqlalchemy import delete
                delete_stmt = delete(SeedKeyword).where(SeedKeyword.id.in_(keyword_ids_to_delete))
                await self.db.execute(delete_stmt)
                keywords_removed = len(keyword_ids_to_delete)
                logger.info(f"[DEDUP-2] ✅ 키워드 {keywords_removed}개 중복 제거 완료")
            else:
                logger.info("[DEDUP-2] 키워드 중복 없음")

            # 2. 제목 중복 제거
            title_query = select(TempTitle).order_by(TempTitle.created_at.asc())
            title_result = await self.db.execute(title_query)
            all_titles = list(title_result.scalars().all())
            logger.info(f"[DEDUP-2] 제목 중복 검사: 전체 {len(all_titles)}개 스캔")

            seen_titles: Dict[str, int] = {}  # title -> first_id
            title_ids_to_delete: List[int] = []

            for t in all_titles:
                t_lower = t.title.lower().strip()
                if t_lower in seen_titles:
                    # 중복 발견 - 삭제 대상
                    title_ids_to_delete.append(t.id)
                    logger.info(f"[DEDUP-2] 중복 제목 발견: '{t.title[:30]}...' (id={t.id}, 원본 id={seen_titles[t_lower]})")
                else:
                    seen_titles[t_lower] = t.id

            # 중복 제목 삭제
            if title_ids_to_delete:
                from sqlalchemy import delete
                delete_stmt = delete(TempTitle).where(TempTitle.id.in_(title_ids_to_delete))
                await self.db.execute(delete_stmt)
                titles_removed = len(title_ids_to_delete)
                logger.info(f"[DEDUP-2] ✅ 제목 {titles_removed}개 중복 제거 완료")
            else:
                logger.info("[DEDUP-2] 제목 중복 없음")

            # 커밋
            await self.db.commit()

            # 남은 개수 계산
            keywords_remaining = len(seen_keywords)
            titles_remaining = len(seen_titles)

            logger.info(
                f"[DEDUP-2] ========== 2차 중복 제거 완료 ==========\n"
                f"[DEDUP-2] 결과: 키워드 {keywords_removed}개 제거 → {keywords_remaining}개 유지\n"
                f"[DEDUP-2] 결과: 제목 {titles_removed}개 제거 → {titles_remaining}개 유지"
            )

            return {
                "keywords_removed": keywords_removed,
                "keywords_remaining": keywords_remaining,
                "titles_removed": titles_removed,
                "titles_remaining": titles_remaining
            }

        except Exception as e:
            logger.error(f"[DEDUP] 중복 제거 중 오류: {e}")
            await self.db.rollback()
            return {
                "keywords_removed": 0,
                "keywords_remaining": 0,
                "titles_removed": 0,
                "titles_remaining": 0,
                "error": str(e)
            }
