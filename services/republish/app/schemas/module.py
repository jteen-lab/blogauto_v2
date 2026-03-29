"""
모듈 관련 스키마

Features:
- 모듈 생성/수정/조회 요청/응답 스키마
- 모듈 타입별 설정 지원
- GP 통합: 레거시 스케줄/간격 필드 제거 (029 마이그레이션)
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ModuleTypeResponse(BaseModel):
    """모듈 타입 응답"""
    id: int
    code: str
    name: str
    icon: Optional[str] = None
    display_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class ModuleCreateRequest(BaseModel):
    """모듈 생성 요청

    Note:
        스케줄/간격/jitter/활성시간대 등 레거시 필드는 제거됨.
        모든 스케줄 제어는 Growth Profile(GP)에서 담당.
    """
    module_type_code: str = Field(..., description="모듈 타입 코드")
    name: str = Field(..., min_length=1, max_length=255, description="모듈 이름")
    description: Optional[str] = Field(None, max_length=500, description="모듈 설명")

    # 타입별 추가 설정
    settings: Dict[str, Any] = Field(default_factory=dict, description="타입별 설정")


class ModuleUpdateRequest(BaseModel):
    """모듈 수정 요청

    Note:
        description 필드는 빈 문자열("")로 설정하면 설명을 삭제합니다.
        None은 필드를 업데이트하지 않음을 의미합니다.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)

    # 타입별 추가 설정
    settings: Optional[Dict[str, Any]] = None


class ModuleResponse(BaseModel):
    """모듈 응답"""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    module_type: ModuleTypeResponse

    # 타입별 설정
    settings: Dict[str, Any] = Field(default_factory=dict, description="타입별 설정")

    # 메타 정보
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModuleDetailResponse(ModuleResponse):
    """모듈 상세 응답"""
    # ModuleResponse의 모든 필드를 상속
    # 추가 상세 필드가 필요하면 여기에 추가
    pass


class ModuleListResponse(BaseModel):
    """모듈 목록 응답"""
    modules: List[ModuleResponse]
    total: int
    page: int
    size: int
    has_next: bool
