"""
제목 관련 Pydantic 스키마
- TitleGroup / MainTitle / TempTitle CRUD 스키마
- Phase C: 그룹 관리, 유사도 정보, 지역 정보 추가
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ TitleGroup ============
class TitleGroupBase(BaseModel):
    """TitleGroup 기본 스키마"""
    name: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    location: Optional[str] = Field(None, max_length=100, description="공통 지역명")
    main_keyword: Optional[str] = Field(None, max_length=200, description="공통 주제 키워드")
    is_active: bool = True


class TitleGroupCreate(TitleGroupBase):
    """TitleGroup 생성 스키마"""
    pass


class TitleGroupUpdate(BaseModel):
    """TitleGroup 수정 스키마"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    location: Optional[str] = Field(None, max_length=100)
    main_keyword: Optional[str] = Field(None, max_length=200)
    representative_title_id: Optional[int] = None
    is_active: Optional[bool] = None


class TitleGroupResponse(TitleGroupBase):
    """TitleGroup 응답 스키마"""
    id: int
    group_uuid: str
    representative_title_id: Optional[int] = None
    representative_title: Optional[str] = None
    member_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ============ MainTitle ============
class MainTitleBase(BaseModel):
    """MainTitle 기본 스키마"""
    title: str = Field(..., max_length=500)
    category_id: Optional[int] = None
    topic_id: Optional[int] = None
    subtopic_id: Optional[int] = None
    status: str = Field(default="available", pattern="^(available|matched|used|archived)$")


class MainTitleCreate(MainTitleBase):
    """MainTitle 생성 스키마"""
    source: str = Field(default="manual", pattern="^(transfer|manual|crawl)$")
    source_temp_title_id: Optional[int] = None
    source_url: Optional[str] = Field(None, max_length=1000)
    location_info: Optional[str] = Field(None, description="지역 정보 JSON")
    keywords: Optional[str] = Field(None, description="키워드 JSON")


class MainTitleUpdate(BaseModel):
    """MainTitle 수정 스키마"""
    title: Optional[str] = Field(None, max_length=500)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    is_group_representative: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(available|matched|used|archived)$")


class CrawledPostInfo(BaseModel):
    """매칭된 크롤 포스트 간략 정보 (Phase 2-2)"""
    id: int
    title: str
    url: Optional[str] = None
    match_score: Optional[float] = None
    published_at: Optional[datetime] = None
    last_renewed_at: Optional[datetime] = None
    image_url: Optional[str] = None
    has_content: bool = False


class MainTitleResponse(MainTitleBase):
    """MainTitle 응답 스키마"""
    id: int
    group_id: Optional[int] = None
    is_group_representative: bool
    similarity_score: Optional[float] = None
    grouped_at: Optional[datetime] = None
    location_info: Optional[str] = None
    keywords: Optional[str] = None
    matched_count: int
    use_count: int
    last_used_at: Optional[datetime] = None
    source: str
    source_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # 추가 정보 (API에서 설정)
    category_name: Optional[str] = None
    category_path: Optional[str] = None  # "주제 - 하위 주제" 형식
    topic_name: Optional[str] = None
    subtopic_name: Optional[str] = None
    group_name: Optional[str] = None
    group_member_count: Optional[int] = None  # 그룹 멤버 수 (활성 그룹 표시용)
    # Phase 2-2: 블로그별 매칭 포스트 정보
    matched_crawled_post: Optional[CrawledPostInfo] = None

    class Config:
        from_attributes = True


class MainTitleWithGroup(MainTitleResponse):
    """MainTitle + 그룹 정보 응답"""
    group: Optional[TitleGroupResponse] = None


class TitleGroupWithTitles(TitleGroupResponse):
    """TitleGroup + 제목 목록 응답"""
    titles: List[MainTitleResponse] = []


class MainTitleListResponse(BaseModel):
    """MainTitle 목록 응답 (페이지네이션)"""
    items: List[MainTitleResponse]
    total: int
    page: int
    size: int
    has_next: bool


class TitleGroupListResponse(BaseModel):
    """TitleGroup 목록 응답 (페이지네이션)"""
    items: List[TitleGroupResponse]
    total: int
    page: int
    size: int
    has_next: bool


# ============ 그룹 관리 요청 스키마 ============
class ChangeRepresentativeRequest(BaseModel):
    """대표 제목 변경 요청"""
    new_representative_id: int


class AddToGroupRequest(BaseModel):
    """그룹에 제목 추가 요청"""
    title_ids: List[int]


class RemoveFromGroupRequest(BaseModel):
    """그룹에서 제목 제거 요청"""
    title_ids: List[int]


class MergeGroupsRequest(BaseModel):
    """그룹 병합 요청"""
    source_group_ids: List[int]
    target_group_id: int

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
