"""프롬프트 빌더 옵션 블록 CRUD 스키마."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_VALID_TYPES = {"persona", "reader", "pattern", "tone", "common"}


class PromptBlockCreate(BaseModel):
    """블록 생성 요청."""

    block_type: str = Field(..., description="persona|reader|pattern|tone|common")
    label: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1)
    code: Optional[str] = Field(
        default=None, description="미지정 시 자동 생성", max_length=50,
    )
    cluster: Optional[str] = Field(default=None, max_length=20)
    sort_order: int = 0
    is_active: bool = True

    @field_validator("block_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"block_type 은 {_VALID_TYPES} 중 하나여야 합니다")
        return v


class PromptBlockUpdate(BaseModel):
    """블록 수정 요청(부분 수정)."""

    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    body: Optional[str] = Field(default=None, min_length=1)
    cluster: Optional[str] = Field(default=None, max_length=20)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class PromptBlockResponse(BaseModel):
    """블록 응답."""

    id: int
    block_type: str
    code: str
    label: str
    body: str
    cluster: Optional[str] = None
    sort_order: int
    is_active: bool
    is_builtin: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
