"""
플로우 관련 스키마

Features:
- 플로우 생성/수정/조회 요청/응답 스키마
- 모듈 및 블로그 관계 포함
- 실행 순서 관리
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

from .module import ModuleResponse


class FlowStatus(str, Enum):
    """플로우 상태"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"


class FlowCreateRequest(BaseModel):
    """플로우 생성 요청"""

    name: str = Field(..., min_length=1, max_length=255, description="플로우 이름")
    description: Optional[str] = Field(None, max_length=500, description="플로우 설명")
    is_active: bool = Field(False, description="활성화 여부")

    # 호환성을 위한 status 필드 (is_active에서 변환됨)
    @property
    def status(self) -> FlowStatus:
        return FlowStatus.ACTIVE if self.is_active else FlowStatus.INACTIVE

    # 초기 모듈/블로그 설정 (선택사항)
    module_ids: List[int] = Field(default_factory=list, description="초기 모듈 ID 목록")
    blog_ids: List[int] = Field(default_factory=list, description="초기 블로그 ID 목록")


class FlowUpdateRequest(BaseModel):
    """플로우 기본 정보 수정 요청"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = Field(None, description="활성화 여부")
    module_ids: Optional[List[int]] = Field(
        None, description="모듈 ID 목록 (전체 교체)"
    )
    blog_ids: Optional[List[int]] = Field(
        None, description="블로그 ID 목록 (전체 교체)"
    )

    @property
    def status(self) -> Optional[str]:
        if self.is_active is None:
            return None
        return "active" if self.is_active else "inactive"


class FlowModuleAddRequest(BaseModel):
    """플로우에 모듈 추가 요청"""

    module_ids: List[int] = Field(..., min_items=1, description="추가할 모듈 ID 목록")
    execution_orders: Optional[List[int]] = Field(
        None, description="실행 순서 (지정하지 않으면 자동 할당)"
    )


class FlowBlogAddRequest(BaseModel):
    """플로우에 블로그 추가 요청"""

    blog_ids: List[int] = Field(..., min_items=1, description="추가할 블로그 ID 목록")
    validate_slots: bool = Field(True, description="Blogger 블로그 슬롯 검증 여부")


class BlogInfo(BaseModel):
    """블로그 기본 정보"""

    id: int
    name: str
    url: str
    platform: str
    is_active: bool

    class Config:
        from_attributes = True


class FlowModuleInfo(BaseModel):
    """플로우-모듈 연결 정보"""

    id: int
    module: ModuleResponse
    execution_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class FlowBlogInfo(BaseModel):
    """플로우-블로그 연결 정보"""

    id: int
    blog: BlogInfo
    created_at: datetime

    class Config:
        from_attributes = True


class FlowResponse(BaseModel):
    """플로우 응답"""

    id: int
    user_id: int
    name: str
    description: Optional[str]
    status: str

    # 호환성을 위한 is_active 속성
    @property
    def is_active(self) -> bool:
        return self.status == "active"

    # 개수 정보
    module_count: int = 0
    blog_count: int = 0

    module_links: List[FlowModuleInfo] = Field(default_factory=list)
    blog_links: List[FlowBlogInfo] = Field(default_factory=list)

    # 다음 실행 예정 시간 (오토런에서 계산)
    next_execution: Optional[datetime] = None

    # 메타 정보
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class FlowDetailResponse(BaseModel):
    """플로우 상세 응답"""

    id: int
    user_id: int
    name: str
    description: Optional[str]
    status: str

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    module_count: int = 0
    blog_count: int = 0

    module_links: List[FlowModuleInfo] = Field(default_factory=list)
    blog_links: List[FlowBlogInfo] = Field(default_factory=list)

    last_execution: Optional[datetime] = None
    execution_count: int = 0
    success_rate: float = 0.0

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class FlowListResponse(BaseModel):
    """플로우 목록 응답"""

    flows: List[FlowResponse]
    total: int
    page: int
    size: int
    has_next: bool


class BlogAddResult(BaseModel):
    """플로우 블로그 추가 결과"""

    success_count: int
    total_requested: int
    failed_blogs: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Blogger 슬롯 예약 정보
    reserved_slots: List[Dict[str, Any]] = Field(default_factory=list)


class FlowBlogAddResult(BaseModel):
    """플로우 블로그 추가 결과 (하위 호환성)"""

    success_count: int
    failed_blogs: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str

    # Blogger 슬롯 예약 정보
    reserved_slots: List[Dict[str, Any]] = Field(default_factory=list)


class FlowModuleAddResult(BaseModel):
    """플로우 모듈 추가 결과"""

    success_count: int
    failed_modules: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str


class FlowStatusUpdateRequest(BaseModel):
    """플로우 상태 변경 요청 (오토런용)"""

    target_status: FlowStatus = Field(..., description="변경할 상태")
    reason: Optional[str] = Field(None, description="변경 이유")


class FlowExecutionInfo(BaseModel):
    """플로우 실행 정보 (오토런용)"""

    id: int
    name: str
    description: Optional[str] = None
    status: FlowStatus
    module_count: int
    blog_count: int

    # 모듈/블로그 연결 정보 (카드 표시용)
    module_links: List[Dict[str, Any]] = Field(default_factory=list)
    blog_links: List[Dict[str, Any]] = Field(default_factory=list)

    # 실행 관련 정보
    next_execution: Optional[datetime] = None
    last_execution: Optional[datetime] = None
    paused_at: Optional[datetime] = None

    # 통계
    execution_count: int = 0
    success_rate: float = 0.0

    class Config:
        from_attributes = True
