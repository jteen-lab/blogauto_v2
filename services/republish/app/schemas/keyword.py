"""
키워드 관련 Pydantic 스키마

Features:
- KeywordCategory CRUD 스키마
- SeedKeyword CRUD 스키마
- CollectedKeyword CRUD 스키마
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ KeywordCategory ============

class KeywordCategoryBase(BaseModel):
    """키워드 카테고리 기본"""
    name: str = Field(..., max_length=100)
    parent_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class KeywordCategoryCreate(KeywordCategoryBase):
    """키워드 카테고리 생성"""
    pass


class KeywordCategoryUpdate(BaseModel):
    """키워드 카테고리 수정"""
    name: Optional[str] = Field(None, max_length=100)
    parent_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class KeywordCategoryResponse(KeywordCategoryBase):
    """키워드 카테고리 응답"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KeywordCategoryTree(KeywordCategoryResponse):
    """계층 구조 포함 응답"""
    children: List["KeywordCategoryTree"] = []


# ============ SeedKeyword ============

class SeedKeywordBase(BaseModel):
    """시드 키워드 기본"""
    keyword: str = Field(..., max_length=200)
    category_id: Optional[int] = None
    source_type: str = Field(
        default="user_input",
        pattern="^(user_input|trend|extracted)$"
    )
    is_active: bool = True
    priority: int = 0


class SeedKeywordCreate(SeedKeywordBase):
    """시드 키워드 생성"""
    pass


class SeedKeywordUpdate(BaseModel):
    """시드 키워드 수정"""
    keyword: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    source_type: Optional[str] = Field(
        None,
        pattern="^(user_input|trend|extracted)$"
    )
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class SeedKeywordResponse(SeedKeywordBase):
    """시드 키워드 응답"""
    id: int
    last_used_at: Optional[datetime]
    use_count: int
    created_at: datetime
    updated_at: datetime
    category: Optional[KeywordCategoryResponse] = None

    class Config:
        from_attributes = True


# ============ CollectedKeyword ============

class CollectedKeywordBase(BaseModel):
    """수집 키워드 기본"""
    keyword: str = Field(..., max_length=200)
    seed_keyword_id: int
    category_id: Optional[int] = None
    search_volume: Optional[int] = None
    competition: Optional[float] = Field(None, ge=0.0, le=1.0)


class CollectedKeywordCreate(CollectedKeywordBase):
    """수집 키워드 생성"""
    pass


class CollectedKeywordBulkCreate(BaseModel):
    """대량 생성용"""
    seed_keyword_id: int
    keywords: List[str]
    category_id: Optional[int] = None


class CollectedKeywordUpdate(BaseModel):
    """수집 키워드 수정"""
    category_id: Optional[int] = None
    search_volume: Optional[int] = None
    competition: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_processed: Optional[bool] = None


class CollectedKeywordResponse(CollectedKeywordBase):
    """수집 키워드 응답"""
    id: int
    is_processed: bool
    process_count: int
    last_processed_at: Optional[datetime]
    created_at: datetime
    seed_keyword: Optional[SeedKeywordResponse] = None
    category: Optional[KeywordCategoryResponse] = None

    class Config:
        from_attributes = True
