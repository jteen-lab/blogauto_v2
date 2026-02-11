"""
참조자료 크롤링 서비스

웹 문서를 크롤링하여 참조자료를 수집합니다.
핵심: 실패 시 다음 문서로 자동 이동하여 목표 개수를 달성합니다.

Features:
- 사용자 설정 가능한 목표/최소 크롤링 수
- 같은 도메인 제한 (최대 2개)
- 블랙리스트 도메인 자동 스킵 및 등록
- 차단 사이트 자동 스킵
- 모든 결과 DB 로깅
"""
import re
import time
import logging
from datetime import datetime
from typing import List, Optional, Set
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.collected_reference import CrawlLog
from ..models.domain_blacklist import DomainBlacklist
from ..schemas.reference_collection import CrawledDocument, CrawlResult

logger = logging.getLogger(__name__)


class ReferenceCrawlingService:
    """참조자료 크롤링 서비스"""

    # 고정 설정값
    CRAWL_TIMEOUT = 10
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 5000
    MAX_SAME_DOMAIN = 2

    # User-Agent
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        db_session: AsyncSession,
        target_count: int = 10,
        min_count: int = 5
    ):
        """
        Args:
            db_session: DB 세션
            target_count: 크롤링 목표 수 (사용자 설정)
            min_count: 최소 필요 수
        """
        self.db = db_session
        self.TARGET_COUNT = max(1, target_count)
        self.MIN_COUNT = max(1, min(min_count, self.TARGET_COUNT))

    async def crawl_documents(
        self,
        urls: List[str],
        reference_id: int
    ) -> CrawlResult:
        """
        메인 크롤링 메서드

        Args:
            urls: 크롤링할 URL 목록
            reference_id: 참조자료 수집 ID (로그용)

        Returns:
            CrawlResult: 크롤링 결과
        """
        logger.info(f"[CRAWL] 시작 | ref_id={reference_id} | urls={len(urls)}")

        # 블랙리스트 도메인 사전 조회
        blacklisted = await self._get_blacklisted_domains()
        if blacklisted:
            logger.info(f"[CRAWL] 블랙리스트 도메인: {len(blacklisted)}개")

        documents: List[CrawledDocument] = []
        domain_counts: dict = {}
        total_attempted = 0
        total_failed = 0

        for url in urls:
            if len(documents) >= self.TARGET_COUNT:
                break

            total_attempted += 1
            domain = self._extract_domain(url)

            # 블랙리스트 도메인 스킵
            if domain in blacklisted:
                await self._log_crawl(
                    reference_id, url, domain,
                    "skipped", "블랙리스트 도메인"
                )
                continue

            # 같은 도메인 제한 확인
            if domain_counts.get(domain, 0) >= self.MAX_SAME_DOMAIN:
                await self._log_crawl(
                    reference_id, url, domain,
                    "skipped", "같은 도메인 제한 초과"
                )
                continue

            # 크롤링 시도
            start_time = time.time()
            doc, error_status, error_msg = await self._crawl_single(url, domain)
            duration_ms = int((time.time() - start_time) * 1000)

            if doc:
                documents.append(doc)
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                await self._log_crawl(
                    reference_id, url, domain, "success",
                    content_length=doc.content_length,
                    duration_ms=duration_ms
                )
            else:
                total_failed += 1
                await self._log_crawl(
                    reference_id, url, domain, error_status,
                    error_message=error_msg, duration_ms=duration_ms
                )
                # 본문 추출 실패 시 블랙리스트 등록
                if error_status in ("failed", "blocked", "timeout"):
                    await self._register_blacklist(domain, error_status)

        has_minimum = len(documents) >= self.MIN_COUNT

        if not has_minimum:
            logger.warning(
                f"[CRAWL] 최소 개수 미달 | ref_id={reference_id} | "
                f"count={len(documents)}"
            )

        logger.info(
            f"[CRAWL] 완료 | ref_id={reference_id} | "
            f"success={len(documents)} | failed={total_failed}"
        )

        return CrawlResult(
            total_attempted=total_attempted,
            total_success=len(documents),
            total_failed=total_failed,
            documents=documents,
            has_minimum=has_minimum
        )

    async def _get_blacklisted_domains(self) -> Set[str]:
        """블랙리스트 도메인 목록 조회"""
        try:
            result = await self.db.execute(
                select(DomainBlacklist.domain).where(
                    DomainBlacklist.is_active == True,
                    DomainBlacklist.fail_count >= DomainBlacklist.FAIL_THRESHOLD
                )
            )
            return set(result.scalars().all())
        except Exception as e:
            logger.warning(f"[CRAWL] 블랙리스트 조회 실패: {e}")
            return set()

    async def _register_blacklist(self, domain: str, reason: str) -> None:
        """실패 도메인 블랙리스트 등록/카운트 증가"""
        if not domain:
            return
        try:
            result = await self.db.execute(
                select(DomainBlacklist).where(
                    DomainBlacklist.domain == domain
                )
            )
            entry = result.scalar_one_or_none()
            if entry:
                entry.increment_fail(reason)
            else:
                self.db.add(DomainBlacklist(
                    domain=domain,
                    reason=reason,
                    last_failed_at=datetime.now()
                ))
            await self.db.flush()
        except Exception as e:
            logger.warning(f"[CRAWL] 블랙리스트 등록 실패: {e}")

    async def _crawl_single(
        self,
        url: str,
        domain: str
    ) -> tuple[Optional[CrawledDocument], str, Optional[str]]:
        """
        단일 URL 크롤링

        Returns:
            (CrawledDocument 또는 None, 상태코드, 에러메시지)
        """
        headers = {"User-Agent": self.USER_AGENT}

        try:
            async with httpx.AsyncClient(
                timeout=self.CRAWL_TIMEOUT
            ) as client:
                response = await client.get(
                    url, headers=headers, follow_redirects=True
                )

                if response.status_code in (401, 403):
                    return None, "blocked", f"HTTP {response.status_code}"

                if response.status_code != 200:
                    return None, "failed", f"HTTP {response.status_code}"

                content = self._extract_content(response.text)
                if not content:
                    return None, "failed", "본문 추출 실패"

                if not self._validate_content(content):
                    return None, "failed", f"콘텐츠 길이 부족 ({len(content)}자)"

                title = self._extract_title(response.text)

                doc = CrawledDocument(
                    url=url,
                    domain=domain,
                    title=title,
                    content=content[:self.MAX_CONTENT_LENGTH],
                    content_length=len(content),
                    crawled_at=datetime.now()
                )
                return doc, "success", None

        except httpx.TimeoutException:
            return None, "timeout", "요청 타임아웃"
        except Exception as e:
            return None, "failed", str(e)

    def _extract_content(self, html: str) -> Optional[str]:
        """HTML에서 본문 추출"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                            'aside', 'form', 'iframe', 'noscript']):
                tag.decompose()

            content_selectors = [
                'article', 'main', '.content', '.post-content',
                '.entry-content', '#content', '.article-body'
            ]

            for selector in content_selectors:
                content_area = soup.select_one(selector)
                if content_area:
                    text = content_area.get_text(separator=' ', strip=True)
                    if len(text) >= self.MIN_CONTENT_LENGTH:
                        return self._clean_text(text)

            body = soup.find('body')
            if body:
                text = body.get_text(separator=' ', strip=True)
                return self._clean_text(text) if text else None

            return None
        except Exception as e:
            logger.warning(f"[CRAWL] 본문 추출 실패: {e}")
            return None

    def _extract_title(self, html: str) -> Optional[str]:
        """HTML에서 제목 추출"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                return og_title['content'].strip()[:200]

            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                return title_tag.string.strip()[:200]

            return None
        except Exception:
            return None

    def _validate_content(self, content: str) -> bool:
        """콘텐츠 유효성 검증"""
        if not content:
            return False
        return len(content) >= self.MIN_CONTENT_LENGTH

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            parsed = urlparse(url)
            return parsed.netloc or ""
        except Exception:
            return ""

    def _clean_text(self, text: str) -> str:
        """텍스트 정제"""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    async def _log_crawl(
        self,
        reference_id: int,
        url: str,
        domain: str,
        status: str,
        error_message: Optional[str] = None,
        content_length: Optional[int] = None,
        duration_ms: Optional[int] = None
    ) -> None:
        """크롤링 로그 DB 저장"""
        try:
            log = CrawlLog(
                reference_id=reference_id,
                url=url,
                domain=domain,
                status=status,
                error_message=error_message,
                content_length=content_length,
                crawl_duration_ms=duration_ms
            )
            self.db.add(log)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"[CRAWL] 로그 저장 실패: {e}")
