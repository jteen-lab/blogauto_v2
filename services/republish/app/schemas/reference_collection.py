"""
참조자료 수집 관련 Pydantic 스키마

Features:
- 네이버 웹문서 검색 결과 스키마
- 크롤링 결과 스키마
- 문서 요약 스키마
- API 요청/응답 스키마
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============ 검색 결과 스키마 ============

class SearchResult(BaseModel):
    """네이버 웹문서 검색 결과 항목"""
    title: str = Field(..., description="검색 결과 제목")
    link: str = Field(..., description="URL")
    description: str = Field(default="", description="검색 결과 설명")
    bloggername: Optional[str] = Field(None, description="블로거 이름")
    bloggerlink: Optional[str] = Field(None, description="블로거 URL")
    postdate: Optional[str] = Field(None, description="작성일 (YYYYMMDD)")


class SearchResponse(BaseModel):
    """검색 API 응답"""
    success: bool
    total: int = Field(default=0, description="전체 검색 결과 수")
    results: List[SearchResult] = Field(default_factory=list)
    error: Optional[str] = None


# ============ 크롤링 결과 스키마 ============

class CrawledDocument(BaseModel):
    """크롤링된 단일 문서"""
    url: str = Field(..., description="문서 URL")
    domain: str = Field(..., description="도메인")
    title: Optional[str] = Field(None, description="문서 제목")
    content: str = Field(..., description="문서 본문")
    content_length: int = Field(..., description="본문 길이")
    crawled_at: datetime = Field(default_factory=datetime.now)


class CrawlResult(BaseModel):
    """크롤링 전체 결과"""
    total_attempted: int = Field(default=0, description="시도한 URL 수")
    total_success: int = Field(default=0, description="성공한 수")
    total_failed: int = Field(default=0, description="실패한 수")
    documents: List[CrawledDocument] = Field(default_factory=list)
    has_minimum: bool = Field(default=False, description="최소 개수 충족 여부")


class CrawlLogItem(BaseModel):
    """크롤링 로그 항목 (응답용)"""
    url: str
    domain: Optional[str] = None
    status: str = Field(..., description="success | failed | timeout | blocked | skipped")
    error_message: Optional[str] = None
    content_length: Optional[int] = None
    crawl_duration_ms: Optional[int] = None
    crawled_at: datetime

    class Config:
        from_attributes = True


# ============ 요약 스키마 ============

class DocumentSummary(BaseModel):
    """문서 요약 결과"""
    url: str = Field(..., description="원본 URL")
    title: Optional[str] = Field(None, description="문서 제목")
    original_length: int = Field(..., description="원본 길이")
    summary: str = Field(..., description="요약 내용")
    summary_length: int = Field(..., description="요약 길이")
    is_ai_summary: bool = Field(default=True, description="AI 요약 여부")


# ============ API 요청/응답 스키마 ============

class CollectRequest(BaseModel):
    """참조자료 수집 요청"""
    search_query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="검색어"
    )
    title_id: Optional[int] = Field(None, description="연결할 메인 타이틀 ID")


class CollectResponse(BaseModel):
    """참조자료 수집 시작 응답"""
    reference_id: int = Field(..., description="생성된 참조자료 ID")
    status: str = Field(..., description="상태")
    message: str = Field(..., description="메시지")


class StatusResponse(BaseModel):
    """수집 상태 응답"""
    reference_id: int
    status: str = Field(..., description="pending | collecting | completed | failed")
    progress: dict = Field(
        default_factory=dict,
        description="진행 상황 {searched, crawled, failed}"
    )
    created_at: datetime
    completed_at: Optional[datetime] = None


class ReferenceResult(BaseModel):
    """참조자료 수집 결과 응답"""
    reference_id: int
    search_query: str
    status: str
    total_searched: int
    total_crawled: int
    total_failed: int
    selected_references: List[DocumentSummary] = Field(default_factory=list)
    crawl_logs: List[CrawlLogItem] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


class ReferenceListItem(BaseModel):
    """참조자료 목록 항목"""
    id: int
    search_query: str
    status: str
    total_crawled: int
    selected_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    title_id: Optional[int] = None

    class Config:
        from_attributes = True
