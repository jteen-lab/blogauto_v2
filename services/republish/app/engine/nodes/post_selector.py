"""
노드: 포스트 선택 모듈

Features:
- 블로그 포스트 선택 (재발행용)
- 저장된 포스트 선택 (신규 발행용)
- 선택 기준: 가장 오래된 / 랜덤
- 최근 N일 제외 옵션
"""
import random
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("post_selector")


class PostSelector:
    """
    포스트 선택 노드

    블로그에서 발행할 포스트를 선택하거나,
    BlogAuto에 저장된 미발행 포스트를 선택합니다.
    """

    def __init__(
        self,
        db: AsyncSession,
        post_source: str = "blog_posts",
        selection_mode: str = "oldest",
        exclude_recent_days: int = 0
    ):
        """
        Args:
            db: 데이터베이스 세션
            post_source: 포스트 소스
                - "blog_posts": 블로그에 발행된 포스트 (재발행)
                - "saved_posts": BlogAuto에 저장된 미발행 포스트 (신규 발행)
            selection_mode: 선택 기준
                - "oldest": 가장 오래된 포스트
                - "random": 랜덤 추출
            exclude_recent_days: 최근 N일 이내 포스트 제외 (0=제외 없음)
        """
        self.db = db
        self.post_source = post_source
        self.selection_mode = selection_mode
        self.exclude_recent_days = exclude_recent_days

        self._wordpress_api = None
        self._blogger_api = None

    @property
    def wordpress_api(self):
        """WordPress API 지연 로딩"""
        if self._wordpress_api is None:
            from ...services.wordpress_api import WordPressAPI
            self._wordpress_api = WordPressAPI()
        return self._wordpress_api

    @property
    def blogger_service(self):
        """Blogger 서비스 지연 로딩"""
        if self._blogger_api is None:
            from ...services.blogger_service import BloggerRepublishService
            self._blogger_api = BloggerRepublishService()
        return self._blogger_api

    async def execute(
        self,
        classified_blogs: list[dict[str, Any]],
        module_settings: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        포스트 선택 실행

        Args:
            classified_blogs: 분류된 블로그 목록 (StatusClassifier 출력)
            module_settings: 모듈별 설정 (선택)

        Returns:
            PostSelectorOutput 형식의 딕셔너리
        """
        logger.info(
            f"[POST_SELECTOR] 시작 | 블로그 수={len(classified_blogs)} | "
            f"소스={self.post_source} | 모드={self.selection_mode}"
        )

        # 모듈 설정 오버라이드
        if module_settings:
            self.post_source = module_settings.get("post_source", self.post_source)
            self.selection_mode = module_settings.get("selection_mode", self.selection_mode)
            self.exclude_recent_days = module_settings.get("exclude_recent_days", self.exclude_recent_days)

        selected_posts = []
        skipped_count = 0

        # 적격 블로그만 처리
        eligible_blogs = [b for b in classified_blogs if b.get("is_eligible", True)]

        for blog_data in eligible_blogs:
            blog = blog_data.get("blog", blog_data)

            try:
                if self.post_source == "blog_posts":
                    # 블로그 포스트 선택 (재발행)
                    result = await self._select_from_blog(blog)
                else:
                    # 저장된 포스트 선택 (신규 발행)
                    result = await self._select_from_saved(blog)

                if result:
                    selected_posts.append(result)
                else:
                    skipped_count += 1

            except Exception as e:
                logger.error(
                    f"[POST_SELECTOR] 포스트 선택 실패 | "
                    f"BlogID={blog.get('id')} | Error={e}"
                )
                skipped_count += 1

        logger.info(
            f"[POST_SELECTOR] 완료 | 선택={len(selected_posts)} | "
            f"스킵={skipped_count}"
        )

        return {
            "selected_posts": selected_posts,
            "selection_summary": {
                "total_blogs": len(eligible_blogs),
                "selected": len(selected_posts),
                "skipped": skipped_count,
                "post_source": self.post_source,
                "selection_mode": self.selection_mode
            }
        }

    async def _select_from_blog(self, blog: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        블로그에서 포스트 선택 (재발행용)

        Args:
            blog: 블로그 정보

        Returns:
            선택된 포스트 정보 또는 None
        """
        blog_id = blog.get("id")
        platform = blog.get("platform", "").lower()

        logger.debug(f"[POST_SELECTOR] 블로그 포스트 조회 | BlogID={blog_id} | Platform={platform}")

        try:
            # 블로그 모델 조회
            blog_obj = await self._get_blog_model(blog_id)
            if not blog_obj:
                logger.warning(f"[POST_SELECTOR] 블로그 모델 없음 | BlogID={blog_id}")
                return None

            # 플랫폼별 분기
            if platform == "wordpress":
                post = await self._get_wordpress_post(blog_obj)
            elif platform == "blogger":
                post = await self._get_blogger_post(blog_obj, blog.get("credential_id"))
            else:
                logger.warning(f"[POST_SELECTOR] 지원하지 않는 플랫폼 | Platform={platform}")
                return None

            if not post:
                return None

            # 최근 N일 제외 체크
            if self.exclude_recent_days > 0:
                post_date = self._parse_date(post.get("date") or post.get("published"))
                if post_date and self._is_recent(post_date):
                    logger.info(
                        f"[POST_SELECTOR] 최근 포스트 제외 | BlogID={blog_id} | "
                        f"PostDate={post_date}"
                    )
                    return None

            return {
                "blog_id": blog_id,
                "blog_name": blog.get("name", "Unknown"),
                "platform": platform,
                "post_id": post.get("id"),
                "post_title": post.get("title", ""),
                "post_date": post.get("date") or post.get("published"),
                "post_url": post.get("link") or post.get("url"),
                "source": "blog_posts",
                "profile": blog.get("profile"),
                "credential_id": blog.get("credential_id")
            }

        except Exception as e:
            logger.error(f"[POST_SELECTOR] 블로그 포스트 조회 실패 | BlogID={blog_id} | Error={e}")
            return None

    async def _get_wordpress_post(self, blog_obj) -> Optional[dict[str, Any]]:
        """WordPress 포스트 조회"""
        try:
            if self.selection_mode == "oldest":
                # 오래된 순으로 1개 조회
                url = self.wordpress_api._get_api_url(
                    blog_obj,
                    "posts?per_page=1&orderby=date&order=asc&status=publish"
                )
            else:
                # 랜덤: 전체 조회 후 무작위 선택 (최대 100개)
                url = self.wordpress_api._get_api_url(
                    blog_obj,
                    "posts?per_page=100&orderby=date&order=asc&status=publish"
                )

            headers = self.wordpress_api._get_auth_headers(blog_obj)
            result = await self.wordpress_api._make_request("GET", url, headers)
            posts = result["data"]

            if not posts:
                return None

            if self.selection_mode == "random" and len(posts) > 1:
                post = random.choice(posts)
            else:
                post = posts[0]

            return {
                "id": str(post["id"]),
                "title": post.get("title", {}).get("rendered", ""),
                "date": post.get("date", ""),
                "link": post.get("link", "")
            }

        except Exception as e:
            logger.error(f"[POST_SELECTOR] WordPress 포스트 조회 실패 | Error={e}")
            return None

    async def _get_blogger_post(
        self,
        blog_obj,
        credential_id: Optional[int]
    ) -> Optional[dict[str, Any]]:
        """Blogger 포스트 조회"""
        try:
            if not credential_id:
                logger.warning("[POST_SELECTOR] Blogger 인증 정보 없음")
                return None

            credential = await self._get_credential(credential_id)
            if not credential:
                return None

            # 블로그 ID 조회
            blogger_id = await self.blogger_service.get_blog_id(blog_obj, credential)

            # 포스트 조회
            headers = self.blogger_service._get_auth_headers(credential)

            if self.selection_mode == "oldest":
                url = f"https://www.googleapis.com/blogger/v3/blogs/{blogger_id}/posts?maxResults=1&orderBy=published"
            else:
                url = f"https://www.googleapis.com/blogger/v3/blogs/{blogger_id}/posts?maxResults=100&orderBy=published"

            result = await self.blogger_service._make_request("GET", url, headers)
            posts = result.get("items", [])

            if not posts:
                return None

            if self.selection_mode == "random" and len(posts) > 1:
                post = random.choice(posts)
            else:
                post = posts[0]

            return {
                "id": post["id"],
                "title": post.get("title", ""),
                "published": post.get("published", ""),
                "url": post.get("url", "")
            }

        except Exception as e:
            logger.error(f"[POST_SELECTOR] Blogger 포스트 조회 실패 | Error={e}")
            return None

    async def _select_from_saved(self, blog: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        저장된 포스트에서 선택 (신규 발행용)

        Args:
            blog: 블로그 정보

        Returns:
            선택된 포스트 정보 또는 None
        """
        blog_id = blog.get("id")
        logger.debug(f"[POST_SELECTOR] 저장된 포스트 조회 | BlogID={blog_id}")

        # TODO: 저장된 포스트 테이블이 구현되면 여기에 로직 추가
        # 현재는 placeholder로 None 반환
        logger.warning(f"[POST_SELECTOR] 저장된 포스트 기능 미구현 | BlogID={blog_id}")
        return None

    async def _get_blog_model(self, blog_id: int):
        """블로그 모델 조회"""
        from ...models.blog import Blog

        query = select(Blog).where(Blog.id == blog_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_credential(self, credential_id: int):
        """Google 인증 정보 조회"""
        from ...models.google_credential import GoogleCredential

        query = select(GoogleCredential).where(GoogleCredential.id == credential_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not date_str:
            return None

        try:
            # ISO 8601 형식 파싱 시도
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _is_recent(self, post_date: datetime) -> bool:
        """최근 N일 이내인지 확인"""
        if not post_date:
            return False

        cutoff = datetime.now() - timedelta(days=self.exclude_recent_days)

        # timezone-aware 비교
        if post_date.tzinfo:
            from datetime import timezone
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        return post_date > cutoff


async def create_post_selector(
    db: AsyncSession,
    post_source: str = "blog_posts",
    selection_mode: str = "oldest",
    exclude_recent_days: int = 0
) -> PostSelector:
    """
    PostSelector 인스턴스 생성 팩토리 함수

    Args:
        db: 데이터베이스 세션
        post_source: 포스트 소스 ("blog_posts" | "saved_posts")
        selection_mode: 선택 기준 ("oldest" | "random")
        exclude_recent_days: 최근 N일 제외

    Returns:
        PostSelector 인스턴스
    """
    return PostSelector(db, post_source, selection_mode, exclude_recent_days)
