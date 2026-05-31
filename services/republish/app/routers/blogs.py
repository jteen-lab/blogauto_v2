"""
블로그 관리 API 엔드포인트

Features:
- 블로그 CRUD 작업
- 연결 테스트
- 통계 조회
- 요청 검증 및 응답
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..core.database import get_db_session
from ..services.blog_service import BlogService
from ..schemas.blog import (
    BlogCreateRequest,
    BlogUpdateRequest,
    BlogResponse,
    BlogListResponse,
    BlogListWrapper,
    BlogConnectionTestResponse,
    BlogStatsResponse,
    BlogMatchingConfigRequest,
    BlogMatchingConfigResponse,
    BlogMatchingStatsResponse,
    ErrorResponse,
)
from ..models.user import User
from ..core.logger import get_logger
from .auth import get_current_user

logger = get_logger("blog_router", "blog.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/blogs", tags=["블로그 관리"])
page_router = APIRouter(tags=["블로그 페이지"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    404: {"model": ErrorResponse, "description": "리소스 없음"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"},
}


@router.post(
    "",
    response_model=BlogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="블로그 등록",
    description="새 블로그를 등록합니다",
    responses=responses,
)
async def create_blog(
    request: BlogCreateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogResponse:
    """블로그 등록"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"블로그 등록 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    blog_service = BlogService(db)
    return await blog_service.create_blog(current_user, request)


@router.get(
    "",
    response_model=BlogListWrapper,
    summary="블로그 목록 조회",
    description="사용자의 블로그 목록을 조회합니다",
    responses=responses,
)
async def get_blogs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogListWrapper:
    blog_service = BlogService(db)
    blogs = await blog_service.get_user_blogs(current_user)
    return BlogListWrapper(blogs=blogs)


@router.get(
    "/with-credentials",
    summary="블로그 목록 조회 (인증정보 포함)",
    description="사용자의 블로그 목록을 조회합니다 (복호화된 인증정보 포함)",
    responses=responses,
)
async def get_blogs_with_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 목록 조회 (인증정보 포함)"""
    blog_service = BlogService(db)
    blogs = await blog_service.get_user_blogs_with_credentials(current_user)
    return {"blogs": blogs}


@router.get(
    "/by-categories",
    summary="카테고리 기반 블로그 필터링",
    description="선택된 카테고리에 매칭된 블로그와 미매칭 블로그를 반환합니다",
    responses=responses,
)
async def get_blogs_by_categories(
    topic_ids: str = None,
    subtopic_ids: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    카테고리 기반 블로그 필터링 (BlogCategory 테이블 기반)

    Args:
        topic_ids: 쉼표로 구분된 topic ID 목록 (예: "1,2,3")
        subtopic_ids: 쉼표로 구분된 subtopic ID 목록 (예: "4,5")

    Returns:
        matched_blogs: 선택된 카테고리와 연결된 블로그 목록
        unmatched_blogs: 선택된 카테고리와 연결되지 않은 블로그 목록
    """
    from sqlalchemy import select, and_, or_
    from sqlalchemy.orm import selectinload
    from ..models.blog import Blog
    from ..models.category import BlogCategory, Topic, SubTopic

    # topic_ids, subtopic_ids 파싱
    parsed_topic_ids = []
    parsed_subtopic_ids = []

    if topic_ids:
        parsed_topic_ids = [int(x.strip()) for x in topic_ids.split(',') if x.strip().isdigit()]
    if subtopic_ids:
        parsed_subtopic_ids = [int(x.strip()) for x in subtopic_ids.split(',') if x.strip().isdigit()]

    # 사용자의 모든 블로그 조회
    query = select(Blog).where(
        Blog.user_id == current_user.id,
        Blog.is_deleted == False
    )
    result = await db.execute(query)
    all_blogs = result.scalars().all()

    matched_blogs = []
    unmatched_blogs = []

    for blog in all_blogs:
        # BlogCategory 테이블에서 해당 블로그의 카테고리 조회
        cat_query = select(BlogCategory).where(
            BlogCategory.blog_id == blog.id,
            BlogCategory.is_active == True
        )
        cat_result = await db.execute(cat_query)
        blog_categories = cat_result.scalars().all()

        # 매칭 여부 확인
        is_matched = False
        matched_categories = []

        for bc in blog_categories:
            # topic_id 매칭 확인
            if bc.topic_id in parsed_topic_ids:
                is_matched = True
                # Topic, SubTopic 이름 조회
                topic_name = ""
                subtopic_name = ""
                if bc.topic_id:
                    topic_result = await db.execute(select(Topic).where(Topic.id == bc.topic_id))
                    topic = topic_result.scalar_one_or_none()
                    topic_name = topic.name if topic else ""
                if bc.subtopic_id:
                    subtopic_result = await db.execute(select(SubTopic).where(SubTopic.id == bc.subtopic_id))
                    subtopic = subtopic_result.scalar_one_or_none()
                    subtopic_name = subtopic.name if subtopic else ""
                matched_categories.append({
                    'topic_id': bc.topic_id,
                    'topic_name': topic_name,
                    'subtopic_id': bc.subtopic_id,
                    'subtopic_name': subtopic_name
                })
            # subtopic_id 매칭 확인
            elif bc.subtopic_id and bc.subtopic_id in parsed_subtopic_ids:
                is_matched = True
                topic_name = ""
                subtopic_name = ""
                if bc.topic_id:
                    topic_result = await db.execute(select(Topic).where(Topic.id == bc.topic_id))
                    topic = topic_result.scalar_one_or_none()
                    topic_name = topic.name if topic else ""
                if bc.subtopic_id:
                    subtopic_result = await db.execute(select(SubTopic).where(SubTopic.id == bc.subtopic_id))
                    subtopic = subtopic_result.scalar_one_or_none()
                    subtopic_name = subtopic.name if subtopic else ""
                matched_categories.append({
                    'topic_id': bc.topic_id,
                    'topic_name': topic_name,
                    'subtopic_id': bc.subtopic_id,
                    'subtopic_name': subtopic_name
                })

        blog_data = {
            'id': blog.id,
            'name': blog.name,
            'url': blog.url,
            'platform': blog.platform,
            'image_mode': blog.image_mode,
        }

        if is_matched:
            blog_data['matched_categories'] = matched_categories
            matched_blogs.append(blog_data)
        else:
            unmatched_blogs.append(blog_data)

    return {
        'matched_blogs': matched_blogs,
        'unmatched_blogs': unmatched_blogs,
    }


@router.get(
    "/{blog_id}/categories",
    summary="블로그의 카테고리 목록 조회",
    description="특정 블로그에 연결된 카테고리 전체를 반환합니다.",
)
async def get_blog_categories(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그에 연결된 카테고리 목록 조회 (양방향 연동 지원)"""
    from sqlalchemy import select
    from ..models.blog import Blog
    from ..models.category import BlogCategory, Topic, SubTopic

    # 블로그 소유권 확인
    blog_q = select(Blog).where(
        Blog.id == blog_id, Blog.user_id == current_user.id,
        Blog.is_deleted == False,
    )
    blog = (await db.execute(blog_q)).scalar_one_or_none()
    if not blog:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")

    # BlogCategory 조회
    bc_q = select(BlogCategory).where(
        BlogCategory.blog_id == blog_id, BlogCategory.is_active == True,
    )
    bcs = (await db.execute(bc_q)).scalars().all()

    categories = []
    for bc in bcs:
        topic_name = ""
        subtopic_name = ""
        if bc.topic_id:
            t = (await db.execute(
                select(Topic).where(Topic.id == bc.topic_id)
            )).scalar_one_or_none()
            topic_name = t.name if t else ""
        if bc.subtopic_id:
            s = (await db.execute(
                select(SubTopic).where(SubTopic.id == bc.subtopic_id)
            )).scalar_one_or_none()
            subtopic_name = s.name if s else ""
        categories.append({
            "topic_id": bc.topic_id,
            "subtopic_id": bc.subtopic_id,
            "topic_name": topic_name,
            "subtopic_name": subtopic_name,
        })

    return {
        "blog_id": blog.id,
        "blog_name": blog.name,
        "categories": categories,
    }


@router.get(
    "/{blog_id}",
    response_model=BlogResponse,
    summary="블로그 상세 조회",
    description="특정 블로그의 상세 정보를 조회합니다",
    responses=responses,
)
async def get_blog(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogResponse:
    """블로그 상세 조회"""
    blog_service = BlogService(db)
    return await blog_service.get_blog_by_id(current_user, blog_id)


@router.put(
    "/{blog_id}",
    response_model=BlogResponse,
    summary="블로그 정보 수정",
    description="블로그 정보를 수정합니다",
    responses=responses,
)
async def update_blog(
    blog_id: int,
    request: BlogUpdateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogResponse:
    """블로그 정보 수정"""
    client_ip = _get_client_ip(http_request)

    logger.info(
        f"블로그 수정 API 요청 | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}"
    )

    blog_service = BlogService(db)
    return await blog_service.update_blog(current_user, blog_id, request)


@router.delete(
    "/{blog_id}",
    summary="블로그 삭제",
    description="블로그를 삭제합니다 (소프트 삭제)",
    responses={**responses, 200: {"description": "삭제 성공"}},
)
async def delete_blog(
    blog_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 삭제"""
    client_ip = _get_client_ip(http_request)

    logger.info(
        f"블로그 삭제 API 요청 | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}"
    )

    blog_service = BlogService(db)
    return await blog_service.delete_blog(current_user, blog_id)


@router.post(
    "/{blog_id}/test",
    response_model=BlogConnectionTestResponse,
    summary="블로그 연결 테스트",
    description="블로그 API 연결을 테스트합니다",
    responses=responses,
)
async def test_blog_connection(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogConnectionTestResponse:
    """블로그 연결 테스트"""
    logger.info(
        f"블로그 연결 테스트 API 요청 | 블로그ID={blog_id} | 사용자={current_user.id}"
    )

    blog_service = BlogService(db)
    return await blog_service.test_blog_connection(current_user, blog_id)


@router.post(
    "/{blog_id}/sync-published",
    summary="발행 포스트 동기화",
    responses=responses,
)
async def sync_published_posts(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    블로그 플랫폼의 발행 포스트와 DB를 동기화

    블로그에서 삭제된 포스트를 감지하여
    DB의 CrawledPost + 이미지 파일을 정리하고
    연결된 MainTitle을 초기화합니다.
    """
    from ..services.crawl_service import CrawlService
    from ..services.post_sync_service import PostSyncService

    logger.info(f"발행 포스트 동기화 요청 | blog_id={blog_id}")

    blog_service = BlogService(db)
    blog = await blog_service._get_user_blog(current_user, blog_id)

    # 1. 플랫폼에서 현재 발행 포스트 수집
    crawl_service = CrawlService(db)
    try:
        if blog.platform.value == "wordpress":
            platform_posts = await crawl_service._crawl_wordpress(
                blog, incremental=False
            )
        elif blog.platform.value == "blogger":
            platform_posts = await crawl_service._crawl_blogger(
                blog, incremental=False
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 플랫폼: {blog.platform.value}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"블로그 포스트 조회 실패: {str(e)}",
        )

    # 2. URL 목록 추출 (정규화)
    platform_urls = {
        post.url.rstrip("/")
        for post in platform_posts
        if post.url
    }

    # 3. 동기화 실행
    sync_service = PostSyncService(db)
    result = await sync_service.sync_published_posts(blog, platform_urls)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    # 4. GP 구간 분류용 total_post_count 갱신 (sync 시 자동 보정).
    # 이 값이 갱신되지 않으면 블로그가 영구히 구간1로 오분류됨.
    if result.platform_post_count and result.platform_post_count > 0:
        from datetime import datetime
        import pytz
        prev_count = blog.total_post_count
        blog.total_post_count = result.platform_post_count
        blog.post_count_updated_at = datetime.now(pytz.timezone('Asia/Seoul'))
        await db.commit()
        logger.info(
            f"[SYNC] total_post_count 갱신 | blog_id={blog_id} | "
            f"{prev_count} → {result.platform_post_count}"
        )

    # 5. Phase MATCH-040 C: 동기화 직후 초기 매칭을 백그라운드로 디스패치.
    # 사용자가 정식제목 탭을 처음 열 때 30초 대기를 겪지 않도록 사전 정리.
    try:
        from ..core.celery_match_tasks import task_auto_match_blog
        config = (blog.matching_config or {}) if blog else {}
        threshold = config.get("matching_threshold", 65)
        task = task_auto_match_blog.delay(blog_id, threshold)
        logger.info(
            f"[SYNC→MATCH] 초기 매칭 백그라운드 디스패치 | "
            f"blog_id={blog_id} | task_id={task.id} | threshold={threshold}"
        )
    except Exception as e:
        # 매칭 디스패치 실패는 sync 자체를 막지 않는다.
        logger.error(
            f"[SYNC→MATCH] 초기 매칭 디스패치 실패 | "
            f"blog_id={blog_id} | error={e}"
        )

    return {
        "success": True,
        "message": (
            f"동기화 완료: 블로그 포스트 {result.platform_post_count}개, "
            f"삭제 {result.deleted_posts}개, "
            f"제목 초기화 {result.reset_titles}개"
        ),
        "platform_post_count": result.platform_post_count,
        "db_published_count": result.db_published_count,
        "deleted_posts": result.deleted_posts,
        "deleted_images": result.deleted_images,
        "reset_titles": result.reset_titles,
    }


@router.get(
    "/stats/summary",
    response_model=BlogStatsResponse,
    summary="블로그 통계 조회",
    description="사용자의 블로그 통계를 조회합니다",
    responses=responses,
)
async def get_blog_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogStatsResponse:
    """블로그 통계 조회"""
    blog_service = BlogService(db)
    return await blog_service.get_user_blog_stats(current_user)


@router.get(
    "/{blog_id}/matching-summary",
    summary="블로그-제목 매칭 요약",
    description="특정 블로그의 크롤링 포스트와 메인 타이틀 간 매칭 현황을 조회합니다",
    responses=responses,
)
async def get_blog_matching_summary(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    블로그-제목 매칭 요약 조회 (BlogCategory 필터 적용).

    blog_id의 활성 BlogCategory에 속한 MainTitle만 카운트 대상.
    카테고리 미설정 블로그는 전체 MainTitle을 대상으로 폴백한다.

    Returns:
        - total: 카테고리 필터된 전체 정식제목 수
        - matched: 그 중 이 블로그 CrawledPost와 매칭된 수
        - published: 그 중 발행 완료된 수
        - pending: 그 중 발행 대기 수
        - unmatched: 카테고리 제목 중 이 블로그에 매칭되지 않은 수 (독립 포스트)
        - unmatched_published: 이 블로그에 발행됐으나 정식제목에 매칭 안 된 글 수
        - crawled_count/matched_posts/unmatched_posts: CrawledPost 통계
    """
    from sqlalchemy import select, func, distinct, or_
    from ..models.title import MainTitle
    from ..models.crawled_post import CrawledPost
    from ..models.category import BlogCategory

    # 블로그 존재 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 1) BlogCategory 기반 MainTitle 필터 빌드 (titles.py와 동일 패턴)
    bc_result = await db.execute(
        select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
        )
    )
    blog_categories = bc_result.scalars().all()

    subtopic_ids: set[int] = set()
    topic_only_ids: set[int] = set()
    for bc in blog_categories:
        if bc.subtopic_id:
            subtopic_ids.add(bc.subtopic_id)
        elif bc.topic_id:
            topic_only_ids.add(bc.topic_id)

    cat_conditions = []
    if subtopic_ids:
        cat_conditions.append(
            MainTitle.subtopic_id.in_(list(subtopic_ids))
        )
    if topic_only_ids:
        cat_conditions.append(
            MainTitle.topic_id.in_(list(topic_only_ids))
        )
    cat_filter = or_(*cat_conditions) if cat_conditions else None

    # 2) 카테고리 필터 + hide_group_members(대표 또는 미그룹 또는 비활성 그룹) 통과
    #    정식제목 탭의 실제 표시 row와 일치시키기 위해 동일 필터 적용.
    from ..models.title import TitleGroup
    hide_group_filter = or_(
        MainTitle.is_group_representative.is_(True),
        MainTitle.group_id.is_(None),
        ~MainTitle.group_id.in_(
            select(TitleGroup.id).where(TitleGroup.member_count >= 2)
        ),
    )

    total_query = select(func.count(MainTitle.id)).where(hide_group_filter)
    if cat_filter is not None:
        total_query = total_query.where(cat_filter)
    total_titles = (await db.execute(total_query)).scalar() or 0

    # 3) 발행완료/발행대기는 CrawledPost 단위로 카운트.
    #    블로그 카드의 matched_count(블로그 실제 발행 매칭)와 의미를 통일하기 위해
    #    BlogCategory/hide_group 필터를 적용하지 않고, 매칭된 모든 CrawledPost 기준.
    #    사용자 가설(블로그 실제 발행 = 발행완료 + 미매칭)과 일치한다.
    cp_published_q = select(func.count(CrawledPost.id)).where(
        CrawledPost.blog_id == blog_id,
        CrawledPost.match_status == "matched",
        CrawledPost.published_at.isnot(None),
    )
    published_count = (await db.execute(cp_published_q)).scalar() or 0

    cp_pending_q = select(func.count(CrawledPost.id)).where(
        CrawledPost.blog_id == blog_id,
        CrawledPost.match_status == "matched",
        CrawledPost.published_at.is_(None),
    )
    pending_count = (await db.execute(cp_pending_q)).scalar() or 0

    matched_count = published_count + pending_count

    # 4) 독립 포스트는 메인 단위로 카운트(정식제목 탭에 표시되는 row).
    #    BlogCategory + hide_group 통과 메인 중 이 블로그에 매칭되지 않은 메인의 수.
    matched_main_ids_q = (
        select(distinct(CrawledPost.matched_main_title_id))
        .where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.match_status == "matched",
            CrawledPost.matched_main_title_id.isnot(None),
        )
    )
    matched_main_ids = {
        row[0] for row in (await db.execute(matched_main_ids_q)).all()
        if row[0] is not None
    }
    if matched_main_ids:
        valid_filter = MainTitle.id.in_(matched_main_ids)
        valid_q = select(func.count(MainTitle.id)).where(
            valid_filter, hide_group_filter,
        )
        if cat_filter is not None:
            valid_q = valid_q.where(cat_filter)
        valid_matched_main = (await db.execute(valid_q)).scalar() or 0
    else:
        valid_matched_main = 0
    unmatched_count = max(total_titles - valid_matched_main, 0)

    # 6) 블로그에 발행됐으나 정식제목에 매칭 안 된 글 수
    unmatched_published_query = select(func.count(CrawledPost.id)).where(
        CrawledPost.blog_id == blog_id,
        CrawledPost.match_status == "unmatched",
    )
    unmatched_published = (
        await db.execute(unmatched_published_query)
    ).scalar() or 0

    # 7) 크롤링 포스트 통계 (블로그 실제 발행 수 = published_at NOT NULL)
    #    blog 카드의 crawled_count와 의미를 통일:
    #    "블로그에 실제 발행된 모든 글 수"
    crawled_stats_query = select(
        func.count(CrawledPost.id).filter(
            CrawledPost.published_at.isnot(None)
        ).label("total"),
        func.count(CrawledPost.id).filter(
            CrawledPost.published_at.isnot(None),
            CrawledPost.match_status == "matched",
        ).label("matched"),
        func.count(CrawledPost.id).filter(
            CrawledPost.published_at.isnot(None),
            CrawledPost.match_status == "unmatched",
        ).label("unmatched"),
    ).where(CrawledPost.blog_id == blog_id)
    crawled_stats = (await db.execute(crawled_stats_query)).first()

    # 블로그의 last_matched_at 조회
    from ..models.blog import Blog
    blog_query = select(Blog.last_matched_at).where(Blog.id == blog_id)
    last_matched_at = (await db.execute(blog_query)).scalar()

    return {
        "total": total_titles,
        "matched": matched_count,
        "published": published_count,
        "pending": pending_count,
        "unmatched": unmatched_count,
        "unmatched_published": unmatched_published,
        # 정식제목 탭에 실제 표시되는 모든 row의 합 (메인 + 미매칭 크롤포스트).
        # 발행완료 + 발행대기 + 독립 + 미매칭과 동일하므로 사용자 직관과 일치한다.
        "unified_total": total_titles + unmatched_published,
        "category_filter_applied": cat_filter is not None,
        "crawled_count": crawled_stats.total if crawled_stats else 0,
        "matched_posts": crawled_stats.matched if crawled_stats else 0,
        "unmatched_posts": crawled_stats.unmatched if crawled_stats else 0,
        "last_matched_at": last_matched_at.isoformat() if last_matched_at else None,
    }


# =================================
# 유사도 매칭 설정 API (Phase 3)
# =================================


@router.get(
    "/{blog_id}/settings/matching",
    response_model=BlogMatchingConfigResponse,
    summary="블로그 매칭 설정 조회",
    description="특정 블로그의 유사도 매칭 설정을 조회합니다",
    responses=responses,
)
async def get_blog_matching_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogMatchingConfigResponse:
    """블로그 매칭 설정 조회"""
    from sqlalchemy import select
    from ..models.blog import Blog

    # 블로그 직접 조회 (BlogResponse가 아닌 Blog 모델 필요)
    query = select(Blog).where(
        Blog.id == blog_id,
        Blog.user_id == current_user.id,
        Blog.is_deleted == False
    )
    result = await db.execute(query)
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    # matching_config가 없으면 기본값 반환
    config = blog.matching_config or {}

    return BlogMatchingConfigResponse(
        allow_duplicate_similar_posts=config.get("allow_duplicate_similar_posts", False),
        matching_threshold=config.get("matching_threshold", 65),
    )


@router.put(
    "/{blog_id}/settings/matching",
    response_model=BlogMatchingConfigResponse,
    summary="블로그 매칭 설정 저장",
    description="특정 블로그의 유사도 매칭 설정을 저장합니다",
    responses=responses,
)
async def update_blog_matching_settings(
    blog_id: int,
    request: BlogMatchingConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogMatchingConfigResponse:
    """블로그 매칭 설정 저장"""
    from sqlalchemy import select
    from ..models.blog import Blog

    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 블로그 직접 조회하여 업데이트
    from sqlalchemy.orm.attributes import flag_modified

    query = select(Blog).where(Blog.id == blog_id, Blog.is_deleted == False)
    result = await db.execute(query)
    blog = result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    # matching_config 업데이트 (JSONB 변경 감지를 위해 새 dict 할당 + flag_modified)
    new_config = {
        "allow_duplicate_similar_posts": request.allow_duplicate_similar_posts,
        "matching_threshold": request.matching_threshold,
    }
    blog.matching_config = new_config
    flag_modified(blog, "matching_config")

    await db.commit()
    await db.refresh(blog)

    logger.info(
        f"블로그 매칭 설정 저장 | 블로그ID={blog_id} | 사용자={current_user.id} | "
        f"임계값={request.matching_threshold}%"
    )

    return BlogMatchingConfigResponse(
        allow_duplicate_similar_posts=request.allow_duplicate_similar_posts,
        matching_threshold=request.matching_threshold,
    )


@router.get(
    "/{blog_id}/settings/matching/stats",
    response_model=BlogMatchingStatsResponse,
    summary="블로그 매칭 통계 조회",
    description="특정 블로그의 매칭 통계를 조회합니다",
    responses=responses,
)
async def get_blog_matching_stats(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> BlogMatchingStatsResponse:
    """블로그 매칭 통계 조회"""
    from sqlalchemy import select, func
    from ..models.crawled_post import CrawledPost
    from ..models.blog import Blog

    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    blog = await blog_service.get_blog_by_id(current_user, blog_id)

    # 크롤링 포스트 통계
    crawled_stats_query = select(
        func.count(CrawledPost.id).label('total'),
        func.count(CrawledPost.id).filter(CrawledPost.match_status == "matched").label('matched'),
        func.count(CrawledPost.id).filter(CrawledPost.match_status == "unmatched").label('unmatched'),
    ).where(CrawledPost.blog_id == blog_id)
    crawled_stats = (await db.execute(crawled_stats_query)).first()

    return BlogMatchingStatsResponse(
        crawled_count=crawled_stats.total if crawled_stats else 0,
        matched_posts=crawled_stats.matched if crawled_stats else 0,
        unmatched_posts=crawled_stats.unmatched if crawled_stats else 0,
        last_matched_at=blog.last_matched_at,
    )


@router.get(
    "/{blog_id}/unmatched-main-titles",
    summary="블로그 미매칭 정식제목 목록 (그룹2)",
    description=(
        "BlogMainTitleScan(matched=False) 카드가 있는 정식제목 = 이 블로그와 "
        "매칭 시도했으나 실패한 정식제목 목록. 사용자 일괄 정리 도구(D) 용도."
    ),
    responses=responses,
)
async def get_blog_unmatched_main_titles(
    blog_id: int,
    page: int = 1,
    size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """이 블로그 입장에서 그룹2(매칭 실패) 정식제목 목록 페이지네이션."""
    from sqlalchemy import select, func
    from ..models.title import MainTitle
    from ..models.blog_main_title_scan import BlogMainTitleScan

    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    base = (
        select(MainTitle)
        .join(
            BlogMainTitleScan,
            BlogMainTitleScan.main_title_id == MainTitle.id,
        )
        .where(
            BlogMainTitleScan.blog_id == blog_id,
            BlogMainTitleScan.matched.is_(False),
        )
        .order_by(MainTitle.id.desc())
    )

    total = (
        await db.execute(
            select(func.count())
            .select_from(BlogMainTitleScan)
            .where(
                BlogMainTitleScan.blog_id == blog_id,
                BlogMainTitleScan.matched.is_(False),
            )
        )
    ).scalar() or 0

    offset = max(0, (page - 1) * size)
    rows = (
        await db.execute(base.offset(offset).limit(size))
    ).scalars().all()

    items = [
        {
            "id": t.id,
            "title": t.title,
            "topic_id": t.topic_id,
            "subtopic_id": t.subtopic_id,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]

    return {
        "blog_id": blog_id,
        "total": total,
        "page": page,
        "size": size,
        "items": items,
    }


class _BulkPostIdsRequest(BaseModel):
    """미매칭 발행글 일괄 처리 요청."""
    post_ids: List[int]


@router.post(
    "/{blog_id}/unmatched-posts/promote-to-main",
    summary="미매칭 발행글을 정식제목으로 승급 + 매칭 (V1 기능)",
    responses=responses,
)
async def promote_unmatched_posts_to_main(
    blog_id: int,
    body: _BulkPostIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """선택한 미매칭 발행글 각각에 대해:

    1) 발행글 제목으로 새 MainTitle 생성 (블로그 첫 활성 카테고리 따름)
    2) CrawledPost.match_status='matched' + matched_main_title_id 부여
    3) BlogMainTitleScan(matched=True) 카드 등록 → 다음 사전체크 0초 유지
    """
    from sqlalchemy import select
    from ..models.crawled_post import CrawledPost
    from ..models.title import MainTitle
    from ..models.category import BlogCategory
    from ..models.blog_main_title_scan import BlogMainTitleScan
    from datetime import datetime as _dt

    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 블로그 첫 활성 카테고리 (분류 시드)
    bc_row = (
        await db.execute(
            select(BlogCategory).where(
                BlogCategory.blog_id == blog_id,
                BlogCategory.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()
    seed_topic = bc_row.topic_id if bc_row else None
    seed_subtopic = bc_row.subtopic_id if bc_row else None

    posts = (
        await db.execute(
            select(CrawledPost).where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.id.in_(body.post_ids),
                CrawledPost.match_status == "unmatched",
            )
        )
    ).scalars().all()

    promoted = 0
    errors: list[str] = []
    now = _dt.utcnow()
    for post in posts:
        try:
            new_title = MainTitle(
                title=post.title,
                status="matched",
                topic_id=seed_topic,
                subtopic_id=seed_subtopic,
            )
            db.add(new_title)
            await db.flush()
            post.mark_matched(new_title.id, 100.0)
            db.add(BlogMainTitleScan(
                blog_id=blog_id,
                main_title_id=new_title.id,
                matched=True,
                scanned_at=now,
            ))
            promoted += 1
        except Exception as e:
            errors.append(f"post_id={post.id}: {e}")

    await db.commit()
    logger.info(
        f"[PROMOTE-MAIN] blog={blog_id} | promoted={promoted}/{len(posts)} | "
        f"requested={len(body.post_ids)} | errors={len(errors)}"
    )
    return {
        "success": True,
        "promoted": promoted,
        "requested": len(body.post_ids),
        "errors": errors,
        "message": f"{promoted}개 발행글이 정식제목으로 등록되어 매칭 완료되었습니다.",
    }


@router.post(
    "/{blog_id}/unmatched-posts/promote-to-temp",
    summary="미매칭 발행글 제목을 임시제목으로 등록",
    responses=responses,
)
async def promote_unmatched_posts_to_temp(
    blog_id: int,
    body: _BulkPostIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """선택한 미매칭 발행글 제목을 TempTitle 로 복제 등록.

    CrawledPost 자체는 그대로 둔다(unmatched 유지). 사용자가 필요 시 별도로
    영구 삭제 액션을 사용한다.
    """
    from sqlalchemy import select
    from ..models.crawled_post import CrawledPost
    from ..models.title import TempTitle

    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    posts = (
        await db.execute(
            select(CrawledPost).where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.id.in_(body.post_ids),
                CrawledPost.match_status == "unmatched",
            )
        )
    ).scalars().all()

    created = 0
    errors: list[str] = []
    for post in posts:
        try:
            db.add(TempTitle(title=post.title, status="new"))
            created += 1
        except Exception as e:
            errors.append(f"post_id={post.id}: {e}")

    await db.commit()
    logger.info(
        f"[PROMOTE-TEMP] blog={blog_id} | created={created}/{len(posts)}"
    )
    return {
        "success": True,
        "created": created,
        "requested": len(body.post_ids),
        "errors": errors,
        "message": f"{created}개 임시제목이 등록되었습니다.",
    }


@router.post(
    "/{blog_id}/unmatched-posts/delete",
    summary="미매칭 발행글 영구 삭제 (CrawledPost row 삭제)",
    responses=responses,
)
async def delete_unmatched_posts(
    blog_id: int,
    body: _BulkPostIdsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """선택한 미매칭 발행글의 CrawledPost row 영구 삭제."""
    from sqlalchemy import delete as sql_delete
    from ..models.crawled_post import CrawledPost

    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    result = await db.execute(
        sql_delete(CrawledPost).where(
            CrawledPost.blog_id == blog_id,
            CrawledPost.id.in_(body.post_ids),
            CrawledPost.match_status == "unmatched",
        )
    )
    deleted = result.rowcount or 0
    await db.commit()
    logger.info(
        f"[DELETE-UNMATCHED] blog={blog_id} | deleted={deleted}"
    )
    return {
        "success": True,
        "deleted": deleted,
        "requested": len(body.post_ids),
        "message": f"{deleted}개 발행글이 삭제되었습니다.",
    }


@router.get(
    "/{blog_id}/match-counts",
    summary="블로그 매칭 사전체크 카운트",
    description=(
        "블로그 선택 시 auto-match 호출 전에 호출하는 사전체크 API. "
        "pending 발행글 수 + 미검토 그룹3 정식제목 수가 모두 0이면 매칭 스킵 가능."
    ),
    responses=responses,
)
async def get_blog_match_counts(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    매칭 사전체크 카운트 조회.

    인덱스만 사용해 ms 단위로 응답한다.
    - pending: 매칭 안 된 신규 발행글 수 (재매칭 대상)
    - unmatched: 매칭 시도했으나 짝 못 찾은 발행글 수 (참고용, 매칭 대상 아님)
    - matched: 매칭 완료된 발행글 수 (참고용)
    - unscanned_titles: 이 블로그 카테고리 ∩ 검토 카드 없는 정식제목 수 (그룹3)
    - needs_match: pending > 0 OR unscanned_titles > 0 이면 True
    """
    from sqlalchemy import select, func, and_, or_
    from ..models.crawled_post import CrawledPost
    from ..models.title import MainTitle
    from ..models.category import BlogCategory
    from ..models.blog_main_title_scan import BlogMainTitleScan

    # 블로그 존재/권한 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 1) CrawledPost 매칭 상태별 카운트 (ix_crawled_post_blog_status 활용)
    post_counts_query = select(
        CrawledPost.match_status,
        func.count(CrawledPost.id),
    ).where(CrawledPost.blog_id == blog_id).group_by(CrawledPost.match_status)
    post_counts = {
        row[0]: row[1]
        for row in (await db.execute(post_counts_query)).all()
    }
    pending_count = post_counts.get("pending", 0)
    unmatched_count = post_counts.get("unmatched", 0)
    matched_count = post_counts.get("matched", 0)

    # 2) 블로그 카테고리 추출
    bc_result = await db.execute(
        select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active.is_(True),
        )
    )
    blog_categories = bc_result.scalars().all()
    subtopic_ids = {bc.subtopic_id for bc in blog_categories if bc.subtopic_id}
    topic_only_ids = {
        bc.topic_id for bc in blog_categories
        if bc.topic_id and not bc.subtopic_id
    }

    # 3) 카테고리 필터된 정식제목 수
    base_filter = MainTitle.status.in_(["available", "matched", "used"])
    cat_conditions = []
    if subtopic_ids:
        cat_conditions.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
    if topic_only_ids:
        cat_conditions.append(MainTitle.topic_id.in_(list(topic_only_ids)))

    candidate_subq = select(MainTitle.id).where(base_filter)
    if cat_conditions:
        candidate_subq = candidate_subq.where(or_(*cat_conditions))

    # 4) 그룹3 (검토 카드 없는 후보 정식제목) 수 — 후보 ID 차집합 방식
    candidate_ids = list((await db.execute(candidate_subq)).scalars().all())
    if candidate_ids:
        scanned_ids = set(
            (await db.execute(
                select(BlogMainTitleScan.main_title_id).where(
                    BlogMainTitleScan.blog_id == blog_id,
                    BlogMainTitleScan.main_title_id.in_(candidate_ids),
                )
            )).scalars().all()
        )
        unscanned_titles_count = len(candidate_ids) - len(scanned_ids)
    else:
        unscanned_titles_count = 0

    needs_match = pending_count > 0 or unscanned_titles_count > 0

    return {
        "blog_id": blog_id,
        "pending": pending_count,
        "unmatched": unmatched_count,
        "matched": matched_count,
        "unscanned_titles": unscanned_titles_count,
        "candidate_titles": len(candidate_ids),
        "needs_match": needs_match,
    }


@router.post(
    "/{blog_id}/auto-match",
    summary="블로그 자동 매칭 실행",
    description="정식제목 탭에서 블로그 선택 시 V3 엔진으로 자동 유사도 매칭",
    responses=responses,
)
async def auto_match_blog_posts(
    blog_id: int,
    async_mode: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    블로그 자동 매칭 (V3 SimilarityService 사용)

    정식제목 탭에서 블로그 선택 시 호출되어
    pending/unmatched 크롤링 포스트를 자동으로 매칭합니다.

    Args:
        async_mode: True 이면 Celery 워커로 디스패치하고 task_id 즉시 반환.
                    프론트는 GET /api/v1/tasks/{task_id} 폴링으로 결과 확인.
                    False(기본)는 기존 동기 호출 — 호환성 유지.

    Returns (동기):
        matched / unmatched / skipped
    Returns (비동기):
        async=True, task_id, state=queued
    """
    from ..services.auto_match_service import AutoMatchService

    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 매칭 설정에서 임계값 가져오기
    from ..models.blog import Blog
    blog = await db.get(Blog, blog_id)
    config = (blog.matching_config or {}) if blog else {}
    threshold = config.get("matching_threshold", 65)

    logger.info(
        f"블로그 자동 매칭 API 요청 | "
        f"블로그ID={blog_id} | 사용자={current_user.id} | "
        f"임계값={threshold}% | async={async_mode}"
    )

    # Phase 3: 비동기 모드 — 워커로 디스패치
    if async_mode:
        from ..core.celery_match_tasks import task_auto_match_blog
        task = task_auto_match_blog.delay(blog_id, threshold)
        return {
            "async": True,
            "task_id": task.id,
            "state": "queued",
            "poll_url": f"/api/v1/tasks/{task.id}",
        }

    # 동기 (기존 동작)
    service = AutoMatchService(db)
    result = await service.auto_match(blog_id, threshold)

    return {
        "success": True,
        **result
    }


@router.post(
    "/{blog_id}/rematch",
    summary="블로그 재매칭 실행",
    description="크롤링된 포스트를 현재 설정으로 다시 매칭합니다",
    responses=responses,
)
async def run_blog_rematch(
    blog_id: int,
    async_mode: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 재매칭 실행

    Args:
        async_mode: True 이면 Celery 워커 디스패치 + task_id 반환 (Phase 3).
    """
    from sqlalchemy import select, update as sql_update
    from ..models.blog import Blog
    from ..models.crawled_post import CrawledPost
    from ..services.similarity_matcher_service import SimilarityMatcherService

    # Phase 3: 비동기 디스패치
    if async_mode:
        # 권한·임계값 확인을 위해 최소 조회만
        blog_service = BlogService(db)
        await blog_service.get_blog_by_id(current_user, blog_id)
        blog = await db.get(Blog, blog_id)
        if not blog:
            raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")
        config = blog.matching_config or {}
        threshold = config.get("matching_threshold", 65)
        from ..core.celery_match_tasks import task_rematch_blog
        task = task_rematch_blog.delay(blog_id, threshold)
        return {
            "async": True,
            "task_id": task.id,
            "state": "queued",
            "poll_url": f"/api/v1/tasks/{task.id}",
        }

    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # Blog 모델 직접 조회 (matching_config 접근용)
    blog_query = select(Blog).where(Blog.id == blog_id, Blog.is_deleted == False)
    blog_result = await db.execute(blog_query)
    blog = blog_result.scalar_one_or_none()

    if not blog:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다")

    logger.info(f"블로그 재매칭 시작 | 블로그ID={blog_id} | 사용자={current_user.id}")

    # 매칭 설정 가져오기
    config = blog.matching_config or {}
    threshold = config.get("matching_threshold", 65)

    # 재매칭: 기존 매칭된/미매칭 포스트를 다시 pending으로 변경
    reset_result = await db.execute(
        sql_update(CrawledPost)
        .where(CrawledPost.blog_id == blog_id)
        .values(
            match_status="pending",
            matched_main_title_id=None,
            match_score=None
        )
    )
    reset_count = reset_result.rowcount

    logger.info(f"재매칭 대상 리셋 | 블로그ID={blog_id} | 리셋={reset_count}개")

    # 재매칭 실행
    matcher_service = SimilarityMatcherService(db)
    matched_count, unmatched_count = await matcher_service.match_blog_posts(
        blog_id=blog_id,
        threshold=threshold
    )

    logger.info(
        f"블로그 재매칭 완료 | 블로그ID={blog_id} | "
        f"처리={reset_count} | 매칭={matched_count} | 미매칭={unmatched_count}"
    )

    return {
        "success": True,
        "message": "재매칭이 완료되었습니다",
        "processed": reset_count,
        "matched": matched_count,
        "unmatched": unmatched_count,
    }


@router.get(
    "/{blog_id}/crawled-posts",
    summary="크롤링 포스트 목록 조회",
    description="특정 블로그의 크롤링 포스트를 조회합니다 (match_status 필터 지원)",
    responses=responses,
)
async def get_blog_crawled_posts(
    blog_id: int,
    match_status: str = None,
    search: str = None,
    page: int = 1,
    size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    블로그의 크롤링 포스트 목록 조회

    Args:
        match_status: 매칭 상태 필터 (matched/unmatched/pending)
        search: 제목 검색어
        page: 페이지 번호
        size: 페이지 크기

    Returns:
        크롤링 포스트 목록
    """
    from sqlalchemy import select, func
    from ..models.crawled_post import CrawledPost

    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 쿼리 구성
    query = select(CrawledPost).where(CrawledPost.blog_id == blog_id)

    if match_status:
        query = query.where(CrawledPost.match_status == match_status)

    # 검색어 필터
    if search:
        query = query.where(CrawledPost.title.ilike(f"%{search}%"))

    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 페이지네이션 및 정렬
    query = query.order_by(CrawledPost.crawled_at.desc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    posts = result.scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "title": p.title,
                "url": p.url,
                "match_status": p.match_status,
                "match_score": p.match_score,
                "matched_main_title_id": p.matched_main_title_id,
                "source": p.source,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "crawled_at": p.crawled_at.isoformat() if p.crawled_at else None,
            }
            for p in posts
        ],
        "total": total,
        "page": page,
        "size": size,
        "has_next": (page * size) < total,
    }


@router.post(
    "/{blog_id}/crawl",
    summary="블로그 포스트 크롤링",
    description="블로그에서 새 포스트를 가져와 매칭합니다",
    responses=responses,
)
async def run_blog_crawl(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 포스트 크롤링"""
    # 블로그 조회 및 권한 확인
    blog_service = BlogService(db)
    blog = await blog_service.get_blog_by_id(current_user, blog_id)

    logger.info(f"블로그 크롤링 시작 | 블로그ID={blog_id} | 사용자={current_user.id}")

    # 연결 테스트 (크롤링 포함)
    result = await blog_service.test_blog_connection(current_user, blog_id)

    if not result.success:
        return {
            "success": False,
            "message": f"크롤링 실패: {result.message}",
            "crawled_count": 0,
        }

    logger.info(
        f"블로그 크롤링 완료 | 블로그ID={blog_id} | 크롤링={result.crawled_count}"
    )

    return {
        "success": True,
        "message": "포스트 새로고침이 완료되었습니다",
        "crawled_count": result.crawled_count,
        "is_new_blog": result.is_new_blog,
        "matching_started": result.matching_started,
    }


# =================================
# 페이지 라우터 (HTML 응답)
# =================================


@page_router.get("/blogs", response_class=HTMLResponse)
async def blogs_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """블로그 목록 페이지"""
    try:
        blog_service = BlogService(db)
        blogs = await blog_service.get_user_blogs(current_user)
        stats = await blog_service.get_user_blog_stats(current_user)

        return templates.TemplateResponse(
            "blogs/list.html",
            {"request": request, "user": current_user, "blogs": blogs, "stats": stats},
        )
    except Exception as e:
        logger.error(f"블로그 목록 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "블로그 목록을 불러올 수 없습니다",
            },
        )


@page_router.get("/blogs/create", response_class=HTMLResponse)
async def create_blog_page(
    request: Request, current_user: User = Depends(get_current_user)
):
    """블로그 등록 페이지"""
    return templates.TemplateResponse(
        "blogs/create.html", {"request": request, "user": current_user}
    )


@page_router.get("/blogs/{blog_id}/settings", response_class=HTMLResponse)
async def blog_settings_page(
    blog_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """블로그 설정 페이지"""
    try:
        blog_service = BlogService(db)
        blog = await blog_service.get_blog_by_id(current_user, blog_id)

        return templates.TemplateResponse(
            "blogs/settings.html",
            {"request": request, "user": current_user, "blog": blog},
        )
    except HTTPException as e:
        if e.status_code == 404:
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "user": current_user,
                    "error_message": "블로그를 찾을 수 없습니다",
                },
            )
        raise
    except Exception as e:
        logger.error(
            f"블로그 설정 페이지 오류 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}"
        )
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "블로그 설정을 불러올 수 없습니다",
            },
        )


# =================================
# 유틸리티 함수
# =================================


def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"
