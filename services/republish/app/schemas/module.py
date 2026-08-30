"""
모듈 관련 스키마

Features:
- 모듈 생성/수정/조회 요청/응답 스키마
- 모듈 타입별 설정 지원
- GP 통합: 레거시 스케줄/간격 필드 제거 (029 마이그레이션)
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator


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
    """모듈 응답.

    Note:
        Phase E (2026-06-02) 부터 ``legacy_bulk_warning`` 필드가 추가되었다.
        기존 ``collect`` 모듈의 ``settings.enable_bulk_collect=True`` 가
        남아 있는 경우 True 로 채워져 UI에서 마이그레이션 안내 배지를
        노출할 수 있도록 한다. 응답 호환을 위해 기본값은 False 다.
    """
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

    # 프롬프트 모듈에 적용된 프리셋 이름(플로우 화면·1회 생성 버튼 표시용).
    # 서버가 한 번에 정한다 — 화면마다 각자 추론하면 답이 달라진다.
    prompt_preset: Optional[str] = Field(
        default=None,
        description="적용된 프롬프트 프리셋 이름. 판정 불가 시 None",
    )
    adsense_approval_preset_label: Optional[str] = Field(
        default=None,
        description="승인 전에만 사용하는 프리셋 이름. 지정 없으면 None",
    )

    # Phase E: 레거시 대량 수집 옵션 사용 중인지 표시
    legacy_bulk_warning: Optional[bool] = Field(
        default=False,
        description=(
            "레거시 collect 모듈에 enable_bulk_collect=True 가 남아 있는지 여부. "
            "True 이면 사용자 마이그레이션 안내 필요."
        ),
    )

    @model_validator(mode="after")
    def _fill_prompt_preset(self) -> "ModuleResponse":
        """settings 에서 적용된 프리셋 이름을 채운다.

        서비스 계층이 아니라 스키마에서 채우는 이유: 모듈 응답은 목록·상세·
        플로우 상세 세 경로로 나가는데, 세 곳에서 각자 대입하면 한 곳이
        빠졌을 때 화면마다 다르게 보인다. 여기서 채우면 경로와 무관하게
        같은 값이 나간다. settings 는 이미 로딩돼 있어 추가 쿼리가 없다.
        """
        code = getattr(self.module_type, "code", "")
        if code not in ("prompt", "generate"):
            return self
        try:
            from ..services.prompt_builder.describe import (
                describe, describe_approval,
            )
            self.prompt_preset = describe(self.settings) or None
            self.adsense_approval_preset_label = (
                describe_approval(self.settings) or None
            )
        except Exception:  # pragma: no cover - 표시용이라 실패해도 응답은 나가야 한다
            pass
        return self

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
