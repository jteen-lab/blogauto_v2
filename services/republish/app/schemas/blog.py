"""
블로그 스키마 정의

Features:
- 블로그 등록/수정/조회 스키마
- 플랫폼별 유효성 검증
- API 키 마스킹 처리
- 응답 스키마 분리
"""

from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum


class BlogPlatform(str, Enum):
    """블로그 플랫폼"""

    WORDPRESS = "wordpress"
    BLOGGER = "blogger"
    OTHER = "other"


class BlogCreateRequest(BaseModel):
    """블로그 등록 요청 스키마"""

    name: str = Field(..., min_length=1, max_length=100, description="블로그 이름")
    url: HttpUrl = Field(..., description="블로그 URL")
    platform: BlogPlatform = Field(..., description="플랫폼 타입")

    # API 인증 정보 (평문으로 받아서 암호화 저장)
    api_key: Optional[str] = Field(None, description="API 키")
    api_secret: Optional[str] = Field(None, description="API 시크릿")
    oauth_token: Optional[str] = Field(None, description="OAuth 토큰")

    # 발행 설정
    auto_publish: bool = Field(False, description="자동 발행 여부")
    republish_interval_hours: int = Field(
        24, ge=1, le=168, description="재발행 간격(시간)"
    )
    daily_limit: int = Field(10, ge=1, le=100, description="일일 발행 제한")

    # 콘텐츠 설정
    editor_type: str = Field("classic", max_length=50, description="에디터 타입")
    css_classes: Optional[Dict[str, str]] = Field(
        None, description="CSS 클래스 치환 규칙"
    )

    @validator("name")
    def validate_name(cls, v: str) -> str:
        """블로그 이름 검증"""
        v = v.strip()
        if len(v) < 1:
            raise ValueError("블로그 이름은 필수입니다")
        return v

    @validator("url")
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        """URL 검증"""
        url_str = str(v)
        if not (url_str.startswith("http://") or url_str.startswith("https://")):
            raise ValueError("유효한 HTTP/HTTPS URL이어야 합니다")
        return v

    @validator("api_key")
    def validate_api_key_for_platform(
        cls, v: Optional[str], values: Dict[str, Any]
    ) -> Optional[str]:
        """플랫폼별 API 키 검증"""
        platform = values.get("platform")

        if platform == BlogPlatform.WORDPRESS and not v:
            raise ValueError("WordPress 블로그는 API 키가 필요합니다")

        if platform == BlogPlatform.BLOGGER and not v:
            raise ValueError("Blogger 블로그는 API 키가 필요합니다")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "내 블로그",
                "url": "https://myblog.example.com",
                "platform": "wordpress",
                "api_key": "your-api-key",
                "api_secret": "your-api-secret",
                "auto_publish": True,
                "republish_interval_hours": 24,
                "daily_limit": 10,
                "editor_type": "classic",
            }
        }


class BlogUpdateRequest(BaseModel):
    """블로그 수정 요청 스키마"""

    name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="블로그 이름"
    )
    url: Optional[HttpUrl] = Field(None, description="블로그 URL")

    # API 인증 정보 (None이 아닌 경우만 업데이트)
    api_key: Optional[str] = Field(None, description="API 키")
    api_secret: Optional[str] = Field(None, description="API 시크릿")
    oauth_token: Optional[str] = Field(None, description="OAuth 토큰")

    # 발행 설정
    auto_publish: Optional[bool] = Field(None, description="자동 발행 여부")
    republish_interval_hours: Optional[int] = Field(
        None, ge=1, le=168, description="재발행 간격(시간)"
    )
    daily_limit: Optional[int] = Field(None, ge=1, le=100, description="일일 발행 제한")

    # 콘텐츠 설정
    editor_type: Optional[str] = Field(None, max_length=50, description="에디터 타입")
    css_classes: Optional[Dict[str, str]] = Field(
        None, description="CSS 클래스 치환 규칙"
    )

    @validator("name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """블로그 이름 검증"""
        if v is not None:
            v = v.strip()
            if len(v) < 1:
                raise ValueError("블로그 이름은 필수입니다")
        return v


class BlogResponse(BaseModel):
    """블로그 조회 응답 스키마"""

    id: int = Field(..., description="블로그 ID")
    user_id: int = Field(..., description="사용자 ID")
    name: str = Field(..., description="블로그 이름")
    url: str = Field(..., description="블로그 URL")
    platform: str = Field(..., description="플랫폼 타입")

    # 상태
    is_active: bool = Field(..., description="활성 상태")
    is_auto_supported: bool = Field(..., description="자동화 지원 여부")
    has_api_credentials: bool = Field(..., description="API 인증 정보 보유 여부")

    # 발행 설정
    auto_publish: bool = Field(..., description="자동 발행 여부")
    republish_interval_hours: int = Field(..., description="재발행 간격(시간)")
    daily_limit: int = Field(..., description="일일 발행 제한")

    # 콘텐츠 설정
    editor_type: str = Field(..., description="에디터 타입")
    css_classes: Optional[Dict[str, str]] = Field(
        None, description="CSS 클래스 치환 규칙"
    )

    # 메타 정보
    created_at: datetime = Field(..., description="생성일시")
    updated_at: datetime = Field(..., description="수정일시")

    class Config:
        from_attributes = True


class BlogListResponse(BaseModel):
    """블로그 목록 아이템 응답 스키마"""

    id: int = Field(..., description="블로그 ID")
    name: str = Field(..., description="블로그 이름")
    url: str = Field(..., description="블로그 URL")
    platform: str = Field(..., description="플랫폼 타입")
    is_active: bool = Field(..., description="활성 상태")
    auto_publish: bool = Field(..., description="자동 발행 여부")
    # 크롤링/매칭 상태 (Phase M-1)
    is_new_blog: bool = Field(True, description="신규 블로그 여부")
    crawl_status: str = Field("never", description="크롤링 상태")
    crawled_count: int = Field(0, description="크롤링된 포스트 수")
    matched_count: int = Field(0, description="매칭된 포스트 수")
    # GP 구간 분류용 - 플랫폼 누적 글 수
    total_post_count: int = Field(0, description="플랫폼 누적 발행 글 수")
    last_crawled_at: Optional[datetime] = Field(None, description="마지막 크롤링 시간")
    last_matched_at: Optional[datetime] = Field(None, description="마지막 매칭 시간")
    created_at: datetime = Field(..., description="생성일시")

    class Config:
        from_attributes = True


class BlogListWrapper(BaseModel):
    """블로그 목록 래퍼 응답 스키마"""

    blogs: list[BlogListResponse] = Field(..., description="블로그 목록")


class BlogConnectionTestResponse(BaseModel):
    """블로그 연결 테스트 응답 스키마"""

    success: bool = Field(..., description="연결 성공 여부")
    message: str = Field(..., description="결과 메시지")
    details: Optional[Dict[str, Any]] = Field(None, description="상세 정보")
    # 크롤링/매칭 결과 (Phase M-1)
    crawled_count: int = Field(0, description="크롤링된 포스트 수")
    is_new_blog: bool = Field(True, description="신규 블로그 여부")
    matching_started: bool = Field(False, description="백그라운드 매칭 시작 여부")


class BlogStatsResponse(BaseModel):
    """블로그 통계 응답 스키마"""

    total_blogs: int = Field(..., description="총 블로그 수")
    active_blogs: int = Field(..., description="활성 블로그 수")
    auto_publish_enabled: int = Field(..., description="자동 발행 활성화 수")
    by_platform: Dict[str, int] = Field(..., description="플랫폼별 수")


class BlogMatchingConfigRequest(BaseModel):
    """블로그 매칭 설정 요청 스키마 (Phase 3)"""

    allow_duplicate_similar_posts: bool = Field(
        False, description="매칭된 포스트도 글 생성 후 발행 (OFF: 독립 포스트만 발행)"
    )
    matching_threshold: int = Field(
        65, ge=50, le=100, description="유사도 매칭 임계값(%)"
    )


class BlogMatchingConfigResponse(BaseModel):
    """블로그 매칭 설정 응답 스키마 (Phase 3)"""

    allow_duplicate_similar_posts: bool = Field(
        False, description="매칭된 포스트도 글 생성 후 발행"
    )
    matching_threshold: int = Field(
        65, description="유사도 매칭 임계값(%)"
    )

    class Config:
        from_attributes = True


class BlogMatchingStatsResponse(BaseModel):
    """블로그 매칭 통계 응답 스키마 (Phase 3)"""

    crawled_count: int = Field(0, description="크롤링된 포스트 수")
    matched_posts: int = Field(0, description="매칭된 포스트 수")
    unmatched_posts: int = Field(0, description="미매칭 포스트 수")
    last_matched_at: Optional[datetime] = Field(None, description="마지막 매칭 시간")


class ErrorResponse(BaseModel):
    """에러 응답 스키마"""

    error: str = Field(..., description="에러 코드")
    message: str = Field(..., description="에러 메시지")
    details: Optional[Dict[str, Any]] = Field(None, description="상세 정보")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "VALIDATION_ERROR",
                "message": "입력값이 올바르지 않습니다",
                "details": {"field": "api_key", "error": "필수 입력값입니다"},
            }
        }
