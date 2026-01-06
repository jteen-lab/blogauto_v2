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
