"""
인증 관련 Pydantic 스키마

Features:
- 요청/응답 데이터 검증
- 자동 문서화 지원
- 타입 안전성
- 에러 메시지 한글화
"""
from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional
from datetime import datetime

from ..models.user import UserTier

class UserRegisterRequest(BaseModel):
    """회원가입 요청 스키마"""

    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., min_length=8, max_length=128, description="비밀번호 (8-128자)")
    full_name: Optional[str] = Field(None, max_length=100, description="전체 이름")

    @validator("password")
    def validate_password(cls, v: str) -> str:
        """비밀번호 강도 검증"""
        if not any(c.islower() for c in v):
            raise ValueError("소문자를 포함해야 합니다")

        if not any(c.isupper() for c in v):
            raise ValueError("대문자를 포함해야 합니다")

        if not any(c.isdigit() for c in v):
            raise ValueError("숫자를 포함해야 합니다")

        return v

    @validator("full_name")
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        """이름 검증"""
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePassword123",
                "full_name": "홍길동"
            }
        }

class UserLoginRequest(BaseModel):
    """로그인 요청 스키마"""

    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., description="비밀번호")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePassword123"
            }
        }

class UserResponse(BaseModel):
    """사용자 정보 응답 스키마"""

    id: int = Field(..., description="사용자 ID")
    email: EmailStr = Field(..., description="이메일 주소")
    full_name: Optional[str] = Field(None, description="전체 이름")
    tier: str = Field(..., description="사용자 등급")
    is_active: bool = Field(..., description="활성화 상태")
    is_verified: bool = Field(..., description="이메일 인증 여부")
    is_superuser: bool = Field(False, description="관리자 권한 여부")
    created_at: Optional[datetime] = Field(None, description="계정 생성일")
    updated_at: Optional[datetime] = Field(None, description="정보 수정일")
    last_login_at: Optional[datetime] = Field(None, description="마지막 로그인")
    display_name: str = Field(..., description="표시 이름")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "email": "user@example.com",
                "full_name": "홍길동",
                "tier": "free",
                "is_active": True,
                "is_verified": True,
                "created_at": "2024-01-15T10:30:45Z",
                "updated_at": "2024-01-15T10:30:45Z",
                "last_login_at": "2024-01-15T14:20:30Z",
                "display_name": "홍길동"
            }
        }

class AuthResponse(BaseModel):
    """인증 성공 응답 스키마"""

    access_token: str = Field(..., description="액세스 토큰")
    token_type: str = Field(default="bearer", description="토큰 타입")
    expires_in: int = Field(..., description="토큰 만료 시간 (초)")
    user: UserResponse = Field(..., description="사용자 정보")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 604800,
                "user": {
                    "id": 1,
                    "email": "user@example.com",
                    "full_name": "홍길동",
                    "tier": "free",
                    "is_active": True,
                    "is_verified": True,
                    "created_at": "2024-01-15T10:30:45Z",
                    "updated_at": "2024-01-15T10:30:45Z",
                    "last_login_at": "2024-01-15T14:20:30Z",
                    "display_name": "홍길동"
                }
            }
        }

class TokenInfo(BaseModel):
    """토큰 정보 스키마"""

    user_id: Optional[int] = Field(None, description="사용자 ID")
    email: Optional[str] = Field(None, description="이메일")
    issued_at: Optional[datetime] = Field(None, description="토큰 발급 시간")
    expires_at: Optional[datetime] = Field(None, description="토큰 만료 시간")
    is_expired: bool = Field(False, description="만료 여부")
    is_blacklisted: bool = Field(False, description="블랙리스트 여부")

class ErrorResponse(BaseModel):
    """에러 응답 스키마"""

    error: str = Field(..., description="에러 코드")
    message: str = Field(..., description="에러 메시지")
    details: Optional[dict] = Field(None, description="상세 정보")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "INVALID_CREDENTIALS",
                "message": "이메일 또는 비밀번호가 잘못되었습니다",
                "details": None
            }
        }

class PasswordChangeRequest(BaseModel):
    """비밀번호 변경 요청 스키마"""

    current_password: str = Field(..., description="현재 비밀번호")
    new_password: str = Field(..., min_length=8, max_length=128, description="새 비밀번호")

    @validator("new_password")
    def validate_new_password(cls, v: str) -> str:
        """새 비밀번호 검증"""
        if not any(c.islower() for c in v):
            raise ValueError("소문자를 포함해야 합니다")

        if not any(c.isupper() for c in v):
            raise ValueError("대문자를 포함해야 합니다")

        if not any(c.isdigit() for c in v):
            raise ValueError("숫자를 포함해야 합니다")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "OldPassword123",
                "new_password": "NewSecurePassword456"
            }
        }