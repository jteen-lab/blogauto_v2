"""
그룹 스키마
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class GroupCreateRequest(BaseModel):
    """그룹 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True
    profile_ids: List[int] = Field(default_factory=list)
    blog_ids: List[int] = Field(default_factory=list)


class GroupUpdateRequest(BaseModel):
    """그룹 수정 요청"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    profile_ids: Optional[List[int]] = None
    blog_ids: Optional[List[int]] = None


class GroupResponse(BaseModel):
    """그룹 응답"""
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    profile_count: int = 0
    blog_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class GroupDetailResponse(GroupResponse):
    """그룹 상세 응답"""
    profiles: List[dict] = Field(default_factory=list)
    blogs: List[dict] = Field(default_factory=list)


class GroupBlogAssignRequest(BaseModel):
    """그룹에 블로그 할당 요청"""
    blog_ids: List[int]
