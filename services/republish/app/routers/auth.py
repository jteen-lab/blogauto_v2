"""
인증 관련 API 엔드포인트

Features:
- 회원가입/로그인/로그아웃
- JWT 토큰 기반 인증
- 쿠키 기반 토큰 관리
- 요청 검증 및 응답
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from ..core.database import get_db_session
from ..core.jwt import verify_token, blacklist_token
from ..services.auth_service import AuthService
from ..schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    AuthResponse,
    UserResponse,
    PasswordChangeRequest,
    TokenInfo,
    ErrorResponse
)
from ..models.user import User
from ..core.logger import get_logger

logger = get_logger("auth_router", "auth.log")
security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth", tags=["인증"])

# 응답 예시
responses = {
    400: {"model": ErrorResponse, "description": "잘못된 요청"},
    401: {"model": ErrorResponse, "description": "인증 실패"},
    500: {"model": ErrorResponse, "description": "서버 내부 오류"}
}

# 의존성 함수들

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """
    현재 인증된 사용자 반환

    JWT 토큰을 쿠키 또는 Authorization 헤더에서 추출하여 검증
    """
    token = None

    # 1. Authorization 헤더에서 토큰 추출
    if credentials:
        token = credentials.credentials

    # 2. 쿠키에서 토큰 추출
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 토큰 검증
    payload = verify_token(token)
    user_id = int(payload.get("sub"))

    # 사용자 조회
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 사용자입니다"
        )

    return user

# 유틸리티 함수들

def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"

def _get_token_from_request(request: Request) -> Optional[str]:
    """요청에서 토큰 추출 (헤더 또는 쿠키)"""
    # Authorization 헤더 확인
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    # 쿠키 확인
    return request.cookies.get("access_token")

def _set_auth_cookie(response: Response, token: str) -> None:
    """인증 토큰 쿠키 설정"""
    from ..core.config import settings

    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,  # XSS 방지
        secure=settings.is_production,  # HTTPS에서만 전송
        samesite="lax"  # CSRF 방지
    )

def _clear_auth_cookie(response: Response) -> None:
    """인증 토큰 쿠키 삭제"""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=False,  # 개발환경 고려
        samesite="lax"
    )

@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="새 사용자 계정을 생성합니다",
    responses=responses
)
async def register(
    request: UserRegisterRequest,
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session)
) -> AuthResponse:
    """사용자 회원가입"""
    client_ip = _get_client_ip(http_request)

    auth_service = AuthService(db)
    auth_response = await auth_service.register_user(request, client_ip)

    # JWT 토큰을 HttpOnly 쿠키에 저장
    _set_auth_cookie(response, auth_response.access_token)

    logger.info(f"회원가입 완료 | 사용자={request.email} | IP={client_ip}")
    return auth_response

@router.post(
    "/login",
    response_model=AuthResponse,
    summary="로그인",
    description="이메일과 비밀번호로 로그인합니다",
    responses=responses
)
async def login(
    request: UserLoginRequest,
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session)
) -> AuthResponse:
    """사용자 로그인"""
    client_ip = _get_client_ip(http_request)

    auth_service = AuthService(db)
    auth_response = await auth_service.login_user(request, client_ip)

    # JWT 토큰을 HttpOnly 쿠키에 저장
    _set_auth_cookie(response, auth_response.access_token)

    logger.info(f"로그인 완료 | 사용자={request.email} | IP={client_ip}")
    return auth_response

@router.post(
    "/logout",
    summary="로그아웃",
    description="현재 세션을 종료합니다",
    responses={200: {"description": "로그아웃 성공"}}
)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
) -> dict:
    """사용자 로그아웃"""
    client_ip = _get_client_ip(request)

    # 토큰 추출 및 블랙리스트 추가
    token = _get_token_from_request(request)
    if token:
        blacklist_token(token)

    # 쿠키 삭제
    _clear_auth_cookie(response)

    logger.info(f"로그아웃 완료 | 사용자={current_user.email} | IP={client_ip}")
    return {"message": "로그아웃되었습니다"}

@router.get(
    "/me",
    response_model=UserResponse,
    summary="현재 사용자 정보",
    description="로그인한 사용자의 정보를 반환합니다",
    responses=responses
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
) -> UserResponse:
    """현재 사용자 정보 조회"""
    user_data = {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "tier": current_user.tier.value,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
        "is_superuser": current_user.is_superuser,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
        "last_login_at": current_user.last_login_at,
        "display_name": current_user.full_name if current_user.full_name else current_user.email.split("@")[0]
    }
    return UserResponse(**user_data)

@router.post(
    "/change-password",
    summary="비밀번호 변경",
    description="현재 비밀번호를 확인 후 새 비밀번호로 변경합니다",
    responses=responses
)
async def change_password(
    request: PasswordChangeRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """비밀번호 변경"""
    client_ip = _get_client_ip(http_request)

    auth_service = AuthService(db)
    await auth_service.change_password(
        current_user,
        request.current_password,
        request.new_password,
        client_ip
    )

    return {"message": "비밀번호가 변경되었습니다"}

@router.get(
    "/token-info",
    response_model=TokenInfo,
    summary="토큰 정보 조회",
    description="현재 토큰의 상세 정보를 반환합니다"
)
async def get_token_info(request: Request) -> TokenInfo:
    """토큰 정보 조회"""
    from ..core.jwt import jwt_manager

    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 없습니다"
        )

    token_info = jwt_manager.get_token_info(token)
    return TokenInfo(**token_info)