"""
노드 1: 블로그 조회 모듈 (공용)

Features:
- Flow에 연결된 블로그 목록 조회
- 블로그별 포스트 수 조회
- 마지막 발행 시간 조회
"""
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger("blog_fetcher")


class BlogFetcher:
    """
    블로그 조회 노드

    모든 플로우에서 첫 번째 단계로 사용됩니다.
    Flow에 연결된 블로그들의 정보와 상태를 조회합니다.
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션
        """
        self.db = db

    async def execute(
        self,
        flow_id: int,
        user_id: int,
        module_id: Optional[int] = None,
        post_range_start: Optional[int] = None,
        post_range_end: Optional[int] = None
    ) -> dict[str, Any]:
        """
        블로그 목록 조회 실행

        Args:
            flow_id: 플로우 ID
            user_id: 사용자 ID
            module_id: 모듈 ID (선택)
            post_range_start: 포스트 범위 시작 (선택)
            post_range_end: 포스트 범위 끝 (선택, None이면 무제한)

        Returns:
            BlogFetcherOutput 형식의 딕셔너리
        """
        logger.info(
            f"[BLOG_FETCHER] 시작 | FlowID={flow_id}, UserID={user_id}, "
            f"PostRange={post_range_start}~{post_range_end if post_range_end else '무제한'}"
        )

        try:
            blogs = await self._fetch_blogs_from_flow(flow_id, user_id)

            # 블로그별 포스트 수 조회
            blog_infos = []
            for blog in blogs:
                blog_info = await self._build_blog_info(blog)
                blog_infos.append(blog_info)

            # 포스트 범위로 블로그 필터링
            if post_range_start is not None:
                filtered_blogs = []
                for blog_info in blog_infos:
                    post_count = blog_info.get("post_count", 0)

                    # 범위 체크: start <= post_count <= end (end가 None이면 무제한)
                    if post_range_end is None:
                        # 무제한: start 이상이면 통과
                        if post_count >= post_range_start:
                            filtered_blogs.append(blog_info)
                            logger.info(
                                f"[BLOG_FETCHER] ✅ 범위 내 | {blog_info['name']}: "
                                f"{post_count}개 >= {post_range_start}"
                            )
                        else:
                            logger.info(
                                f"[BLOG_FETCHER] ❌ 범위 외 | {blog_info['name']}: "
                                f"{post_count}개 < {post_range_start}"
                            )
                    else:
                        # 범위 지정: start <= post_count <= end
                        if post_range_start <= post_count <= post_range_end:
                            filtered_blogs.append(blog_info)
                            logger.info(
                                f"[BLOG_FETCHER] ✅ 범위 내 | {blog_info['name']}: "
                                f"{post_range_start} <= {post_count} <= {post_range_end}"
                            )
                        else:
                            logger.info(
                                f"[BLOG_FETCHER] ❌ 범위 외 | {blog_info['name']}: "
                                f"{post_count}개 not in {post_range_start}~{post_range_end}"
                            )

                blog_infos = filtered_blogs
                logger.info(f"[BLOG_FETCHER] 필터링 후 | {len(blog_infos)}개 블로그")

            logger.info(f"[BLOG_FETCHER] 완료 | {len(blog_infos)}개 블로그 조회됨")

            return {
                "blogs": blog_infos,
                "total_count": len(blog_infos),
                "fetched_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"[BLOG_FETCHER] 오류 | FlowID={flow_id} | Error={e}")
            raise

    async def _fetch_blogs_from_flow(self, flow_id: int, user_id: int) -> list:
        """Flow에 연결된 블로그 목록 조회"""
        # 동적 임포트로 순환 참조 방지 (컨테이너/로컬 환경 호환)
        try:
            from app.models.flow import Flow
            from app.models.flow_blog import FlowBlog
            from app.models.blog import Blog
        except ImportError:
            from services.republish.app.models.flow import Flow
            from services.republish.app.models.flow_blog import FlowBlog
            from services.republish.app.models.blog import Blog

        query = (
            select(Blog)
            .join(FlowBlog, FlowBlog.blog_id == Blog.id)
            .join(Flow, Flow.id == FlowBlog.flow_id)
            .where(
                and_(
                    Flow.id == flow_id,
                    Flow.user_id == user_id
                )
            )
            .options(selectinload(Blog.google_credential))
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _build_blog_info(self, blog) -> dict[str, Any]:
        """블로그 정보 딕셔너리 생성"""
        # 포스트 수 조회 (캐시된 값 사용 또는 API 호출)
        post_count = await self._get_post_count(blog)

        # 마지막 발행 시간 (post_count_updated_at 사용)
        last_publish_at = None
        if hasattr(blog, 'post_count_updated_at') and blog.post_count_updated_at:
            last_publish_at = blog.post_count_updated_at.isoformat()

        return {
            "id": blog.id,
            "name": blog.name,
            "url": blog.url,
            "platform": blog.platform.value if hasattr(blog.platform, 'value') else str(blog.platform),
            "post_count": post_count,
            "last_publish_at": last_publish_at,
            "credential_id": blog.google_credential_id if hasattr(blog, 'google_credential_id') else None
        }

    async def _get_post_count(self, blog) -> int:
        """
        블로그 포스트 수 조회

        우선순위:
        1. DB 캐시된 값 (blog.total_post_count)
        2. API 호출 (필요 시)
        """
        # 캐시된 값이 있으면 사용
        if hasattr(blog, 'total_post_count') and blog.total_post_count is not None:
            return blog.total_post_count

        # 캐시가 없으면 0 반환 (API 호출은 별도 노드에서 처리)
        return 0


async def create_blog_fetcher(db: AsyncSession) -> BlogFetcher:
    """
    BlogFetcher 인스턴스 생성 팩토리 함수

    Args:
        db: 데이터베이스 세션

    Returns:
        BlogFetcher 인스턴스
    """
    return BlogFetcher(db)
