"""
대량 제목 수집 서비스 (2단계 분리 방식) — LEGACY

수집 주기마다 효율적으로 URL과 제목을 분리 수집합니다.

수집 프로세스 (2단계):
[Phase 1] URL 수집 및 저장
  1. 키워드 20개로 네이버 블로그 검색
  2. 검색 결과에서 블로그/사이트 URL 추출
  3. CollectedUrl 테이블에 저장 (중복 방지)
  4. 도메인 필터 적용

[Phase 2] 제목 수집 (1~3개 URL만)
  1. CollectedUrl에서 미처리 URL 1~3개 조회
  2. 해당 URL에서 제목 수집
  3. TempTitle 테이블에 저장
  4. URL을 처리 완료 표시

장점:
- 수집 시간 단축 (한 번에 1~3개 URL만 처리)
- URL 축적 → 점진적 제목 수집
- 관리 용이 (URL 상태 추적 가능)

------------------------------------------------------------------
DEPRECATED (Phase B-2026-06-02):
    이 파일은 `keyword_collector_service` 호환을 위해 보존된다.
    신규 코드는 `app.services.bulk_collect` 패키지의
    ChunkProcessor / DomainLimiter / LastmodTracker / Timebox 와
    `app.services.url_classifier.URLClassifier` 를 사용해야 한다.
    사이트맵/제목 추출 공용 로직은 `app.services.bulk_collect.sitemap_parser`
    로 이동했다. Phase E 에서 이 파일은 thin wrapper 로 정리될 예정.
------------------------------------------------------------------
"""
import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models.user_settings import UserSettings
from ..models.content_filter import ContentFilter
from ..models.collected_url import CollectedUrl

logger = logging.getLogger("keyword_collector")


class BulkTitleCollectorService:
    """대량 제목 수집 서비스 (2단계 분리 방식)"""

    # RSS 피드 URL 패턴
    RSS_PATTERNS = {
        "tistory": "/rss",
        "wordpress": "/feed",
        "blogger": "/feeds/posts/default",
        "naver": None,  # API 사용
    }

    # 수집 설정
    DEFAULT_URLS_PER_CYCLE = 3  # 주기당 처리할 URL 수
    # MAX_TITLES_PER_URL 제거 - 제한 없음 (사이트맵의 모든 URL 수집)

    def __init__(
        self,
        db: AsyncSession,
        settings: UserSettings,
        filters: Optional[List[ContentFilter]] = None
    ):
        """
        Args:
            db: 데이터베이스 세션
            settings: 사용자 설정 (API 키 포함)
            filters: 콘텐츠 필터 목록 (도메인 필터 적용용)
        """
        self.db = db
        self.settings = settings
        self.filters = filters or []
        self._filtered_domains: Set[str] = set()

    # =========================================================================
    # Phase 1: URL 수집 및 저장
    # =========================================================================

    async def collect_urls(
        self,
        keywords: List[str],
        max_urls_per_keyword: int = 100
    ) -> Dict[str, Any]:
        """
        Phase 1: 키워드로 검색하여 URL 수집 및 저장.

        DEPRECATED (Phase E, 2026-06-02):
            본 메서드는 레거시 ``keyword_collector_service`` 의 호환 경로에서만
            호출된다. 신규 코드는 ``app.services.bulk_collect`` 패키지의
            ``ChunkProcessor`` / ``DomainLimiter`` / ``LastmodTracker`` /
            ``Timebox`` 와 ``app.services.url_classifier.URLClassifier`` 를
            사용해야 한다. 동작은 호환 유지를 위해 그대로 두지만, 신규 기능
            확장은 금지한다.

        Args:
            keywords: 검색 키워드 목록 (최대 20개)
            max_urls_per_keyword: 키워드당 최대 URL 수

        Returns:
            수집 결과
        """
        if not keywords:
            return {
                "success": False,
                "error": "키워드가 필요합니다",
                "urls_found": 0,
                "urls_saved": 0
            }

        # 네이버 검색 API 확인
        if not self.settings.naver_search_client_id:
            return {
                "success": False,
                "error": "네이버 검색 API 키가 설정되지 않았습니다",
                "urls_found": 0,
                "urls_saved": 0
            }

        logger.info(f"[BULK_COLLECTOR] Phase 1: URL 수집 시작 (키워드 {len(keywords)}개)")

        headers = {
            "X-Naver-Client-Id": self.settings.naver_search_client_id,
            "X-Naver-Client-Secret": self.settings.naver_search_client_secret
        }

        stats = {
            "total_keywords": len(keywords),
            "urls_found": 0,
            "urls_saved": 0,
            "urls_filtered": 0,
            "urls_duplicate": 0,
            "platforms": {}
        }

        # 이번 수집에서 이미 추가된 도메인 추적 (중복 방지).
        # DEPRECATED (Phase E): 레거시 "도메인 단위 1회만 적재" 정책.
        # 신규 bulk_collect 모듈은 사용 안 함 (사이트맵 기반 청크 수집으로 대체).
        added_domains: Set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for keyword in keywords:
                    # 키워드로 블로그 검색
                    response = await client.get(
                        "https://openapi.naver.com/v1/search/blog.json",
                        headers=headers,
                        params={
                            "query": keyword,
                            "display": min(100, max_urls_per_keyword),
                            "sort": "date"
                        }
                    )

                    if response.status_code != 200:
                        logger.warning(f"[BULK_COLLECTOR] 키워드 '{keyword}' 검색 실패: {response.status_code}")
                        continue

                    data = response.json()
                    items = data.get("items", [])

                    logger.info(f"[BULK_COLLECTOR] 키워드 '{keyword}': {len(items)}개 결과")

                    # 검색 결과에서 URL 추출 및 저장
                    for item in items:
                        link = item.get("link", "")
                        blogger_link = item.get("bloggerlink", "")
                        search_title = item.get("title", "")

                        # 도메인 추출
                        domain = self._extract_blog_domain(blogger_link or link)
                        if not domain:
                            continue

                        stats["urls_found"] += 1

                        # 도메인 필터 체크
                        if self._check_domain_filter(domain):
                            stats["urls_filtered"] += 1
                            self._filtered_domains.add(domain)
                            continue

                        # 플랫폼 판별
                        platform = self._detect_platform(blogger_link or link)
                        stats["platforms"][platform] = stats["platforms"].get(platform, 0) + 1

                        # 이번 수집에서 이미 추가된 도메인인지 확인
                        if domain in added_domains:
                            stats["urls_duplicate"] += 1
                            continue

                        # DB에 저장 (중복 시 스킵)
                        saved = await self._save_url(
                            url=blogger_link or link,
                            domain=domain,
                            platform=platform,
                            search_keyword=keyword,
                            search_title=self._clean_title(search_title)
                        )

                        if saved:
                            stats["urls_saved"] += 1
                            added_domains.add(domain)  # 저장 성공 시 추적
                        else:
                            stats["urls_duplicate"] += 1

                    # 키워드 간 딜레이
                    await asyncio.sleep(0.1)

            await self.db.commit()

            logger.info(
                f"[BULK_COLLECTOR] Phase 1 완료: "
                f"발견 {stats['urls_found']}개, 저장 {stats['urls_saved']}개, "
                f"필터링 {stats['urls_filtered']}개, 중복 {stats['urls_duplicate']}개"
            )

            return {
                "success": True,
                "phase": "url_collect",
                **stats
            }

        except Exception as e:
            logger.error(f"[BULK_COLLECTOR] URL 수집 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                **stats
            }

    async def _save_url(
        self,
        url: str,
        domain: str,
        platform: str,
        search_keyword: str,
        search_title: str
    ) -> bool:
        """
        URL을 CollectedUrl 테이블에 저장 (중복 시 스킵)

        중복 체크 키: (url, source_module_id IS NULL)
            - alembic 042에서 UNIQUE 제약이 (domain) → (url, source_module_id)로 변경됨
            - 레거시 호출자(keyword_collector_service)는 모듈 ID 없이 적재하므로
              source_module_id=NULL인 row끼리만 url 단위 중복 체크 수행
            - NULL끼리는 NULLS DISTINCT(기본)라 DB UNIQUE가 안 걸리므로
              애플리케이션 레벨에서 명시적으로 중복 차단해야 함

        Returns:
            True면 새로 저장됨, False면 이미 존재
        """
        try:
            # 이미 존재하는지 확인 (url + source_module_id IS NULL 조합)
            existing = await self.db.execute(
                select(CollectedUrl)
                .where(CollectedUrl.url == url)
                .where(CollectedUrl.source_module_id.is_(None))
            )
            if existing.scalars().first():
                logger.debug(f"[BULK_COLLECTOR] 중복 URL 스킵: {url}")
                return False

            # 새 URL 저장 (source_module_id=None: 레거시 적재 경로)
            new_url = CollectedUrl(
                url=url,
                domain=domain,
                platform=platform,
                search_keyword=search_keyword,
                search_title=search_title,
                source_module_id=None,
                is_processed=False,
                is_active=True
            )
            self.db.add(new_url)
            return True

        except Exception as e:
            # IntegrityError (중복) 등의 예외 발생 시 세션 상태 복구
            await self.db.rollback()
            logger.warning(f"[BULK_COLLECTOR] URL 저장 오류 ({url}): {e}")
            return False

    # =========================================================================
    # Phase 2: 제목 수집 (1~3개 URL만)
    # =========================================================================

    async def collect_titles_from_urls(
        self,
        urls_per_cycle: int = 3,
        delay_between_sites: float = 0.5,
        max_titles_per_url: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Phase 2: 저장된 URL에서 제목 수집 (1~3개만)

        Args:
            urls_per_cycle: 한 주기에 처리할 URL 수 (기본 3개)
            delay_between_sites: 사이트 간 딜레이 (초)
            max_titles_per_url: URL당 최대 제목 수집 수 (None=무제한)

        Returns:
            수집 결과
        """
        logger.info(f"[BULK_COLLECTOR] Phase 2: 제목 수집 시작 (URL {urls_per_cycle}개)")

        # 미처리 URL 조회 (is_processed=False, is_active=True)
        urls_query = (
            select(CollectedUrl)
            .where(CollectedUrl.is_processed == False)
            .where(CollectedUrl.is_active == True)
            .order_by(CollectedUrl.created_at.asc())  # 오래된 것부터
            .limit(urls_per_cycle)
        )
        result = await self.db.execute(urls_query)
        urls_to_process = list(result.scalars().all())

        if not urls_to_process:
            logger.info("[BULK_COLLECTOR] 처리할 URL이 없습니다")
            return {
                "success": True,
                "phase": "title_collect",
                "urls_processed": 0,
                "titles_collected": 0,
                "message": "처리할 URL이 없습니다"
            }

        logger.info(f"[BULK_COLLECTOR] {len(urls_to_process)}개 URL 처리 예정")

        stats = {
            "urls_processed": 0,
            "urls_success": 0,
            "urls_failed": 0,
            "titles_collected": 0,
            "platforms": {}
        }

        all_titles = []

        for url_obj in urls_to_process:
            try:
                logger.info(f"[BULK_COLLECTOR] 처리 중: {url_obj.platform}:{url_obj.domain}")

                # 제목 수집
                titles = await self._collect_from_site(
                    blog_domain=url_obj.domain,
                    platform=url_obj.platform,
                    original_url=url_obj.url,
                    max_titles=max_titles_per_url
                )

                if titles:
                    all_titles.extend(titles)
                    stats["titles_collected"] += len(titles)
                    stats["urls_success"] += 1
                    stats["platforms"][url_obj.platform] = (
                        stats["platforms"].get(url_obj.platform, 0) + len(titles)
                    )

                    # URL 처리 완료 표시
                    url_obj.mark_processed(titles_count=len(titles))

                    logger.info(
                        f"[BULK_COLLECTOR] {url_obj.domain} → {len(titles)}개 제목 수집"
                    )
                else:
                    # 제목을 가져오지 못한 경우도 처리 완료로 표시
                    url_obj.mark_processed(titles_count=0)
                    logger.warning(f"[BULK_COLLECTOR] {url_obj.domain}: 제목 없음")

                stats["urls_processed"] += 1

            except Exception as e:
                logger.error(f"[BULK_COLLECTOR] {url_obj.domain} 처리 오류: {e}")
                url_obj.mark_error(str(e))
                stats["urls_failed"] += 1
                stats["urls_processed"] += 1

            # 사이트 간 딜레이
            await asyncio.sleep(delay_between_sites)

        await self.db.commit()

        logger.info(
            f"[BULK_COLLECTOR] Phase 2 완료: "
            f"URL {stats['urls_processed']}개 처리, "
            f"제목 {stats['titles_collected']}개 수집"
        )

        return {
            "success": True,
            "phase": "title_collect",
            "titles": all_titles,
            **stats
        }

    # =========================================================================
    # 통합 수집 (Phase 1 + Phase 2)
    # =========================================================================

    async def collect_bulk_titles(
        self,
        keywords: List[str],
        delay_between_sites: float = 0.5,
        urls_per_cycle: int = 3,
        max_titles_per_url: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        대량 제목 수집 (2단계 통합)

        1. Phase 1: 키워드로 URL 수집 및 저장
        2. Phase 2: 저장된 URL 중 1~3개에서 제목 수집

        Args:
            keywords: 검색 키워드 목록
            delay_between_sites: 사이트 간 딜레이 (초)
            urls_per_cycle: 주기당 처리할 URL 수
            max_titles_per_url: URL당 최대 제목 수집 수 (None=무제한)

        Returns:
            수집 결과
        """
        if not keywords:
            return {
                "success": False,
                "error": "키워드가 필요합니다",
                "titles": [],
                "stats": {}
            }

        logger.info(f"[BULK_COLLECTOR] 대량 수집 시작 (2단계 방식)")

        # Phase 1: URL 수집
        phase1_result = await self.collect_urls(keywords)

        if not phase1_result.get("success"):
            return {
                "success": False,
                "error": phase1_result.get("error", "URL 수집 실패"),
                "titles": [],
                "stats": {"phase1": phase1_result}
            }

        # Phase 2: 제목 수집 (1~3개 URL만)
        phase2_result = await self.collect_titles_from_urls(
            urls_per_cycle=urls_per_cycle,
            delay_between_sites=delay_between_sites,
            max_titles_per_url=max_titles_per_url
        )

        # 결과 통합
        titles = phase2_result.get("titles", [])

        # 중복 제목 제거
        seen_titles = set()
        unique_titles = []
        for title_data in titles:
            title = title_data.get("title", "")
            if title not in seen_titles:
                seen_titles.add(title)
                unique_titles.append(title_data)

        stats = {
            "phase1_urls_saved": phase1_result.get("urls_saved", 0),
            "phase1_urls_filtered": phase1_result.get("urls_filtered", 0),
            "phase2_urls_processed": phase2_result.get("urls_processed", 0),
            "total_titles": len(unique_titles),
            "duplicates_removed": len(titles) - len(unique_titles),
            "platforms": phase2_result.get("platforms", {})
        }

        logger.info(
            f"[BULK_COLLECTOR] 대량 수집 완료: "
            f"URL {stats['phase1_urls_saved']}개 저장, "
            f"{stats['phase2_urls_processed']}개 처리, "
            f"제목 {stats['total_titles']}개 수집"
        )

        return {
            "success": True,
            "titles": unique_titles,
            "stats": stats,
            "filtered_domains": list(self._filtered_domains)
        }

    # =========================================================================
    # URL 상태 관리
    # =========================================================================

    async def get_url_stats(self) -> Dict[str, Any]:
        """URL 수집 상태 통계 조회"""
        from sqlalchemy import func

        # 전체 URL 수
        total_query = select(func.count()).select_from(CollectedUrl)
        total = (await self.db.execute(total_query)).scalar() or 0

        # 처리 완료 URL 수
        processed_query = (
            select(func.count())
            .select_from(CollectedUrl)
            .where(CollectedUrl.is_processed == True)
        )
        processed = (await self.db.execute(processed_query)).scalar() or 0

        # 미처리 URL 수
        pending_query = (
            select(func.count())
            .select_from(CollectedUrl)
            .where(CollectedUrl.is_processed == False)
            .where(CollectedUrl.is_active == True)
        )
        pending = (await self.db.execute(pending_query)).scalar() or 0

        # 비활성화된 URL 수 (에러 3회 이상)
        inactive_query = (
            select(func.count())
            .select_from(CollectedUrl)
            .where(CollectedUrl.is_active == False)
        )
        inactive = (await self.db.execute(inactive_query)).scalar() or 0

        # 플랫폼별 통계
        platform_query = (
            select(CollectedUrl.platform, func.count())
            .group_by(CollectedUrl.platform)
        )
        platform_result = await self.db.execute(platform_query)
        platforms = {row[0]: row[1] for row in platform_result.fetchall()}

        return {
            "total": total,
            "processed": processed,
            "pending": pending,
            "inactive": inactive,
            "platforms": platforms
        }

    async def reset_processed_urls(self, older_than_days: int = 7) -> int:
        """
        오래된 처리 완료 URL을 재수집 대상으로 전환

        Args:
            older_than_days: N일 이전에 처리된 URL만 대상

        Returns:
            초기화된 URL 수
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=older_than_days)

        result = await self.db.execute(
            update(CollectedUrl)
            .where(CollectedUrl.is_processed == True)
            .where(CollectedUrl.last_processed_at < cutoff_date)
            .values(is_processed=False, error_count=0, last_error=None)
        )

        await self.db.commit()
        count = result.rowcount

        logger.info(f"[BULK_COLLECTOR] {count}개 URL 재수집 대상으로 전환")
        return count

    # =========================================================================
    # 유틸리티 메서드
    # =========================================================================

    def _detect_platform(self, url: str) -> str:
        """URL에서 플랫폼 판별"""
        url_lower = url.lower()

        if "tistory.com" in url_lower:
            return "tistory"
        elif "blog.naver.com" in url_lower:
            return "naver"
        elif "blogspot.com" in url_lower or "blogger.com" in url_lower:
            return "blogger"
        elif "wordpress.com" in url_lower:
            return "wordpress"
        else:
            return "unknown"

    def _extract_blog_domain(self, url: str) -> Optional[str]:
        """URL에서 블로그 도메인 추출"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc

            # 네이버 블로그는 path에서 username 추출
            if "blog.naver.com" in domain:
                path_parts = parsed.path.strip("/").split("/")
                if path_parts and path_parts[0]:
                    return f"blog.naver.com/{path_parts[0]}"
                return None

            return domain

        except Exception:
            return None

    def _check_domain_filter(self, url: str) -> bool:
        """도메인 필터 체크 (True면 차단됨)"""
        if not self.filters:
            return False

        url_lower = url.lower()

        for filter_obj in self.filters:
            if not filter_obj.is_active:
                continue

            filter_type = (filter_obj.filter_type or "").lower().strip()
            if filter_type != "domain":
                continue

            filter_value = (filter_obj.filter_value or "").lower().strip()
            if filter_value and filter_value in url_lower:
                logger.info(f"[BULK_COLLECTOR] 도메인 필터링: {url} (필터: {filter_value})")
                return True

        return False

    async def _collect_from_site(
        self,
        blog_domain: str,
        platform: str,
        original_url: str,
        max_titles: Optional[int] = None,
        crawl_delay: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        사이트에서 전체 포스트 제목 수집 (사이트맵 기반)

        Args:
            blog_domain: 블로그 도메인
            platform: 플랫폼 (tistory, naver, blogger, wordpress 등)
            original_url: 원본 URL
            max_titles: 최대 제목 수집 수 (None=무제한)
            crawl_delay: 사이트맵 크롤링 시 딜레이 (초)

        Returns:
            수집된 제목 목록
        """
        titles = []

        if platform == "naver":
            # 네이버는 사이트맵 없음 - API 사용
            if "/" in blog_domain:
                blogger_id = blog_domain.split("/")[-1]
                titles = await self._collect_from_naver_blog(blogger_id, max_titles=max_titles)
        else:
            # 모든 플랫폼: 사이트맵 기반 크롤링 (RSS 폐기)
            titles = await self._fetch_sitemap_titles(
                blog_domain, max_titles=max_titles, crawl_delay=crawl_delay
            )

        # 소스 정보 추가
        for title_data in titles:
            title_data["blog_domain"] = blog_domain
            title_data["platform"] = platform

        return titles

    async def _fetch_rss_titles(
        self,
        rss_url: str,
        max_titles: int = 100
    ) -> List[Dict[str, Any]]:
        """RSS 피드에서 제목 수집"""
        titles = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(rss_url)

                if response.status_code != 200:
                    return []

                content = response.text

                # RSS/Atom 제목 파싱
                title_pattern = re.compile(
                    r'<title[^>]*>(?:<!\[CDATA\[)?(.+?)(?:\]\]>)?</title>',
                    re.IGNORECASE | re.DOTALL
                )
                matches = title_pattern.findall(content)

                # 첫 번째는 피드 제목이므로 제외
                for title in matches[1:max_titles + 1]:
                    title = self._clean_title(title)
                    if title and len(title) >= 5:
                        titles.append({
                            "title": title,
                            "source": "bulk_rss",
                            "rss_url": rss_url
                        })

        except Exception as e:
            logger.warning(f"[BULK_COLLECTOR] RSS 파싱 오류: {rss_url} - {e}")

        return titles

    async def _collect_from_naver_blog(
        self,
        blogger_id: str,
        max_titles: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """네이버 블로그에서 제목 수집 (API 기반, 페이지네이션으로 전체 수집)"""
        if not self.settings.naver_search_client_id:
            return []

        titles = []
        headers = {
            "X-Naver-Client-Id": self.settings.naver_search_client_id,
            "X-Naver-Client-Secret": self.settings.naver_search_client_secret
        }

        query = f"site:blog.naver.com/{blogger_id}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start = 1
                display = 100  # API 최대값

                while True:
                    response = await client.get(
                        "https://openapi.naver.com/v1/search/blog.json",
                        headers=headers,
                        params={
                            "query": query,
                            "display": display,
                            "start": start,
                            "sort": "date"
                        }
                    )

                    if response.status_code != 200:
                        break

                    data = response.json()
                    items = data.get("items", [])

                    if not items:
                        break

                    for item in items:
                        title = item.get("title", "")
                        title = self._clean_title(title)

                        if title and len(title) >= 5:
                            titles.append({
                                "title": title,
                                "source": "bulk_naver_blog",
                                "link": item.get("link", ""),
                                "blogger_id": blogger_id
                            })

                    # max_titles 지정 시 제한 체크
                    if max_titles and len(titles) >= max_titles:
                        titles = titles[:max_titles]
                        break

                    # 다음 페이지
                    total = data.get("total", 0)
                    start += display

                    # API 제한: start + display <= 1000
                    if start > 1000 or start > total:
                        break

                    await asyncio.sleep(0.1)  # API 부하 방지

        except Exception as e:
            logger.warning(f"[BULK_COLLECTOR] 네이버 블로그 수집 오류: {blogger_id} - {e}")

        return titles

    def _clean_title(self, title: str) -> str:
        """HTML 태그 및 특수문자 정리"""
        title = re.sub(r'<[^>]+>', '', title)
        title = title.replace("&quot;", '"')
        title = title.replace("&amp;", "&")
        title = title.replace("&lt;", "<")
        title = title.replace("&gt;", ">")
        title = title.replace("&apos;", "'")
        title = title.replace("&#39;", "'")
        title = title.replace("<![CDATA[", "").replace("]]>", "")
        title = re.sub(r'\s+', ' ', title)
        return title.strip()

    # =========================================================================
    # 사이트맵 기반 크롤링 (전체 포스트 수집)
    # =========================================================================

    async def _fetch_sitemap_titles(
        self,
        blog_domain: str,
        max_titles: Optional[int] = None,
        crawl_delay: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        사이트맵에서 전체 포스트 URL 추출 후 제목 크롤링

        Args:
            blog_domain: 블로그 도메인
            max_titles: 최대 제목 수집 수 (None=무제한, 사이트맵의 모든 URL)
            crawl_delay: URL 간 크롤링 딜레이 (초)

        Returns:
            수집된 제목 목록
        """
        titles = []

        try:
            # 1. 사이트맵에서 포스트 URL 추출 (무제한)
            post_urls = await self._extract_urls_from_sitemap(blog_domain, max_urls=max_titles)

            if not post_urls:
                logger.info(f"[SITEMAP] {blog_domain}: 사이트맵에서 URL을 찾을 수 없음")
                return []

            logger.info(f"[SITEMAP] {blog_domain}: {len(post_urls)}개 URL 발견")

            # 2. 각 URL에서 제목 크롤링 (제한 없음)
            for url in post_urls:
                title = await self._fetch_title_from_url(url)
                if title and len(title) >= 5:
                    titles.append({
                        "title": title,
                        "source": "bulk_sitemap",
                        "link": url
                    })

                # max_titles 지정 시 제한 체크
                if max_titles and len(titles) >= max_titles:
                    break

                # 크롤링 딜레이
                await asyncio.sleep(crawl_delay)

            logger.info(f"[SITEMAP] {blog_domain}: {len(titles)}개 제목 수집 완료")

        except Exception as e:
            logger.warning(f"[SITEMAP] {blog_domain} 크롤링 오류: {e}")

        return titles

    async def _extract_urls_from_sitemap(
        self,
        blog_domain: str,
        max_urls: Optional[int] = None
    ) -> List[str]:
        """
        사이트맵에서 포스트 URL 추출 (인덱스 사이트맵 지원)

        Args:
            blog_domain: 블로그 도메인
            max_urls: 최대 URL 수 (None=무제한)

        Returns:
            포스트 URL 목록
        """
        urls = []
        sitemap_url = f"https://{blog_domain}/sitemap.xml"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(sitemap_url)

                if response.status_code != 200:
                    return []

                content = response.text

                # 사이트맵 인덱스인지 확인 (하위 사이트맵 링크 포함)
                if "<sitemapindex" in content:
                    urls = await self._parse_sitemap_index(client, content, max_urls)
                else:
                    urls = self._parse_sitemap_urls(content, max_urls)

        except Exception as e:
            logger.warning(f"[SITEMAP] 사이트맵 파싱 오류: {sitemap_url} - {e}")

        return urls

    async def _parse_sitemap_index(
        self,
        client: httpx.AsyncClient,
        content: str,
        max_urls: Optional[int] = None
    ) -> List[str]:
        """사이트맵 인덱스에서 하위 사이트맵 파싱 (무제한 지원)"""
        urls = []

        # 하위 사이트맵 URL 추출
        sitemap_pattern = re.compile(r'<loc>([^<]+)</loc>', re.IGNORECASE)
        sub_sitemaps = sitemap_pattern.findall(content)

        # posts 관련 사이트맵 우선, 없으면 전체 사용
        post_sitemaps = [s for s in sub_sitemaps if 'post' in s.lower()]
        if not post_sitemaps:
            post_sitemaps = sub_sitemaps  # 전체 사이트맵 사용 (제한 없음)

        for sitemap_loc in post_sitemaps:
            # max_urls 지정 시 제한 체크
            if max_urls and len(urls) >= max_urls:
                break

            try:
                response = await client.get(sitemap_loc)
                if response.status_code == 200:
                    remaining = None if not max_urls else max_urls - len(urls)
                    sub_urls = self._parse_sitemap_urls(response.text, remaining)
                    urls.extend(sub_urls)
                await asyncio.sleep(0.1)
            except Exception:
                continue

        return urls if not max_urls else urls[:max_urls]

    def _parse_sitemap_urls(self, content: str, max_urls: Optional[int] = None) -> List[str]:
        """사이트맵 XML에서 URL 추출 (무제한 지원)"""
        urls = []

        # <loc> 태그에서 URL 추출
        loc_pattern = re.compile(r'<loc>([^<]+)</loc>', re.IGNORECASE)
        matches = loc_pattern.findall(content)

        for url in matches:
            # 포스트 URL만 필터링 (숫자 ID 포함된 URL)
            if re.search(r'/\d+$', url) or '/entry/' in url or '/post/' in url:
                urls.append(url)
                # max_urls 지정 시 제한 체크
                if max_urls and len(urls) >= max_urls:
                    break

        return urls

    async def _fetch_title_from_url(self, url: str) -> Optional[str]:
        """개별 URL에서 제목 추출"""
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    return None

                content = response.text

                # <title> 태그에서 제목 추출
                title_match = re.search(
                    r'<title[^>]*>([^<]+)</title>',
                    content,
                    re.IGNORECASE
                )

                if title_match:
                    title = self._clean_title(title_match.group(1))
                    # 사이트 이름 제거 (예: " - 블로그명")
                    title = re.sub(r'\s*[-|]\s*[^-|]+$', '', title)
                    return title.strip()

        except Exception:
            pass

        return None
