"""
제목 관련 Pydantic 스키마
- TitleGroup / MainTitle / TempTitle CRUD 스키마
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

# ============ TitleGroup ============
class TitleGroupBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True

class TitleGroupCreate(TitleGroupBase):
    pass

class TitleGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    representative_title_id: Optional[int] = None
    is_active: Optional[bool] = None

class TitleGroupResponse(TitleGroupBase):
    id: int
    representative_title_id: Optional[int]
    member_count: int
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

# ============ MainTitle ============
class MainTitleBase(BaseModel):
    title: str = Field(..., max_length=500)
    category_id: Optional[int] = None
    status: str = Field(default="available", pattern="^(available|matched|used|archived)$")

class MainTitleCreate(MainTitleBase):
    source_temp_title_id: Optional[int] = None
    source_url: Optional[str] = Field(None, max_length=1000)

class MainTitleUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    is_group_representative: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(available|matched|used|archived)$")

class MainTitleResponse(MainTitleBase):
    id: int
    group_id: Optional[int]
    is_group_representative: bool
    matched_count: int
    use_count: int
    last_used_at: Optional[datetime]
    source_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class MainTitleWithGroup(MainTitleResponse):
    group: Optional[TitleGroupResponse] = None

class TitleGroupWithTitles(TitleGroupResponse):
    titles: List[MainTitleResponse] = []

# ============ TempTitle ============
class TempTitleBase(BaseModel):
    title: str = Field(..., max_length=500)
    source_blog_url: str = Field(..., max_length=1000)
    source_post_url: str = Field(..., max_length=1000)
    collection_stage: str = Field(..., pattern="^(keyword_search|blog_crawl)$")

class TempTitleCreate(TempTitleBase):
    source_keyword_id: Optional[int] = None

class TempTitleBulkCreate(BaseModel):
    titles: List[TempTitleCreate]

class TempTitleUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(new|filtered|categorized|moved|duplicate)$")
    filter_reason: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    category_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

class TempTitleResponse(TempTitleBase):
    id: int
    source_keyword_id: Optional[int]
    status: str
    filter_reason: Optional[str]
    category_id: Optional[int]
    category_confidence: Optional[float]
    similar_title_id: Optional[int]
    similarity_score: Optional[float]
    moved_to_main_id: Optional[int]
    moved_at: Optional[datetime]
    created_at: datetime
    processed_at: Optional[datetime]
    class Config:
        from_attributes = True

class TempTitleFilter(BaseModel):
    title_id: int
    is_filtered: bool
    filter_reason: Optional[str] = None
    filter_keywords: List[str] = []

class TempTitleSimilarity(BaseModel):
    title_id: int
    similar_title_id: Optional[int]
    similarity_score: float
    is_duplicate: bool
    suggested_group_id: Optional[int]
