"""
재발행 관리 API 엔드포인트

Features:
- 연결 테스트
- 수동 재발행 실행
- 스케줄러 상태 모니터링
- 발행 이력 조회
- 대시보드 데이터
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from ..core.database import get_db_session
from ..services.publish_service import PublishService
# TODO: 프로파일 시스템에서 모듈 시스템으로 전환 중
# from ..services.profile_service import ProfileService
from ..schemas.republish import (
    ConnectionTestResponse,
    ManualRepublishRequest,
    ManualRepublishResponse,
    SchedulerStatusResponse,
    PublishHistoryRequest,
    PublishHistoryResponse,
    RepublishDashboardResponse,
    PublishResult,
    ErrorResponse
)
from ..models.user import User
from ..core.logger import get_logger
from .auth import get_current_user

logger = get_logger("republish_router", "republish.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/republish", tags=["재발행 관리"])
page_router = APIRouter(tags=["재발행 페이지"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    404: {"model": ErrorResponse, "description": "리소스 없음"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"}
}


# ===========================================
# 연결 테스트 API
# ===========================================

@router.post(
    "/test/{blog_id}",
    response_model=ConnectionTestResponse,
    summary="블로그 연결 테스트",
    description="블로그 API 연결 상태를 테스트합니다",
    responses=responses
)
async def test_blog_connection(
    blog_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ConnectionTestResponse:
    """블로그 연결 테스트"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"블로그 연결 테스트 API 요청 | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        publish_service = PublishService(db)
        test_result = await publish_service.test_blog_connection(current_user, blog_id)

        if test_result["success"]:
            logger.info(f"블로그 연결 테스트 성공 | 블로그ID={blog_id} | 사용자={current_user.id}")
        else:
            logger.warning(f"블로그 연결 테스트 실패 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={test_result.get('error_details')}")

        return ConnectionTestResponse(**test_result)

    except ValueError as e:
        logger.warning(f"블로그 연결 테스트 실패 - 권한 없음 | 블로그ID={blog_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="블로그를 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"블로그 연결 테스트 실패 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="연결 테스트 중 오류가 발생했습니다"
        )


# ===========================================
# 수동 재발행 API
# ===========================================

@router.post(
    "/trigger/{profile_id}",
    response_model=ManualRepublishResponse,
    summary="수동 재발행 실행",
    description="특정 프로파일의 재발행을 수동으로 실행합니다",
    responses=responses
)
async def trigger_manual_republish(
    profile_id: int,
    request: ManualRepublishRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ManualRepublishResponse:
    """수동 재발행 실행"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"수동 재발행 실행 API 요청 | 프로파일ID={profile_id} | 사용자={current_user.id} | 강제실행={request.force_execute} | IP={client_ip}")

    try:
        publish_service = PublishService(db)
        result = await publish_service.execute_manual_republish(
            current_user,
            profile_id,
            request.force_execute,
            request.specific_post_id,
            request.dry_run
        )

        if result["executed"]:
            logger.info(f"수동 재발행 실행 성공 | 프로파일ID={profile_id} | 사용자={current_user.id} | 결과={result['result']}")
        else:
            logger.warning(f"수동 재발행 실행 불가 | 프로파일ID={profile_id} | 사용자={current_user.id} | 이유={result['message']}")

        return ManualRepublishResponse(
            profile_id=profile_id,
            **result
        )

    except ValueError as e:
        logger.warning(f"수동 재발행 실행 실패 - 유효성 검증 오류 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"수동 재발행 실행 실패 | 프로파일ID={profile_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="수동 재발행 실행 중 오류가 발생했습니다"
        )


# ===========================================
# 스케줄러 상태 API
# ===========================================

@router.get(
    "/status",
    response_model=SchedulerStatusResponse,
    summary="스케줄러 상태 조회",
    description="재발행 스케줄러의 현재 상태를 조회합니다",
    responses=responses
)
async def get_scheduler_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> SchedulerStatusResponse:
    """스케줄러 상태 조회"""
    try:
        # 여기서는 스케줄러 상태를 가져오는 로직이 필요합니다
        # 실제 구현에서는 스케줄러 서비스에서 상태를 가져와야 합니다
        from ..core.scheduler import scheduler_manager

        status_data = await scheduler_manager.get_status()

        logger.info(f"스케줄러 상태 조회 | 사용자={current_user.id} | 상태={status_data['status']}")
        return SchedulerStatusResponse(**status_data)

    except Exception as e:
        logger.error(f"스케줄러 상태 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="스케줄러 상태 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 발행 이력 API
# ===========================================

@router.get(
    "/history",
    response_model=PublishHistoryResponse,
    summary="발행 이력 조회",
    description="재발행 이력을 조회합니다",
    responses=responses
)
async def get_publish_history(
    profile_id: Optional[int] = Query(None, description="프로파일 ID 필터"),
    blog_id: Optional[int] = Query(None, description="블로그 ID 필터"),
    result: Optional[str] = Query(None, description="결과 필터"),
    limit: int = Query(50, description="조회 개수", ge=1, le=200),
    offset: int = Query(0, description="오프셋", ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> PublishHistoryResponse:
    """발행 이력 조회"""
    try:
        publish_service = PublishService(db)

        # 요청 객체 생성
        history_request = PublishHistoryRequest(
            profile_id=profile_id,
            blog_id=blog_id,
            result=result,
            limit=limit,
            offset=offset
        )

        history = await publish_service.get_publish_history(current_user, history_request)

        logger.info(f"발행 이력 조회 | 사용자={current_user.id} | 개수={len(history.entries)}")
        return history

    except Exception as e:
        logger.error(f"발행 이력 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="발행 이력 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 대시보드 API
# ===========================================

@router.get(
    "/dashboard",
    response_model=RepublishDashboardResponse,
    summary="재발행 대시보드",
    description="재발행 관련 전체 현황을 조회합니다",
    responses=responses
)
async def get_republish_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> RepublishDashboardResponse:
    """재발행 대시보드 데이터 조회"""
    try:
        publish_service = PublishService(db)
        # profile_service = ProfileService(db)

        # 대시보드 데이터 수집
        dashboard_data = await publish_service.get_dashboard_data(current_user)

        logger.info(f"재발행 대시보드 조회 | 사용자={current_user.id}")
        return RepublishDashboardResponse(**dashboard_data)

    except Exception as e:
        logger.error(f"재발행 대시보드 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="대시보드 데이터 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 페이지 라우터 (HTML 응답)
# ===========================================

@page_router.get("/republish", response_class=HTMLResponse)
async def republish_dashboard_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """재발행 대시보드 페이지"""
    try:
        publish_service = PublishService(db)
        # profile_service = ProfileService(db)

        # 대시보드 데이터 수집
        dashboard_data = await publish_service.get_dashboard_data(current_user)
        # profiles = await profile_service.get_user_profiles(current_user)
        profiles = []  # 임시: 빈 목록

        return templates.TemplateResponse(
            "republish/dashboard.html",
            {
                "request": request,
                "user": current_user,
                "dashboard": dashboard_data,
                "profiles": profiles
            }
        )
    except Exception as e:
        logger.error(f"재발행 대시보드 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "대시보드를 불러올 수 없습니다"
            }
        )


@page_router.get("/republish/history", response_class=HTMLResponse)
async def republish_history_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """재발행 이력 페이지"""
    try:
        publish_service = PublishService(db)

        # 최근 50개 이력 조회
        history_request = PublishHistoryRequest(limit=50, offset=0)
        history = await publish_service.get_publish_history(current_user, history_request)

        return templates.TemplateResponse(
            "republish/history.html",
            {
                "request": request,
                "user": current_user,
                "history": history
            }
        )
    except Exception as e:
        logger.error(f"재발행 이력 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "발행 이력을 불러올 수 없습니다"
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