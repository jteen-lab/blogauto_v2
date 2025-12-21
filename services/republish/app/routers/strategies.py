"""
전략 관리 API 엔드포인트

Features:
- 블로그별 발행 비중 전략 관리
- 자동/수동 비중 조절
- 전략 통계 조회
- 비중 분포 최적화
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..services.strategy_service import StrategyService
from ..schemas.strategy import (
    StrategyUpdateRequest,
    StrategyResponse,
    StrategyStatsResponse,
    WeightAdjustmentRequest,
    WeightAdjustmentResponse,
    AutoAdjustmentResult,
    ErrorResponse
)
from ..models.user import User
from ..core.logger import get_logger
from .auth import get_current_user

logger = get_logger("strategy_router", "strategy.log")
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/strategies", tags=["전략 관리"])
page_router = APIRouter(tags=["전략 페이지"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    404: {"model": ErrorResponse, "description": "리소스 없음"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"}
}


# ===========================================
# 전략 관리 API
# ===========================================

@router.get(
    "/{blog_id}",
    response_model=StrategyResponse,
    summary="블로그 전략 조회",
    description="특정 블로그의 발행 비중 전략을 조회합니다 (없으면 기본값으로 생성)",
    responses=responses
)
async def get_blog_strategy(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StrategyResponse:
    """블로그 전략 조회"""
    try:
        strategy_service = StrategyService(db)
        strategy = await strategy_service.get_or_create_strategy(current_user, blog_id)

        logger.info(f"블로그 전략 조회 | 블로그ID={blog_id} | 사용자={current_user.id}")
        return strategy

    except ValueError as e:
        logger.warning(f"블로그 전략 조회 실패 - 권한 없음 | 블로그ID={blog_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="블로그를 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"블로그 전략 조회 실패 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="블로그 전략 조회 중 오류가 발생했습니다"
        )


@router.put(
    "/{blog_id}",
    response_model=StrategyResponse,
    summary="블로그 전략 수정",
    description="블로그의 발행 비중 전략을 수정합니다",
    responses=responses
)
async def update_blog_strategy(
    blog_id: int,
    request: StrategyUpdateRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StrategyResponse:
    """블로그 전략 수정"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"블로그 전략 수정 API 요청 | 블로그ID={blog_id} | 사용자={current_user.id} | IP={client_ip}")

    try:
        strategy_service = StrategyService(db)
        update_data = request.model_dump(exclude_unset=True)
        strategy = await strategy_service.update_strategy(current_user, blog_id, update_data)

        logger.info(f"블로그 전략 수정 성공 | 블로그ID={blog_id} | 사용자={current_user.id}")
        return strategy

    except ValueError as e:
        logger.warning(f"블로그 전략 수정 실패 - 유효성 검증 오류 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"블로그 전략 수정 실패 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="블로그 전략 수정 중 오류가 발생했습니다"
        )


# ===========================================
# 통계 API
# ===========================================

@router.get(
    "/stats/summary",
    response_model=StrategyStatsResponse,
    summary="전체 전략 통계",
    description="사용자의 모든 블로그 전략 통계를 조회합니다",
    responses=responses
)
async def get_strategy_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StrategyStatsResponse:
    """전체 전략 통계 조회"""
    try:
        strategy_service = StrategyService(db)
        stats = await strategy_service.get_user_strategy_stats(current_user)

        logger.info(f"전체 전략 통계 조회 | 사용자={current_user.id}")
        return stats

    except Exception as e:
        logger.error(f"전체 전략 통계 조회 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="전략 통계 조회 중 오류가 발생했습니다"
        )


@router.get(
    "/{blog_id}/stats",
    response_model=StrategyResponse,
    summary="블로그 전략 통계",
    description="특정 블로그의 전략 통계를 조회합니다",
    responses=responses
)
async def get_blog_strategy_stats(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StrategyResponse:
    """블로그 전략 통계 조회"""
    try:
        strategy_service = StrategyService(db)
        strategy = await strategy_service.get_strategy_with_stats(current_user, blog_id)

        logger.info(f"블로그 전략 통계 조회 | 블로그ID={blog_id} | 사용자={current_user.id}")
        return strategy

    except ValueError as e:
        logger.warning(f"블로그 전략 통계 조회 실패 - 권한 없음 | 블로그ID={blog_id} | 사용자={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="블로그를 찾을 수 없습니다"
        )
    except Exception as e:
        logger.error(f"블로그 전략 통계 조회 실패 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="블로그 전략 통계 조회 중 오류가 발생했습니다"
        )


# ===========================================
# 비중 조절 API
# ===========================================

@router.post(
    "/adjust-weights",
    response_model=WeightAdjustmentResponse,
    summary="비중 일괄 조절",
    description="여러 블로그의 발행 비중을 일괄 조절합니다",
    responses=responses
)
async def adjust_weights(
    request: WeightAdjustmentRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> WeightAdjustmentResponse:
    """비중 일괄 조절"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"비중 일괄 조절 API 요청 | 사용자={current_user.id} | 블로그수={len(request.blog_adjustments)} | IP={client_ip}")

    try:
        strategy_service = StrategyService(db)
        result = await strategy_service.adjust_weights(
            current_user,
            request.blog_adjustments,
            request.normalize
        )

        logger.info(f"비중 일괄 조절 성공 | 사용자={current_user.id} | 조절된_블로그수={len(result.adjusted_blogs)}")
        return result

    except ValueError as e:
        logger.warning(f"비중 일괄 조절 실패 - 유효성 검증 오류 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"비중 일괄 조절 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="비중 조절 중 오류가 발생했습니다"
        )


@router.post(
    "/auto-adjust",
    response_model=AutoAdjustmentResult,
    summary="자동 비중 조절",
    description="발행 이력을 분석하여 자동으로 비중을 조절합니다",
    responses=responses
)
async def auto_adjust_weights(
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AutoAdjustmentResult:
    """자동 비중 조절"""
    client_ip = _get_client_ip(http_request)

    logger.info(f"자동 비중 조절 API 요청 | 사용자={current_user.id} | IP={client_ip}")

    try:
        strategy_service = StrategyService(db)
        result = await strategy_service.auto_adjust_weights(current_user)

        if result.performed:
            logger.info(f"자동 비중 조절 수행 | 사용자={current_user.id} | 이유={result.reason}")
        else:
            logger.info(f"자동 비중 조절 불필요 | 사용자={current_user.id} | 이유={result.reason}")

        return result

    except Exception as e:
        logger.error(f"자동 비중 조절 실패 | 사용자={current_user.id} | 오류={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="자동 비중 조절 중 오류가 발생했습니다"
        )


# ===========================================
# 페이지 라우터 (HTML 응답)
# ===========================================

@page_router.get("/strategies", response_class=HTMLResponse)
async def strategies_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """전략 관리 페이지"""
    try:
        strategy_service = StrategyService(db)
        stats = await strategy_service.get_user_strategy_stats(current_user)

        return templates.TemplateResponse(
            "strategies/manage.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"전략 관리 페이지 오류 | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "전략 정보를 불러올 수 없습니다"
            }
        )


@page_router.get("/strategies/{blog_id}", response_class=HTMLResponse)
async def strategy_detail_page(
    blog_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """블로그별 전략 상세 페이지"""
    try:
        strategy_service = StrategyService(db)
        strategy = await strategy_service.get_strategy_with_stats(current_user, blog_id)

        return templates.TemplateResponse(
            "strategies/detail.html",
            {
                "request": request,
                "user": current_user,
                "strategy": strategy,
                "blog_id": blog_id
            }
        )
    except ValueError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "블로그를 찾을 수 없습니다"
            }
        )
    except Exception as e:
        logger.error(f"전략 상세 페이지 오류 | 블로그ID={blog_id} | 사용자={current_user.id} | 오류={e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "user": current_user,
                "error_message": "전략 상세 정보를 불러올 수 없습니다"
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