"""
인증 비즈니스 로직

Features:
- 사용자 등록/로그인
- 비밀번호 검증
- JWT 토큰 관리
- 보안 이벤트 로깅
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from typing import Optional, Tuple
from datetime import timedelta

from ..models.user import User, UserTier
from ..schemas.auth import UserRegisterRequest, UserLoginRequest, AuthResponse, UserResponse
from ..core.password import hash_password, verify_password, validate_password_strength
from ..core.jwt import create_access_token
from ..core.config import settings
from ..core.logger import get_logger, log_auth_attempt, log_security_event

logger = get_logger("auth_service", "auth.log")

class AuthService:
    """인증 서비스 클래스"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def register_user(self, request: UserRegisterRequest,
                           ip_address: str) -> AuthResponse:
        """
        사용자 회원가입

        Args:
            request: 회원가입 요청 데이터
            ip_address: 클라이언트 IP

        Returns:
            인증 응답 (토큰 + 사용자 정보)

        Raises:
            HTTPException: 이미 존재하는 이메일 등
        """
        logger.info(f"회원가입 시도 | 이메일={request.email} | IP={ip_address}")

        # 이메일 중복 확인
        await self._check_email_exists(request.email)

        # 비밀번호 강도 검증
        is_valid, errors = validate_password_strength(request.password)
        if not is_valid:
            log_security_event(logger, "WEAK_PASSWORD_ATTEMPT", {
                "email": request.email,
                "ip": ip_address,
                "errors": errors
            })
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"비밀번호가 요구사항을 만족하지 않습니다: {', '.join(errors)}"
            )

        try:
            # 비밀번호 해싱
            hashed_password = hash_password(request.password)

            # 사용자 생성
            user = User(
                email=request.email,
                hashed_password=hashed_password,
                full_name=request.full_name,
                tier=UserTier.FREE,
                is_active=True,
                is_verified=False  # 이메일 인증 필요
            )

            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

            # 로그인 처리
            return await self._create_auth_response(user, ip_address, "회원가입")

        except Exception as e:
            await self.db.rollback()
            logger.error(f"회원가입 실패 | 이메일={request.email} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="회원가입 처리 중 오류가 발생했습니다"
            )

    async def login_user(self, request: UserLoginRequest,
                        ip_address: str) -> AuthResponse:
        """
        사용자 로그인

        Args:
            request: 로그인 요청 데이터
            ip_address: 클라이언트 IP

        Returns:
            인증 응답 (토큰 + 사용자 정보)

        Raises:
            HTTPException: 인증 실패
        """
        logger.info(f"로그인 시도 | 이메일={request.email} | IP={ip_address}")

        # 사용자 조회
        user = await self._get_user_by_email(request.email)
        if not user:
            log_auth_attempt(logger, request.email, ip_address, False, "사용자 없음")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 잘못되었습니다"
            )

        # 계정 상태 확인
        if not user.is_active:
            log_auth_attempt(logger, request.email, ip_address, False, "비활성 계정")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="비활성화된 계정입니다. 관리자에게 문의하세요"
            )

        # 비밀번호 검증
        if not verify_password(request.password, user.hashed_password):
            log_auth_attempt(logger, request.email, ip_address, False, "비밀번호 불일치")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 잘못되었습니다"
            )

        # 로그인 성공 처리
        return await self._create_auth_response(user, ip_address, "로그인")

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        ID로 사용자 조회

        Args:
            user_id: 사용자 ID

        Returns:
            사용자 객체 또는 None
        """
        query = select(User).where(User.id == user_id, User.is_active == True)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def change_password(self, user: User, current_password: str,
                             new_password: str, ip_address: str) -> bool:
        """
        비밀번호 변경

        Args:
            user: 사용자 객체
            current_password: 현재 비밀번호
            new_password: 새 비밀번호
            ip_address: 클라이언트 IP

        Returns:
            변경 성공 여부

        Raises:
            HTTPException: 현재 비밀번호 불일치 등
        """
        logger.info(f"비밀번호 변경 시도 | 사용자={user.email} | IP={ip_address}")

        # 현재 비밀번호 검증
        if not verify_password(current_password, user.hashed_password):
            log_security_event(logger, "INVALID_PASSWORD_CHANGE", {
                "user_id": user.id,
                "email": user.email,
                "ip": ip_address
            })
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다"
            )

        # 새 비밀번호 강도 검증
        is_valid, errors = validate_password_strength(new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"새 비밀번호가 요구사항을 만족하지 않습니다: {', '.join(errors)}"
            )

        try:
            # 새 비밀번호 해싱 및 저장
            user.hashed_password = hash_password(new_password)
            await self.db.commit()

            log_security_event(logger, "PASSWORD_CHANGED", {
                "user_id": user.id,
                "email": user.email,
                "ip": ip_address
            })

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"비밀번호 변경 실패 | 사용자={user.email} | 오류={e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="비밀번호 변경 중 오류가 발생했습니다"
            )

    async def _check_email_exists(self, email: str) -> None:
        """이메일 중복 확인"""
        query = select(User).where(User.email == email)
        result = await self.db.execute(query)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            logger.warning(f"이메일 중복 | 이메일={email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이미 사용 중인 이메일입니다"
            )

    async def _get_user_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자 조회"""
        query = select(User).where(User.email == email)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _create_auth_response(self, user: User, ip_address: str,
                                  action: str) -> AuthResponse:
        """인증 응답 생성"""
        # 마지막 로그인 시간 업데이트
        user.update_last_login()
        await self.db.commit()

        # JWT 토큰 생성
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "tier": user.tier.value
        }

        access_token = create_access_token(token_data)

        # 성공 로깅
        log_auth_attempt(logger, user.email, ip_address, True)

        # 응답 생성
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_expire_minutes * 60,
            user=UserResponse.from_orm(user)
        )