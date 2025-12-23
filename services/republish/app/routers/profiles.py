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
            "linked_blogs_count": await profile_service.get_linked_blogs_count(profile.id),
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
        profiles_raw = await profile_service.get_user_profiles(current_user)

        # 프로파일에 추가 정보 첨부
        profiles = []
        for p in profiles_raw:
            profile_dict = {
                "id": p.id,
                "name": p.name,
                "is_active": p.is_active,
                "min_post_count": p.min_post_count,
                "post_range_start": p.post_range_start,
                "post_range_end": p.post_range_end,
                "interval_mode": p.interval_mode,
                "manual_interval_minutes": p.manual_interval_minutes,
                "auto_daily_count": p.auto_daily_count,
                "priority": p.priority,
                "created_at": p.created_at,
                "linked_blogs_count": await profile_service.get_linked_blogs_count(p.id),
                "total_published": 0  # TODO: 실제 발행 수
            }
            profiles.append(ProfileListResponse(**profile_dict))

        logger.info(f"프로파일 목록 조회 | 사용자={current_user.id} | 프로파일수={len(profiles)}")
        return profiles

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
        profiles_raw = await profile_service.get_user_profiles(current_user)
        
        # 프로파일에 추가 정보 첨부
        profiles = []
        for p in profiles_raw:
            profile_dict = {
                "id": p.id,
                "name": p.name,
                "is_active": p.is_active,
                "min_post_count": p.min_post_count,
                "post_range_start": p.post_range_start,
                "post_range_end": p.post_range_end,
                "interval_mode": p.interval_mode,
                "manual_interval_minutes": p.manual_interval_minutes,
                "auto_daily_count": p.auto_daily_count,
                "priority": p.priority,
                "created_at": p.created_at,
                "linked_blogs_count": await profile_service.get_linked_blogs_count(p.id),
                "total_published": 0  # TODO: 실제 발행 수
            }
            profiles.append(type("Profile", (), profile_dict)())
        
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

@page_router.get("/profiles/new", response_class=HTMLResponse)
async def profile_create_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """프로파일 생성 페이지"""
    return templates.TemplateResponse(
        "profiles/form.html",
        {
            "request": request,
            "user": current_user,
            "profile": None
        }
    )


@page_router.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
async def profile_edit_page(
    profile_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """프로파일 수정 페이지"""
    try:
        profile_service = ProfileService(db)
        profile = await profile_service.get_profile_by_id(current_user, profile_id)
        return templates.TemplateResponse(
            "profiles/form.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile
            }
        )
    except ValueError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "프로파일을 찾을 수 없습니다"
            }
        )
    except Exception as e:
        logger.error(f"프로파일 수정 페이지 오류 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "프로파일 정보를 불러올 수 없습니다"
            }
        )


@page_router.get("/profiles/{profile_id}/stats", response_class=HTMLResponse)
async def profile_stats_page(
    profile_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """프로파일 통계 페이지"""
    try:
        profile_service = ProfileService(db)
        profile = await profile_service.get_profile_by_id(current_user, profile_id)
        # 간단한 통계 데이터
        stats = {
            "profile": profile,
            "total_published": 0,
            "success_rate": 0.0,
            "linked_blogs": []
        }
        return templates.TemplateResponse(
            "profiles/stats.html",
            {
                "request": request,
                "user": current_user,
                "profile": profile,
                "stats": stats
            }
        )
    except ValueError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "프로파일을 찾을 수 없습니다"
            }
        )
    except Exception as e:
        logger.error(f"프로파일 통계 페이지 오류 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "프로파일 통계를 불러올 수 없습니다"
            }
        )


@router.put(
    "/{profile_id}",
    response_model=ProfileResponse,
    summary="프로파일 수정",
    description="기존 프로파일을 수정합니다",
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
        logger.info(f"프로파일 수정 요청 데이터 | update_data={update_data}")
        profile = await profile_service.update_profile(current_user, profile_id, update_data)

        # 응답 데이터 구성
        response_data = {
            **profile.__dict__,
            "linked_blogs_count": await profile_service.get_linked_blogs_count(profile.id),
            "total_published": 0
        }

        logger.info(f"프로파일 수정 성공 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return ProfileResponse(**response_data)

    except ValueError as e:
        error_msg = str(e)
        # 중복 이름 오류인지 확인
        if "이미" in error_msg and "이름의 프로파일이 존재합니다" in error_msg:
            logger.warning(f"프로파일 수정 실패 - 중복 이름 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        else:
            logger.warning(f"프로파일 수정 실패 - 권한 없음 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={error_msg}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="프로파일을 찾을 수 없습니다"
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
    description="프로파일을 삭제합니다",
    responses=responses
)
async def delete_profile(
    profile_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """프로파일 삭제 API"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"프로파일 삭제 API 요청 | 프로파일ID={profile_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        profile_service = ProfileService(db)
        result = await profile_service.delete_profile(current_user, profile_id)

        logger.info(f"프로파일 삭제 성공 | 프로파일ID={profile_id} | 사용자={current_user.id}")
        return {
            "success": True,
            "message": result.get("message", "프로파일이 삭제되었습니다")
        }

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


@router.post("/{profile_id}/copy")
async def copy_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """프로파일 복사 API"""
    try:
        profile_service = ProfileService(db)
        new_profile = await profile_service.copy_profile(profile_id, current_user)
        return {
            "success": True,
            "message": "프로파일이 복사되었습니다",
            "profile_id": new_profile.id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"프로파일 복사 실패 | profile_id={profile_id} | 오류={e}")
        raise HTTPException(status_code=500, detail="프로파일 복사에 실패했습니다")
