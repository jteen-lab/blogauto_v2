"""
크롤링 서비스

블로그 플랫폼 API를 통해 포스트 제목을 수집하고
CrawledPost 레코드로 저장합니다.

Features:
- WordPress REST API 포스트 크롤링
- Blogger API 포스트 크롤링 (API Key / OAuth 동적 인증)
- 배치 처리 및 증분 크롤링
- 에러 핸들링 및 재시도
"""
import os
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..models.blog import Blog, BlogPlatform
from ..models.crawled_post import CrawledPost
from ..core.security import decrypt_data
from ..core.logger import get_logger
from . import blogger_crawl_helper as bch

logger = get_logger("crawl_service", "crawl.log")


def _resolve_max_crawl_posts() -> int:
    """크롤링 최대 글 수 — 환경변수 MAX_CRAWL_POSTS로 조정 가능.

    기본 10000으로 상향. 500은 일반 블로그도 잘리는 너무 낮은 값.
    0 이하/잘못된 값은 기본값으로 fallback.
    """
    raw = os.getenv("MAX_CRAWL_POSTS", "10000").strip()
    try:
        v = int(raw)
        return v if v > 0 else 10000
    except (TypeError, ValueError):
        return 10000


@dataclass
class CrawledPostData:
    """크롤링된 포스트 데이터"""
    title: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass
class CrawlResult:
    """크롤링 결과"""
    success: bool
    crawled_count: int
    new_count: int
    error: Optional[str] = None
    is_new_blog: bool = False


class CrawlService:
    """크롤링 서비스"""

    # API 요청 설정
    REQUEST_TIMEOUT = 30.0
    MAX_POSTS_PER_REQUEST = 100
    # 환경변수 MAX_CRAWL_POSTS로 조정 (기본 10000). 707개 등 일반 블로그도
    # 잘리지 않도록 500 → 10000 상향. 매우 큰 블로그는 환경변수로 추가 확대.
    MAX_TOTAL_POSTS = _resolve_max_crawl_posts()

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def crawl_blog_posts(
        self,
        blog: Blog,
        incremental: bool = True
    ) -> CrawlResult:
        """
        블로그 포스트 크롤링

        Args:
            blog: 블로그 객체
            incremental: 증분 크롤링 여부 (마지막 크롤링 이후 포스트만)

        Returns:
            CrawlResult: 크롤링 결과
        """
        logger.info(f"크롤링 시작 | 블로그ID={blog.id} | 플랫폼={blog.platform.value}")

        try:
            # 플랫폼별 크롤링 실행
            if blog.platform == BlogPlatform.WORDPRESS:
                posts = await self._crawl_wordpress(blog, incremental)
            elif blog.platform == BlogPlatform.BLOGGER:
                posts = await self._crawl_blogger(blog, incremental)
            else:
                logger.warning(f"지원하지 않는 플랫폼 | 블로그ID={blog.id} | 플랫폼={blog.platform}")
                return CrawlResult(
                    success=False,
                    crawled_count=0,
                    new_count=0,
                    error="지원하지 않는 플랫폼입니다"
                )

            # 신규 블로그 여부 판단
            is_new_blog = len(posts) == 0

            # 크롤링 결과 저장
            new_count = await self._save_crawled_posts(blog.id, posts)

            # 블로그 상태 업데이트
            blog.last_crawled_at = datetime.now()
            blog.crawled_count = await self._get_total_crawled_count(blog.id)
            blog.is_new_blog = is_new_blog
            await self.db.commit()

            logger.info(f"크롤링 완료 | 블로그ID={blog.id} | 수집={len(posts)} | 신규={new_count}")

            return CrawlResult(
                success=True,
                crawled_count=len(posts),
                new_count=new_count,
                is_new_blog=is_new_blog
            )

        except Exception as e:
            logger.error(f"크롤링 실패 | 블로그ID={blog.id} | 오류={e}")
            return CrawlResult(
                success=False,
                crawled_count=0,
                new_count=0,
                error=str(e)
            )

    async def _crawl_wordpress(
        self,
        blog: Blog,
        incremental: bool = True
    ) -> List[CrawledPostData]:
        """
        WordPress REST API를 통한 포스트 크롤링

        WordPress REST API: GET /wp-json/wp/v2/posts
        """
        posts: List[CrawledPostData] = []
        page = 1
        base_url = blog.url.rstrip('/')

        # REST API 엔드포인트
        api_url = f"{base_url}/wp-json/wp/v2/posts"

        # 헤더 설정 (인증 필요 시)
        headers = await self._get_wordpress_headers(blog)

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            while len(posts) < self.MAX_TOTAL_POSTS:
                params = {
                    "per_page": self.MAX_POSTS_PER_REQUEST,
                    "page": page,
                    "status": "publish",
                    "_fields": "id,title,link,date"
                }

                # 증분 크롤링: 마지막 크롤링 이후 포스트만
                if incremental and blog.last_crawled_at:
                    params["after"] = blog.last_crawled_at.isoformat()

                try:
                    response = await client.get(api_url, params=params, headers=headers)

                    if response.status_code == 400:
                        # 페이지 끝
                        break

                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        break

                    for post in data:
                        title = post.get("title", {}).get("rendered", "")
                        if title:
                            posts.append(CrawledPostData(
                                title=self._clean_title(title),
                                url=post.get("link"),
                                published_at=self._parse_datetime(post.get("date"))
                            ))

                    # 다음 페이지 확인
                    total_pages = int(response.headers.get("X-WP-TotalPages", 1))
                    if page >= total_pages:
                        break

                    page += 1

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        logger.warning(f"WordPress 인증 실패 | 블로그ID={blog.id}")
                    raise

        return posts

    async def _crawl_blogger(
        self,
        blog: Blog,
        incremental: bool = True
    ) -> List[CrawledPostData]:
        """
        Blogger API를 통한 포스트 크롤링

        Blogger ID 획득 우선순위:
          1. blog.placeholders["blogger_id"] 캐시
          2. blog.api_key_encrypted가 숫자이면 직접 ID
          3. Google API Key로 blogs/byurl 호출
          4. OAuth Bearer Token으로 blogs/byurl 호출

        인증 방식:
          - API Key: ?key= 파라미터
          - OAuth: Authorization: Bearer 헤더
        """
        posts: List[CrawledPostData] = []

        # 인증 정보 획득
        api_key = bch.get_blogger_api_key(blog)
        oauth_token = await bch.get_blogger_oauth_token(blog, self.db)

        # 인증 수단이 하나도 없으면 조기 실패
        if not api_key and not oauth_token:
            logger.error(f"Blogger 인증 정보 없음 | 블로그ID={blog.id}")
            raise ValueError(
                "Blogger 인증 정보가 없습니다. "
                "API Key 또는 OAuth 토큰을 설정하세요."
            )

        # Blogger ID 획득 (강건한 다단계 탐색)
        blog_id, auth_method = await bch.resolve_blogger_id(
            blog, api_key, oauth_token
        )
        if not blog_id:
            raise ValueError(
                "Blogger 블로그 ID를 찾을 수 없습니다. "
                "API Key, OAuth 토큰, 또는 블로그 설정을 확인하세요."
            )

        # 인증 방식 결정 (ID 획득에 성공한 방식을 우선 사용)
        auth_params, auth_headers = bch.build_blogger_auth(
            api_key, oauth_token, auth_method=auth_method
        )

        api_url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts"
        page_token = None

        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            while len(posts) < self.MAX_TOTAL_POSTS:
                params: Dict[str, Any] = {
                    "maxResults": self.MAX_POSTS_PER_REQUEST,
                    "status": "live",
                    "fields": "items(id,title,url,published),nextPageToken",
                    **auth_params,
                }

                if page_token:
                    params["pageToken"] = page_token

                # 증분 크롤링
                if incremental and blog.last_crawled_at:
                    params["startDate"] = blog.last_crawled_at.isoformat()

                try:
                    response = await client.get(
                        api_url, params=params, headers=auth_headers
                    )
                    response.raise_for_status()
                    data = response.json()

                    items = data.get("items", [])
                    for post in items:
                        title = post.get("title", "")
                        if title:
                            posts.append(CrawledPostData(
                                title=self._clean_title(title),
                                url=post.get("url"),
                                published_at=self._parse_datetime(
                                    post.get("published")
                                )
                            ))

                    # 다음 페이지 토큰
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        logger.warning(
                            f"Blogger 인증 실패 | 블로그ID={blog.id}"
                        )
                    raise

        return posts

    async def _get_wordpress_headers(self, blog: Blog) -> Dict[str, str]:
        """WordPress API 헤더 생성"""
        headers = {"Accept": "application/json"}

        # Application Password 인증 (있는 경우)
        if blog.api_key_encrypted and blog.api_secret_encrypted:
            try:
                username = decrypt_data(blog.api_key_encrypted)
                app_password = decrypt_data(blog.api_secret_encrypted)
                import base64
                credentials = base64.b64encode(f"{username}:{app_password}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"
            except Exception as e:
                logger.warning(f"WordPress 인증 정보 복호화 실패 | 블로그ID={blog.id} | 오류={e}")

        return headers

    async def _save_crawled_posts(
        self,
        blog_id: int,
        posts: List[CrawledPostData]
    ) -> int:
        """
        크롤링된 포스트 저장

        Returns:
            int: 신규 저장된 포스트 수
        """
        new_count = 0

        for post_data in posts:
            # 중복 확인
            existing = await self.db.execute(
                select(CrawledPost).where(
                    and_(
                        CrawledPost.blog_id == blog_id,
                        CrawledPost.title == post_data.title
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue

            # 신규 포스트 저장
            crawled_post = CrawledPost(
                blog_id=blog_id,
                title=post_data.title,
                url=post_data.url,
                published_at=post_data.published_at,
                match_status="pending",
                source="crawled",
                crawled_at=datetime.now()
            )
            self.db.add(crawled_post)
            new_count += 1

        if new_count > 0:
            await self.db.commit()

        return new_count

    async def _get_total_crawled_count(self, blog_id: int) -> int:
        """블로그의 전체 크롤링 포스트 수 조회"""
        result = await self.db.execute(
            select(CrawledPost).where(CrawledPost.blog_id == blog_id)
        )
        return len(result.scalars().all())

    def _clean_title(self, title: str) -> str:
        """제목 정제 (HTML 엔티티 디코딩 등)"""
        import html
        cleaned = html.unescape(title)
        cleaned = cleaned.strip()
        return cleaned[:500] if len(cleaned) > 500 else cleaned

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not date_str:
            return None

        try:
            # ISO 8601 형식 파싱
            if "T" in date_str:
                # 타임존 정보 제거 (간단한 처리)
                date_str = date_str.split("+")[0].split("Z")[0]
                return datetime.fromisoformat(date_str)
            return None
        except Exception:
            return None

    async def get_crawled_posts(
        self,
        blog_id: int,
        match_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[CrawledPost], int]:
        """
        크롤링된 포스트 목록 조회

        Args:
            blog_id: 블로그 ID
            match_status: 매칭 상태 필터 (matched/unmatched/pending)
            limit: 조회 개수
            offset: 시작 위치

        Returns:
            (포스트 목록, 전체 개수)
        """
        query = select(CrawledPost).where(CrawledPost.blog_id == blog_id)

        if match_status:
            query = query.where(CrawledPost.match_status == match_status)

        query = query.order_by(CrawledPost.crawled_at.desc())

        # 전체 개수 조회
        count_result = await self.db.execute(query)
        total = len(count_result.scalars().all())

        # 페이지네이션 적용
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        posts = result.scalars().all()

        return list(posts), total
