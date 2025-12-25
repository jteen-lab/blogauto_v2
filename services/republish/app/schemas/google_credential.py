"""
Google 계정 인증 정보 스키마

Features:
- Google 계정 생성/조회 스키마
- 토큰 정보 포함/제외 버전
- 보안을 위한 민감 정보 필터링
"""
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime
from typing import Optional, List


class GoogleCredentialBase(BaseModel):
    """Google 계정 기본 스키마"""
    google_email: EmailStr


class GoogleCredentialCreate(GoogleCredentialBase):
    """Google 계정 생성 스키마"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in_seconds: Optional[int] = None

    @validator('access_token')
    def validate_access_token(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError('유효한 액세스 토큰이 필요합니다')
        return v.strip()

    @validator('expires_in_seconds')
    def validate_expires_in(cls, v):
        if v is not None and v <= 0:
            raise ValueError('만료 시간은 양수여야 합니다')
        return v


class GoogleCredentialUpdate(BaseModel):
    """Google 계정 업데이트 스키마"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in_seconds: Optional[int] = None

    @validator('access_token')
    def validate_access_token(cls, v):
        if v is not None and (not v or len(v.strip()) < 10):
            raise ValueError('유효한 액세스 토큰이 필요합니다')
        return v.strip() if v else None

    @validator('expires_in_seconds')
    def validate_expires_in(cls, v):
        if v is not None and v <= 0:
            raise ValueError('만료 시간은 양수여야 합니다')
        return v


class GoogleCredentialResponse(GoogleCredentialBase):
    """Google 계정 응답 스키마 (민감 정보 제외)"""
    id: int
    user_id: int
    is_token_expired: bool
    token_expires_in_minutes: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GoogleCredentialWithToken(GoogleCredentialResponse):
    """Google 계정 응답 스키마 (토큰 포함)"""
    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None

    class Config:
        from_attributes = True


class GoogleCredentialListResponse(BaseModel):
    """Google 계정 목록 응답 스키마"""
    accounts: List[GoogleCredentialResponse]
    total: int

    class Config:
        from_attributes = True


class GoogleCredentialStatus(BaseModel):
    """Google 계정 상태 스키마"""
    credential_id: int
    google_email: EmailStr
    is_token_valid: bool
    is_token_expired: bool
    needs_refresh: bool
    token_expires_in_minutes: Optional[int]
    last_checked: datetime

    class Config:
        from_attributes = True