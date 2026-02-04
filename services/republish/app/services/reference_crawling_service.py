"""
참조자료 크롤링 서비스

웹 문서를 크롤링하여 참조자료를 수집합니다.
핵심: 실패 시 다음 문서로 자동 이동하여 목표 개수(10개)를 달성합니다.

Features:
- 목표 개수 달성까지 자동 순회
- 같은 도메인 제한 (최대 2개)
- 차단 사이트 자동 스킵
- 모든 결과 DB 로깅
"""
import re
import time
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.collected_reference import CrawlLog
from ..schemas.reference_collection import CrawledDocument, CrawlResult

logger = logging.getLogger(__name__)


class ReferenceCrawlingService:
    """참조자료 크롤링 서비스"""

    # 설정값
    CRAWL_TIMEOUT = 10
    TARGET_COUNT = 10
    MIN_COUNT = 5
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 5000
    MAX_SAME_DOMAIN = 2

    # User-Agent
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

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

        documents: List[CrawledDocument] = []
        domain_counts: dict = {}
        total_attempted = 0
        total_failed = 0

        for url in urls:
            if len(documents) >= self.TARGET_COUNT:
                break

            total_attempted += 1
            domain = self._extract_domain(url)

            # 같은 도메인 제한 확인
            if domain_counts.get(domain, 0) >= self.MAX_SAME_DOMAIN:
                await self._log_crawl(reference_id, url, domain, "skipped", "같은 도메인 제한 초과")
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
                    content_length=doc.content_length, duration_ms=duration_ms
                )
            else:
                total_failed += 1
                await self._log_crawl(
                    reference_id, url, domain, error_status,
                    error_message=error_msg, duration_ms=duration_ms
                )

        has_minimum = len(documents) >= self.MIN_COUNT

        if not has_minimum:
            logger.warning(f"[CRAWL] 최소 개수 미달 | ref_id={reference_id} | count={len(documents)}")

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

    async def _crawl_single(
        self,
        url: str,
        domain: str
    ) -> tuple[Optional[CrawledDocument], str, Optional[str]]:
        """
        단일 URL 크롤링

        Args:
            url: 크롤링 URL
            domain: 도메인

        Returns:
            (CrawledDocument 또는 None, 상태코드, 에러메시지)
        """
        headers = {"User-Agent": self.USER_AGENT}

        try:
            async with httpx.AsyncClient(timeout=self.CRAWL_TIMEOUT) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)

                # 차단 응답 확인
                if response.status_code in (401, 403):
                    return None, "blocked", f"HTTP {response.status_code}"

                if response.status_code != 200:
                    return None, "failed", f"HTTP {response.status_code}"

                # 본문 추출
                content = self._extract_content(response.text)
                if not content:
                    return None, "failed", "본문 추출 실패"

                # 콘텐츠 검증
                if not self._validate_content(content):
                    return None, "failed", f"콘텐츠 길이 부족 ({len(content)}자)"

                # 제목 추출
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
        """
        HTML에서 본문 추출

        Args:
            html: HTML 문자열

        Returns:
            추출된 본문 또는 None
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 불필요한 요소 제거
            for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                            'aside', 'form', 'iframe', 'noscript']):
                tag.decompose()

            # 본문 영역 찾기 (우선순위)
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

            # 본문 영역 없으면 body 전체에서 추출
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

            # og:title 우선
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                return og_title['content'].strip()[:200]

            # title 태그
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
        if len(content) < self.MIN_CONTENT_LENGTH:
            return False
        return True

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
