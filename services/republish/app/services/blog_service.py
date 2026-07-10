"""
블로그 비즈니스 로직

Features:
- 블로그 CRUD 작업
- API 키 암호화/복호화
- 플랫폼별 연결 테스트
- 보안 이벤트 로깅
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..models.blog import Blog, BlogPlatform
from ..models.user import User
from ..schemas.blog import (
    BlogCreateRequest,
    BlogUpdateRequest,
    BlogResponse,
    BlogListResponse,
    BlogConnectionTestResponse,
    BlogStatsResponse
)
from ..core.security import encrypt_data, decrypt_data
from ..core.logger import get_logger, log_security_event
from .crawl_service import CrawlService
from .similarity_matcher_service import SimilarityMatcherService
from ..models.action_log import ActionLog

logger = get_logger("blog_service", "blog.log")


async def add_action_log(
    db: AsyncSession,
    level: str,
    message: str,
    category: str = None,
    resource_type: str = None,
    resource_id: int = None
):
    """동작 로그 추가 헬퍼"""
    try:
        log = ActionLog(
            level=level,
            message=message,
            category=category,
            resource_type=resource_type,
            resource_id=resource_id
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.warning(f"동작 로그 저장 실패: {e}")


class BlogService:
    """블로그 서비스 클래스"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_blog(self, user: User, request: BlogCreateRequest) -> BlogResponse:
        """
        블로그 등록

        Args:
            user: 사용자 객체
            request: 블로그 등록 요청

        Returns:
            생성된 블로그 정보

        Raises:
            HTTPException: 등록 실패시
        """
        logger.info(f"블로그 등록 시도 | 사용자={user.id} | 이름={request.name} | 플랫폼={request.platform}")

        # 중복 URL 확인
        await self._check_duplicate_url(user.id, str(request.url))

        try:
            # 자동화 지원 여부 결정
            is_auto_supported = request.platform != BlogPlatform.OTHER

            # API 키 암호화
            api_key_encrypted = await self._encrypt_api_credential(
                request.api_key, "api_key"
            ) if request.api_key else None

            api_secret_encrypted = await self._encrypt_api_credential(
                request.api_secret, "api_secret"
            ) if request.api_secret else None

            oauth_token_encrypted = await self._encrypt_api_credential(
                request.oauth_token, "oauth_token"
            ) if request.oauth_token else None

            # 블로그 객체 생성
            blog = Blog(
                user_id=user.id,
                name=request.name,
                url=str(request.url),
                platform=request.platform,
                is_auto_supported=is_auto_supported,
                api_key_encrypted=api_key_encrypted,
                api_secret_encrypted=api_secret_encrypted,
                oauth_token_encrypted=oauth_token_encrypted,
                auto_publish=request.auto_publish and is_auto_supported,
                republish_interval_hours=request.republish_interval_hours,
                daily_limit=request.daily_limit,
                editor_type=request.editor_type,
                css_classes=request.css_classes
            )

            self.db.add(blog)
            await self.db.commit()
            await self.db.refresh(blog)

            logger.info(f"블로그 등록 완료 | 블로그ID={blog.id} | 사용자={user.id}")

            return BlogResponse(**blog.to_dict())

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 등록 실패 | 사용자={user.id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 등록 중 오류가 발생했습니다"
            )

    async def get_user_blogs(self, user: User, include_deleted: bool = False) -> List[BlogListResponse]:
        """
        사용자 블로그 목록 조회

        카드 카운트 의미 (사용자 의도와 정식제목 탭과의 일관성):
          - crawled_count: 블로그에 실제 발행된 모든 글 수
            = CrawledPost(blog_id).published_at IS NOT NULL
            = 정식제목 탭 [발행완료] + [미매칭] 합과 일치
          - matched_count: 그 중 정식제목과 매칭된 발행글 수
            = match_status='matched' AND published_at IS NOT NULL

        blogs.crawled_count/matched_count 캐시 컬럼은 generator/matcher가
        시점에 따라 갱신하지 않아 stale → 응답 시점에 실시간 SQL COUNT로 보강.

        Args:
            user: 사용자 객체
            include_deleted: 삭제된 블로그 포함 여부

        Returns:
            블로그 목록 (crawled/matched 실시간 발행 기준)
        """
        from ..models.crawled_post import CrawledPost
        from sqlalchemy import func as _func

        query = select(Blog).where(Blog.user_id == user.id)

        if not include_deleted:
            query = query.where(Blog.is_deleted == False)

        query = query.order_by(Blog.created_at.desc())

        result = await self.db.execute(query)
        blogs = result.scalars().all()

        # 실시간 카운트 일괄 조회 (N+1 방지)
        # published_at IS NOT NULL을 "블로그 실제 발행" 기준으로 사용
        blog_ids = [b.id for b in blogs]
        counts: dict[int, dict] = {}
        if blog_ids:
            count_q = (
                select(
                    CrawledPost.blog_id,
                    _func.count(CrawledPost.id).filter(
                        CrawledPost.published_at.isnot(None)
                    ).label("published_total"),
                    _func.count(CrawledPost.id).filter(
                        CrawledPost.published_at.isnot(None),
                        CrawledPost.match_status == "matched",
                    ).label("matched_published"),
                )
                .where(CrawledPost.blog_id.in_(blog_ids))
                .group_by(CrawledPost.blog_id)
            )
            for row in (await self.db.execute(count_q)).all():
                counts[row.blog_id] = {
                    "published_total": row.published_total or 0,
                    "matched_published": row.matched_published or 0,
                }

        logger.info(f"블로그 목록 조회 | 사용자={user.id} | 개수={len(blogs)}")

        items = []
        for blog in blogs:
            d = blog.to_dict()
            c = counts.get(blog.id) or {"published_total": 0, "matched_published": 0}
            d["crawled_count"] = c["published_total"]
            d["matched_count"] = c["matched_published"]
            # GP 구간 분류용 total_post_count 보강:
            # 저장된 total_post_count가 0/누락이면 DB의 published count를
            # fallback으로 사용. 사용자가 sync 안 눌렀어도 GP 분류 가능.
            stored_total = blog.total_post_count or 0
            db_published = c["published_total"]
            d["total_post_count"] = max(stored_total, db_published)
            items.append(BlogListResponse(**d))
        return items

    async def get_user_blogs_with_credentials(self, user: User) -> List[dict]:
        """
        사용자 블로그 목록 조회 (복호화된 인증정보 포함)

        crawled_count/matched_count는 published_at IS NOT NULL 기준으로
        실시간 SQL COUNT 보강 (blog_service.get_user_blogs와 동일 의미).

        Args:
            user: 사용자 객체

        Returns:
            블로그 목록 (인증정보 포함, 실시간 카운트 반영)
        """
        from ..models.crawled_post import CrawledPost
        from sqlalchemy import func as _func

        query = select(Blog).where(
            Blog.user_id == user.id,
            Blog.is_deleted == False
        ).order_by(Blog.created_at.desc())

        result = await self.db.execute(query)
        blogs = result.scalars().all()

        # 실시간 발행 카운트 일괄 조회 (N+1 방지, 의미는 get_user_blogs와 동일)
        blog_ids = [b.id for b in blogs]
        counts: dict[int, dict] = {}
        if blog_ids:
            count_q = (
                select(
                    CrawledPost.blog_id,
                    _func.count(CrawledPost.id).filter(
                        CrawledPost.published_at.isnot(None)
                    ).label("published_total"),
                    _func.count(CrawledPost.id).filter(
                        CrawledPost.published_at.isnot(None),
                        CrawledPost.match_status == "matched",
                    ).label("matched_published"),
                )
                .where(CrawledPost.blog_id.in_(blog_ids))
                .group_by(CrawledPost.blog_id)
            )
            for row in (await self.db.execute(count_q)).all():
                counts[row.blog_id] = {
                    "published_total": row.published_total or 0,
                    "matched_published": row.matched_published or 0,
                }

        logger.info(f"블로그 목록 조회 (인증정보 포함) | 사용자={user.id} | 개수={len(blogs)}")

        items = []
        for blog in blogs:
            d = blog.to_dict_with_credentials(decrypt_data)
            c = counts.get(blog.id) or {"published_total": 0, "matched_published": 0}
            d["crawled_count"] = c["published_total"]
            d["matched_count"] = c["matched_published"]
            items.append(d)
        return items

    async def get_blog_by_id(self, user: User, blog_id: int) -> BlogResponse:
        """
        블로그 상세 조회

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            블로그 상세 정보

        Raises:
            HTTPException: 블로그를 찾을 수 없는 경우
        """
        blog = await self._get_user_blog(user, blog_id)
        return BlogResponse(**blog.to_dict())

    async def update_blog(self, user: User, blog_id: int, request: BlogUpdateRequest) -> BlogResponse:
        """
        블로그 정보 수정

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID
            request: 수정 요청

        Returns:
            수정된 블로그 정보
        """
        blog = await self._get_user_blog(user, blog_id)

        logger.info(f"블로그 수정 시도 | 블로그ID={blog_id} | 사용자={user.id}")

        try:
            # 변경된 필드 추적
            changed_fields = []

            # 기본 정보 업데이트
            if request.name is not None:
                blog.name = request.name
                changed_fields.append("name")

            if request.url is not None:
                blog.url = str(request.url)
                changed_fields.append("url")

            # API 키 업데이트 (값이 제공되고 빈 문자열이 아닌 경우만)
            if request.api_key is not None and request.api_key.strip():
                blog.api_key_encrypted = await self._encrypt_api_credential(
                    request.api_key, "api_key"
                )
                changed_fields.append("api_key")

            if request.api_secret is not None and request.api_secret.strip():
                blog.api_secret_encrypted = await self._encrypt_api_credential(
                    request.api_secret, "api_secret"
                )
                changed_fields.append("api_secret")

            if request.oauth_token is not None and request.oauth_token.strip():
                blog.oauth_token_encrypted = await self._encrypt_api_credential(
                    request.oauth_token, "oauth_token"
                )
                changed_fields.append("oauth_token")

            # 발행 설정 업데이트
            if request.auto_publish is not None:
                blog.auto_publish = request.auto_publish and blog.is_auto_supported
                changed_fields.append("auto_publish")

            if request.republish_interval_hours is not None:
                blog.republish_interval_hours = request.republish_interval_hours
                changed_fields.append("republish_interval_hours")

            if request.daily_limit is not None:
                blog.daily_limit = request.daily_limit
                changed_fields.append("daily_limit")

            if request.editor_type is not None:
                blog.editor_type = request.editor_type
                changed_fields.append("editor_type")

            if request.css_classes is not None:
                blog.css_classes = request.css_classes
                changed_fields.append("css_classes")

            await self.db.commit()
            await self.db.refresh(blog)

            logger.info(f"블로그 수정 완료 | 블로그ID={blog_id} | 변경필드={changed_fields}")

            return BlogResponse(**blog.to_dict())

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 수정 실패 | 블로그ID={blog_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 수정 중 오류가 발생했습니다"
            )

    async def delete_blog(self, user: User, blog_id: int) -> dict:
        """
        블로그 완전 삭제(하드 삭제).

        blog 및 blog_id로 연결된 모든 데이터를 DB에서 제거한다(소프트삭제 잔재 방지).
        FK가 NO ACTION인 테이블(카테고리/프로필링크/발행전략/posts/publish_logs)은
        blogs 삭제 전 먼저 지우고, 나머지(crawled_posts/generation_histories/
        flow_blogs/module_blogs 등)는 blogs 삭제 시 DB의 ON DELETE CASCADE로 자동
        정리된다(task_executions는 SET NULL). 되돌릴 수 없음.

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            삭제 결과
        """
        from sqlalchemy import text

        # blog_id FK가 NO ACTION이라 blogs 삭제 전 반드시 선삭제해야 하는 테이블.
        # (나머지 blog_id 참조 테이블은 FK가 CASCADE/SET NULL이라 자동 처리)
        preclean_tables = (
            "blog_categories", "blog_profile_links", "blog_publish_strategies",
            "posts", "publish_logs",
        )

        blog = await self._get_user_blog(user, blog_id)
        blog_name = blog.name

        logger.info(f"블로그 완전삭제 시도 | 블로그ID={blog_id} | 사용자={user.id}")

        try:
            # ORM identity map과 직접 SQL 삭제 충돌 방지를 위해 세션에서 분리
            self.db.expunge(blog)

            # 1) NO ACTION FK 테이블 선삭제 (테이블명은 고정 상수 → 인젝션 없음)
            for table in preclean_tables:
                await self.db.execute(
                    text(f"DELETE FROM {table} WHERE blog_id = :bid"), {"bid": blog_id}
                )
            # 2) blogs 삭제 → 나머지 관련 테이블 CASCADE/SET NULL 자동 정리
            await self.db.execute(text("DELETE FROM blogs WHERE id = :bid"), {"bid": blog_id})
            await self.db.commit()

            logger.info(f"블로그 완전삭제 완료 | 블로그ID={blog_id} | 이름={blog_name}")

            return {"message": f"블로그 '{blog_name}'이(가) 완전히 삭제되었습니다"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"블로그 삭제 실패 | 블로그ID={blog_id} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="블로그 삭제 중 오류가 발생했습니다"
            )

    async def test_blog_connection(self, user: User, blog_id: int) -> BlogConnectionTestResponse:
        """
        블로그 API 연결 테스트

        Args:
            user: 사용자 객체
            blog_id: 블로그 ID

        Returns:
            연결 테스트 결과
        """
        blog = await self._get_user_blog(user, blog_id)

        logger.info(f"블로그 연결 테스트 시도 | 블로그ID={blog_id}")

        if not blog.is_auto_supported:
            return BlogConnectionTestResponse(
                success=False,
                message="자동화를 지원하지 않는 플랫폼입니다",
                details={"platform": blog.platform.value}
            )

        if not blog.has_api_credentials:
            return BlogConnectionTestResponse(
                success=False,
                message="API 인증 정보가 설정되지 않았습니다",
                details={"missing_credentials": True}
            )

        # 실제 API 연결 테스트는 Phase 4에서 구현 예정
        # 현재는 기본적인 검증만 수행
        test_result = await self._perform_connection_test(blog)

        logger.info(f"블로그 연결 테스트 완료 | 블로그ID={blog_id} | 결과={test_result['success']}")

        return BlogConnectionTestResponse(**test_result)

    async def get_user_blog_stats(self, user: User) -> BlogStatsResponse:
        """
        사용자 블로그 통계 조회

        Args:
            user: 사용자 객체

        Returns:
            블로그 통계
        """
        query = select(Blog).where(
            and_(Blog.user_id == user.id, Blog.is_deleted == False)
        )

        result = await self.db.execute(query)
        blogs = result.scalars().all()

        total_blogs = len(blogs)
        active_blogs = sum(1 for blog in blogs if blog.is_active)
        auto_publish_enabled = sum(1 for blog in blogs if blog.auto_publish)

        # 플랫폼별 통계
        by_platform = {}
        for blog in blogs:
            platform = blog.platform.value
            by_platform[platform] = by_platform.get(platform, 0) + 1

        return BlogStatsResponse(
            total_blogs=total_blogs,
            active_blogs=active_blogs,
            auto_publish_enabled=auto_publish_enabled,
            by_platform=by_platform
        )

    async def _check_duplicate_url(self, user_id: int, url: str) -> None:
        """URL 중복 확인"""
        query = select(Blog).where(
            and_(
                Blog.user_id == user_id,
                Blog.url == url,
                Blog.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        existing_blog = result.scalar_one_or_none()

        if existing_blog:
            logger.warning(f"URL 중복 | 사용자={user_id} | URL={url}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 등록된 블로그 URL입니다"
            )

    async def _get_user_blog(self, user: User, blog_id: int) -> Blog:
        """사용자 블로그 조회"""
        query = select(Blog).where(
            and_(
                Blog.id == blog_id,
                Blog.user_id == user.id,
                Blog.is_deleted == False
            )
        )

        result = await self.db.execute(query)
        blog = result.scalar_one_or_none()

        if not blog:
            logger.warning(f"블로그 없음 | 블로그ID={blog_id} | 사용자={user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="블로그를 찾을 수 없습니다"
            )

        return blog

    async def _encrypt_api_credential(self, value: str, field_name: str) -> str:
        """API 인증 정보 암호화"""
        try:
            encrypted_value = encrypt_data(value)

            # 보안 로그 (값은 마스킹)
            masked_value = "****" + value[-4:] if len(value) > 4 else "****"
            log_security_event(logger, "API_KEY_ENCRYPTED", {
                "field": field_name,
                "masked_value": masked_value
            })

            return encrypted_value

        except Exception as e:
            logger.error(f"암호화 실패 | 필드={field_name} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="암호화 처리 중 오류가 발생했습니다"
            )

    async def _perform_connection_test(self, blog: Blog) -> Dict[str, Any]:
        """
        연결 테스트 및 크롤링/매칭 수행

        Phase M-1: 연결테스트 시 크롤링 + 백그라운드 매칭
        1. API 연결 확인
        2. 포스트 타이틀 크롤링
        3. 기존 블로그인 경우 백그라운드 매칭 시작
        """
        # 기본적인 설정 확인
        if blog.platform == BlogPlatform.WORDPRESS:
            if not blog.api_key_encrypted or not blog.api_secret_encrypted:
                return {
                    "success": False,
                    "message": "WordPress API 키와 시크릿이 모두 필요합니다",
                    "details": {"platform": "wordpress", "missing_auth": True},
                    "crawled_count": 0,
                    "is_new_blog": True,
                    "matching_started": False
                }

        elif blog.platform == BlogPlatform.BLOGGER:
            if not blog.api_key_encrypted:
                return {
                    "success": False,
                    "message": "Blogger API 키가 필요합니다",
                    "details": {"platform": "blogger", "missing_api_key": True},
                    "crawled_count": 0,
                    "is_new_blog": True,
                    "matching_started": False
                }

        # 블로그 상태를 크롤링 중으로 변경
        blog.crawl_status = "crawling"
        await self.db.commit()

        try:
            # 1. 포스트 크롤링 실행
            crawl_service = CrawlService(self.db)
            crawl_result = await crawl_service.crawl_blog_posts(blog, incremental=False)

            if not crawl_result.success:
                blog.crawl_status = "error"
                await self.db.commit()
                return {
                    "success": False,
                    "message": f"크롤링 실패: {crawl_result.error}",
                    "details": {"platform": blog.platform.value, "error": crawl_result.error},
                    "crawled_count": 0,
                    "is_new_blog": True,
                    "matching_started": False
                }

            # SEO 플러그인 감지 (WordPress만, 실패해도 무시)
            if blog.platform == BlogPlatform.WORDPRESS:
                try:
                    from .publishing.seo_detector import SEODetector
                    detector = SEODetector()
                    seo_result = await detector.detect(blog.url)
                    seo_config = blog.seo_config or {}
                    seo_config["detected_plugin"] = seo_result.get("detected_plugin")
                    seo_config["detected_at"] = seo_result.get("detected_at")
                    blog.seo_config = seo_config
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(blog, 'seo_config')
                except Exception as e:
                    logger.warning(
                        f"SEO 플러그인 감지 실패 (무시) | blog_id={blog.id} | error={e}"
                    )

            # 2. 신규 블로그 여부 확인
            is_new_blog = crawl_result.is_new_blog

            if is_new_blog:
                # 신규 블로그: 매칭 불필요
                blog.crawl_status = "synced"
                blog.is_new_blog = True
                await self.db.commit()

                logger.info(f"신규 블로그 연결 완료 | 블로그ID={blog.id}")

                # 동작 로그 기록
                await add_action_log(
                    self.db, "SUCCESS",
                    f"신규 블로그 연결 완료: {blog.name}",
                    category="crawl", resource_type="blog", resource_id=blog.id
                )

                return {
                    "success": True,
                    "message": "신규 블로그로 등록되었습니다. 글 생성 후 바로 발행 가능합니다.",
                    "details": {
                        "platform": blog.platform.value,
                        "url": blog.url,
                        "is_new_blog": True
                    },
                    "crawled_count": 0,
                    "is_new_blog": True,
                    "matching_started": False
                }

            # 3. 기존 운영 블로그: 백그라운드 매칭 시작
            blog.crawl_status = "matching"
            blog.is_new_blog = False
            await self.db.commit()

            # 동작 로그 기록 (크롤링 완료)
            await add_action_log(
                self.db, "INFO",
                f"블로그 크롤링 완료: {blog.name} ({crawl_result.crawled_count}개)",
                category="crawl", resource_type="blog", resource_id=blog.id
            )

            # 백그라운드에서 매칭 실행 (비동기)
            await self._run_background_matching(blog.id)

            logger.info(f"기존 블로그 연결 완료 - 매칭 시작 | 블로그ID={blog.id} | 크롤링={crawl_result.crawled_count}")

            return {
                "success": True,
                "message": f"{crawl_result.crawled_count}개 포스트 발견. 백그라운드에서 유사도 매칭 진행 중...",
                "details": {
                    "platform": blog.platform.value,
                    "url": blog.url,
                    "crawled_count": crawl_result.crawled_count,
                    "new_posts": crawl_result.new_count
                },
                "crawled_count": crawl_result.crawled_count,
                "is_new_blog": False,
                "matching_started": True
            }

        except Exception as e:
            blog.crawl_status = "error"
            await self.db.commit()
            logger.error(f"연결 테스트 실패 | 블로그ID={blog.id} | 오류={e}")

            return {
                "success": False,
                "message": f"연결 테스트 중 오류가 발생했습니다: {str(e)}",
                "details": {"platform": blog.platform.value, "error": str(e)},
                "crawled_count": 0,
                "is_new_blog": True,
                "matching_started": False
            }

    async def _run_background_matching(self, blog_id: int) -> None:
        """
        백그라운드 유사도 매칭 실행

        Note: 현재는 동기적으로 실행하지만,
        추후 Celery/FastAPI BackgroundTasks로 비동기 처리 가능
        """
        try:
            matcher_service = SimilarityMatcherService(self.db)
            matched_count, unmatched_count = await matcher_service.match_blog_posts(blog_id)

            logger.info(f"백그라운드 매칭 완료 | 블로그ID={blog_id} | 매칭={matched_count} | 미매칭={unmatched_count}")

            # 동작 로그 기록 (매칭 완료)
            blog = await self.db.get(Blog, blog_id)
            if blog:
                await add_action_log(
                    self.db, "SUCCESS",
                    f"유사도 매칭 완료: {blog.name} ({matched_count}/{matched_count + unmatched_count})",
                    category="match", resource_type="blog", resource_id=blog_id
                )

        except Exception as e:
            logger.error(f"백그라운드 매칭 실패 | 블로그ID={blog_id} | 오류={e}")

            # 동작 로그 기록 (매칭 실패)
            await add_action_log(
                self.db, "ERROR",
                f"유사도 매칭 실패: 블로그 ID {blog_id} - {str(e)[:100]}",
                category="match", resource_type="blog", resource_id=blog_id
            )

            # 블로그 상태를 에러로 변경
            blog = await self.db.get(Blog, blog_id)
            if blog:
                blog.crawl_status = "error"
                await self.db.commit()