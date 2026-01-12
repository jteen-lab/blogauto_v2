"""
URL 이력 관련 Pydantic 스키마
"""
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator

# ============ BlogUrlHistory ============
class BlogUrlHistoryBase(BaseModel):
    blog_url: str = Field(..., max_length=1000)
    blog_platform: str = Field(default="other", pattern="^(naver|tistory|wordpress|other)$")
    blog_name: Optional[str] = Field(None, max_length=200)
    hold_days: int = Field(default=30, ge=1, le=365)

class BlogUrlHistoryCreate(BlogUrlHistoryBase):
    total_posts_count: int = 0
    @field_validator('blog_url')
    @classmethod
    def normalize_url(cls, v: str) -> str:
        """URL 정규화 (trailing slash 제거)"""
        return v.rstrip('/')

class BlogUrlHistoryUpdate(BaseModel):
    blog_name: Optional[str] = Field(None, max_length=200)
    hold_days: Optional[int] = Field(None, ge=1, le=365)
    is_active: Optional[bool] = None
    total_posts_count: Optional[int] = None

class BlogUrlHistoryResponse(BlogUrlHistoryBase):
    id: int
    total_posts_count: int
    collected_posts_count: int
    collection_count: int
    last_collected_at: datetime
    next_collection_date: datetime
    is_active: bool
    last_error: Optional[str]
    error_count: int
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class BlogUrlHistoryCheck(BaseModel):
    """URL 수집 가능 여부 체크 응답"""
    blog_url: str
    exists: bool
    can_collect: bool
    next_collection_date: Optional[datetime] = None
    reason: Optional[str] = None

class BlogUrlHistoryStats(BaseModel):
    """URL 이력 통계"""
    total_urls: int
    active_urls: int
    collectible_urls: int
    by_platform: Dict[str, int]
