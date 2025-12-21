"""
프로파일 관리 API 엔드포인트

Features:
- 프로파일 CRUD 작업
- 블로그 연동/해제
- 프로파일 통계 조회
- 요청 검증 및 응답
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..core.database import get_db_session
from ..services.profile_service import ProfileService
from ..schemas.profile import (
    ProfileCreateRequest,
    ProfileUpdateRequest,
    ProfileResponse,
    ProfileListResponse,
    BlogLinkRequest,
    BlogUnlinkRequest,
    BlogLinkResponse,
    LinkedBlogResponse,
    ProfileStatsResponse,
    ProfileDetailStatsResponse,
    ErrorResponse
)
from ..models.user import User
from ..core.logger import get_logger
from .auth import get_current_user

logger = get_logger("profile_router", "profile.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/profiles", tags=["프로파일 관리"])
page_router = APIRouter(tags=["프로파일 페이지"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    404: {"model": ErrorResponse, "description": "리소스 없음"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"}
}


# ===========================================
# 프로파일 CRUD API
# ===========================================

@router.post(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="프로파일 생성",
    description="새 재발행 프로파일을 생성합니다",
    responses=responses
)
async def create_profile(
    request: ProfileCreateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ProfileResponse:
    """프로파일 생성"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"프로파일 생성 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        profile_data = request.model_dump()
        profile = await profile_service.create_profile(current_user, profile_data)

        # 응답 데이터 구성
        response_data = {
            **profile.__dict__,
            "linked_blogs_count": 0,
            "total_published": 0
        }

        logger.info(f"프로파일 생성 성공 | 프로파일ID={profile.id} | 사용자={current_user.id}")
        return ProfileResponse(**response_data)

    except ValueError as e:
        logger.warning(f"프로파일 생성 실패 - 유효성 검증 오류 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"프로파일 생성 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 생성 중 오류가 발생했습니다"
        )


@router.get(
    "",
    response_model=List[ProfileListResponse],
    summary="프로파일 목록 조회",
    description="사용자의 프로파일 목록을 조회합니다",
    responses=responses
)
async def get_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[ProfileListResponse]:
    """프로파일 목록 조회"""
    try:
        profile_service = ProfileService(db)
        profiles = await profile_service.get_user_profiles(current_user)

        logger.info(f"프로파일 목록 조회 | 사용자={current_user.id} | 개수={len(profiles)}")
        return profiles

    except Exception as e:
        logger.error(f"프로파일 목록 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 목록 조회 중 오류가 발생했습니다"
        )


@router.get(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="프로파일 상세 조회",
    description="특정 프로파일의 상세 정보를 조회합니다",
    responses=responses
)
async def get_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ProfileResponse:
    """프로파일 상세 조회"""
    try:
        profile_service = ProfileService(db)
        profile = await profile_service.get_profile_by_id(current_user, profile_id)

        logger.info(f"프로파일 상세 조회 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return profile

    except ValueError as e:
        logger.warning(f"프로파일 조회 실패 - 권한 없음 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로파일을 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"프로파일 상세 조회 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 조회 중 오류가 발생했습니다"
        )


@router.put(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="프로파일 수정",
    description="프로파일 정보를 수정합니다",
    responses=responses
)
async def update_profile(
    profile_id: int,
    request: ProfileUpdateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ProfileResponse:
    """프로파일 수정"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"프로파일 수정 API 요청 | 프로파일ID={profile_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        update_data = request.model_dump(exclude_unset=True)
        profile = await profile_service.update_profile(current_user, profile_id, update_data)

        logger.info(f"프로파일 수정 성공 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return profile

    except ValueError as e:
        logger.warning(f"프로파일 수정 실패 - 유효성 검증 오류 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"프로파일 수정 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 수정 중 오류가 발생했습니다"
        )


@router.delete(
    "/{profile_id}",
    summary="프로파일 삭제",
    description="프로파일을 삭제합니다 (소프트 삭제)",
    responses={
        **responses,
        200: {"description": "삭제 성공"}
    }
)
async def delete_profile(
    profile_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """프로파일 삭제"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"프로파일 삭제 API 요청 | 프로파일ID={profile_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        await profile_service.delete_profile(current_user, profile_id)

        logger.info(f"프로파일 삭제 성공 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return {"message": "프로파일이 삭제되었습니다"}

    except ValueError as e:
        logger.warning(f"프로파일 삭제 실패 - 권한 없음 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로파일을 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"프로파일 삭제 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 삭제 중 오류가 발생했습니다"
        )


# ===========================================
# 블로그 연동 API
# ===========================================

@router.post(
    "/{profile_id}/link/{blog_id}",
    response_model=BlogLinkResponse,
    summary="블로그 연동",
    description="프로파일에 블로그를 연동합니다",
    responses=responses
)
async def link_blog(
    profile_id: int,
    blog_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> BlogLinkResponse:
    """블로그 연동"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"블로그 연동 API 요청 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        result = await profile_service.link_blog(current_user, profile_id, blog_id)

        response = BlogLinkResponse(
            profile_id=profile_id,
            blog_id=blog_id,
            message="블로그가 성공적으로 연동되었습니다",
            success=True
        )

        logger.info(f"블로그 연동 성공 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id}")
        return response

    except ValueError as e:
        logger.warning(f"블로그 연동 실패 - 유효성 검증 오류 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"블로그 연동 실패 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="블로그 연동 중 오류가 발생했습니다"
        )


@router.delete(
    "/{profile_id}/unlink/{blog_id}",
    summary="블로그 연동 해제",
    description="프로파일에서 블로그 연동을 해제합니다",
    responses={
        **responses,
        200: {"description": "연동 해제 성공"}
    }
)
async def unlink_blog(
    profile_id: int,
    blog_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """블로그 연동 해제"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"블로그 연동 해제 API 요청 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        await profile_service.unlink_blog(current_user, profile_id, blog_id)

        logger.info(f"블로그 연동 해제 성공 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id}")
        return {"message": "블로그 연동이 해제되었습니다"}

    except ValueError as e:
        logger.warning(f"블로그 연동 해제 실패 - 권한 없음 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연동 정보를 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"블로그 연동 해제 실패 | 프로파일ID={profile_id} | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="블로그 연동 해제 중 오류가 발생했습니다"
        )


@router.get(
    "/{profile_id}/blogs",
    response_model=List[LinkedBlogResponse],
    summary="연동된 블로그 목록",
    description="프로파일에 연동된 블로그 목록을 조회합니다",
    responses=responses
)
async def get_linked_blogs(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[LinkedBlogResponse]:
    """연동된 블로그 목록 조회"""
    try:
        profile_service = ProfileService(db)
        blogs = await profile_service.get_linked_blogs(current_user, profile_id)

        logger.info(f"연동된 블로그 목록 조회 | 프로파일ID={profile_id} | 사용자={current_user.id} | 개수={len(blogs)}")
        return blogs

    except ValueError as e:
        logger.warning(f"연동된 블로그 목록 조회 실패 - 권한 없음 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로파일을 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"연동된 블로그 목록 조회 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="연동된 블로그 목록 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 통계 API
# ===========================================

@router.get(
    "/stats/summary",
    response_model=ProfileStatsResponse,
    summary="프로파일 통계 조회",
    description="사용자의 프로파일 전체 통계를 조회합니다",
    responses=responses
)
async def get_profile_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ProfileStatsResponse:
    """프로파일 통계 조회"""
    try:
        profile_service = ProfileService(db)
        stats = await profile_service.get_profile_stats(current_user)

        logger.info(f"프로파일 통계 조회 | 사용자={current_user.id}")
        return stats

    except Exception as e:
        logger.error(f"프로파일 통계 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 통계 조회 중 오류가 발생했습니다"
        )


@router.get(
    "/{profile_id}/stats",
    response_model=ProfileDetailStatsResponse,
    summary="프로파일 상세 통계",
    description="특정 프로파일의 상세 통계를 조회합니다",
    responses=responses
)
async def get_profile_detail_stats(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ProfileDetailStatsResponse:
    """프로파일 상세 통계 조회"""
    try:
        profile_service = ProfileService(db)
        stats = await profile_service.get_profile_detail_stats(current_user, profile_id)

        logger.info(f"프로파일 상세 통계 조회 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return stats

    except ValueError as e:
        logger.warning(f"프로파일 상세 통계 조회 실패 - 권한 없음 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로파일을 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"프로파일 상세 통계 조회 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로파일 상세 통계 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 페이지 라우터 (HTML 응답)
# ===========================================

@page_router.get("/profiles", response_class=HTMLResponse)
async def profiles_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """프로파일 목록 페이지"""
    try:
        profile_service = ProfileService(db)
        profiles = await profile_service.get_user_profiles(current_user)
        stats = await profile_service.get_profile_stats(current_user)

        return templates.TemplateResponse(
            "profiles/list.html",
            {
                "request": request,
                "user": current_user,
                "profiles": profiles,
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"프로파일 목록 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "프로파일 목록을 불러올 수 없습니다"
            }
        )


# ===========================================
# 유틸리티 함수
# ===========================================

def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"