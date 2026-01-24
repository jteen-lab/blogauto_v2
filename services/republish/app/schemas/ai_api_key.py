"""
AI API 키 다계정 관리 스키마

Features:
- API 키 CRUD 요청/응답 스키마
- 우선순위 변경 스키마
- 유효성 검증
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AIProvider(str, Enum):
    """AI 서비스 제공자"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    NANOBANANA = "nanobanana"  # Nano Banana (이미지 생성 - Gemini 기반)


class AIKeyStatus(str, Enum):
    """API 키 상태"""
    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    DISABLED = "disabled"


class AIApiKeyBase(BaseModel):
    """AI API 키 기본 스키마"""
    provider: AIProvider = Field(..., description="AI 서비스 제공자")
    label: str = Field(..., min_length=1, max_length=100, description="사용자 정의 라벨")


class AIApiKeyCreate(AIApiKeyBase):
    """AI API 키 생성 요청"""
    api_key: str = Field(..., min_length=1, max_length=512, description="API 키")
    priority: int = Field(default=0, ge=0, description="우선순위 (낮을수록 우선)")

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """API 키 유효성 검증"""
        v = v.strip()
        if not v:
            raise ValueError("API 키는 필수입니다")
        if "****" in v:
            raise ValueError("마스킹된 API 키는 사용할 수 없습니다")
        return v


class AIApiKeyUpdate(BaseModel):
    """AI API 키 수정 요청"""
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = Field(None, min_length=1, max_length=512)
    priority: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: Optional[str]) -> Optional[str]:
        """API 키 유효성 검증"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if "****" in v:
            # 마스킹된 키는 무시 (기존 값 유지)
            return None
        return v


class AIApiKeyPriorityUpdate(BaseModel):
    """우선순위 일괄 변경 요청"""
    priorities: List[dict] = Field(
        ...,
        description="[{id: 1, priority: 0}, {id: 2, priority: 1}, ...]"
    )

    @field_validator('priorities')
    @classmethod
    def validate_priorities(cls, v: List[dict]) -> List[dict]:
        """우선순위 목록 유효성 검증"""
        for item in v:
            if 'id' not in item or 'priority' not in item:
                raise ValueError("각 항목에 id와 priority가 필요합니다")
            if not isinstance(item['id'], int) or item['id'] < 1:
                raise ValueError("id는 양의 정수여야 합니다")
            if not isinstance(item['priority'], int) or item['priority'] < 0:
                raise ValueError("priority는 0 이상의 정수여야 합니다")
        return v


class AIApiKeyResponse(AIApiKeyBase):
    """AI API 키 응답"""
    id: int
    user_id: int
    api_key: str = Field(..., description="마스킹된 API 키")
    provider_display_name: str
    priority: int
    is_active: bool
    is_available: bool
    status: AIKeyStatus
    usage_count: int
    error_count: int
    last_used_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIApiKeyListResponse(BaseModel):
    """AI API 키 목록 응답"""
    keys: List[AIApiKeyResponse]
    total: int
    by_provider: dict = Field(
        default_factory=dict,
        description="제공자별 키 개수"
    )


class AIApiKeyStatusUpdate(BaseModel):
    """API 키 상태 업데이트 (내부용)"""
    status: AIKeyStatus
    error_message: Optional[str] = None


class AvailableKeyResponse(BaseModel):
    """사용 가능한 키 조회 응답"""
    id: int
    provider: AIProvider
    label: str
    priority: int
    api_key: str = Field(..., description="실제 API 키 (내부 사용)")

    class Config:
        from_attributes = True
