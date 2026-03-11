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
    블로그-제목 매칭 요약 조회

    Returns:
        - total: 전체 메인 타이틀 수
        - matched: 이 블로그 포스트와 매칭된 타이틀 수
        - unmatched: 이 블로그와 매칭되지 않은 타이틀 수 (독립 포스트)
        - crawled_count: 크롤링된 포스트 총 수
        - matched_posts: 매칭된 포스트 수
        - unmatched_posts: 미매칭 포스트 수
    """
    from sqlalchemy import select, func, distinct
    from ..models.title import MainTitle
    from ..models.crawled_post import CrawledPost

    # 블로그 존재 확인
    blog_service = BlogService(db)
    await blog_service.get_blog_by_id(current_user, blog_id)

    # 전체 메인 타이틀 수
    total_titles_query = select(func.count(MainTitle.id))
    total_titles = (await db.execute(total_titles_query)).scalar() or 0

    # 이 블로그에서 매칭된 메인 타이틀 ID들
    matched_title_ids_query = select(distinct(CrawledPost.matched_main_title_id)).where(
        CrawledPost.blog_id == blog_id,
        CrawledPost.match_status == "matched",
        CrawledPost.matched_main_title_id.isnot(None)
    )
    matched_result = await db.execute(matched_title_ids_query)
    matched_title_ids = [r[0] for r in matched_result.all() if r[0]]
    matched_count = len(matched_title_ids)

    # 미매칭 타이틀 수 (전체 - 매칭됨)
    unmatched_count = total_titles - matched_count

    # 크롤링 포스트 통계
    crawled_stats_query = select(
        func.count(CrawledPost.id).label('total'),
        func.count(CrawledPost.id).filter(CrawledPost.match_status == "matched").label('matched'),
        func.count(CrawledPost.id).filter(CrawledPost.match_status == "unmatched").label('unmatched'),
    ).where(CrawledPost.blog_id == blog_id)
    crawled_stats = (await db.execute(crawled_stats_query)).first()

    # 블로그의 last_matched_at 조회
    from ..models.blog import Blog
    blog_query = select(Blog.last_matched_at).where(Blog.id == blog_id)
    last_matched_at = (await db.execute(blog_query)).scalar()

    return {
        "total": total_titles,
        "matched": matched_count,
        "unmatched": unmatched_count,
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


@router.post(
    "/{blog_id}/auto-match",
    summary="블로그 자동 매칭 실행",
    description="정식제목 탭에서 블로그 선택 시 V3 엔진으로 자동 유사도 매칭",
    responses=responses,
)
async def auto_match_blog_posts(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    블로그 자동 매칭 (V3 SimilarityService 사용)

    정식제목 탭에서 블로그 선택 시 호출되어
    pending/unmatched 크롤링 포스트를 자동으로 매칭합니다.

    Returns:
        matched: 매칭 성공 수
        unmatched: 미매칭 수
        skipped: 건너뛴 수
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
        f"임계값={threshold}%"
    )

    # 자동 매칭 실행
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 재매칭 실행"""
    from sqlalchemy import select, update as sql_update
    from ..models.blog import Blog
    from ..models.crawled_post import CrawledPost
    from ..services.similarity_matcher_service import SimilarityMatcherService

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
