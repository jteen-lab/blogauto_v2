"""
카테고리 관리 스키마

Features:
- 3계층 카테고리 요청/응답 스키마
- Pydantic v2 호환
- 검증 및 직렬화 최적화
- 계층적 데이터 구조 지원
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ===============================
# Topic (주제) 스키마
# ===============================

class TopicCreateRequest(BaseModel):
    """주제 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100, description="주제명")
    description: Optional[str] = Field(None, max_length=1000, description="주제 설명")
    order: int = Field(default=0, ge=0, description="정렬 순서")

    class Config:
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "name": "건강",
                "description": "건강 관련 주제들",
                "order": 1
            }
        }


class TopicUpdateRequest(BaseModel):
    """주제 수정 요청"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="주제명")
    description: Optional[str] = Field(None, max_length=1000, description="주제 설명")
    order: Optional[int] = Field(None, ge=0, description="정렬 순서")

    class Config:
        str_strip_whitespace = True


class TopicResponse(BaseModel):
    """주제 응답"""
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    order: int
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # 하위 항목 수
    subtopic_count: Optional[int] = Field(default=0, description="하위 주제 개수")
    keyword_count: Optional[int] = Field(default=0, description="키워드 개수")

    class Config:
        from_attributes = True


# ===============================
# SubTopic (하위 주제) 스키마
# ===============================

class SubTopicCreateRequest(BaseModel):
    """하위 주제 생성 요청"""
    topic_id: int = Field(..., gt=0, description="상위 주제 ID")
    name: str = Field(..., min_length=1, max_length=100, description="하위 주제명")
    description: Optional[str] = Field(None, max_length=1000, description="하위 주제 설명")
    order: int = Field(default=0, ge=0, description="정렬 순서")

    class Config:
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "topic_id": 1,
                "name": "질병",
                "description": "각종 질병 관련 하위 주제",
                "order": 1
            }
        }


class SubTopicUpdateRequest(BaseModel):
    """하위 주제 수정 요청"""
    topic_id: Optional[int] = Field(None, gt=0, description="상위 주제 ID")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="하위 주제명")
    description: Optional[str] = Field(None, max_length=1000, description="하위 주제 설명")
    order: Optional[int] = Field(None, ge=0, description="정렬 순서")

    class Config:
        str_strip_whitespace = True


class SubTopicResponse(BaseModel):
    """하위 주제 응답"""
    id: int
    topic_id: int
    name: str
    description: Optional[str] = None
    order: int
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # 상위 정보
    topic_name: Optional[str] = Field(default=None, description="상위 주제명")

    # 하위 항목 수
    keyword_count: Optional[int] = Field(default=0, description="키워드 개수")

    class Config:
        from_attributes = True


# ===============================
# Keyword (키워드) 스키마
# ===============================

class KeywordCreateRequest(BaseModel):
    """키워드 생성 요청"""
    subtopic_id: int = Field(..., gt=0, description="상위 하위주제 ID")
    name: str = Field(..., min_length=1, max_length=100, description="키워드명")
    description: Optional[str] = Field(None, max_length=1000, description="키워드 설명")
    order: int = Field(default=0, ge=0, description="정렬 순서")
    search_volume: int = Field(default=0, ge=0, description="검색량")
    difficulty: int = Field(default=0, ge=0, le=10,
                            description="난이도 (0=미설정, 1-10)")
    priority: int = Field(default=5, ge=1, le=10, description="매칭 우선순위 (1-10, 낮을수록 높은 우선순위)")

    class Config:
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "subtopic_id": 1,
                "name": "골다공증",
                "description": "뼈 밀도가 감소하는 질병",
                "order": 1,
                "search_volume": 1000,
                "difficulty": 5,
                "priority": 5
            }
        }


class KeywordUpdateRequest(BaseModel):
    """키워드 수정 요청"""
    subtopic_id: Optional[int] = Field(None, gt=0, description="상위 하위주제 ID")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="키워드명")
    description: Optional[str] = Field(None, max_length=1000, description="키워드 설명")
    order: Optional[int] = Field(None, ge=0, description="정렬 순서")
    search_volume: Optional[int] = Field(None, ge=0, description="검색량")
    # 0 은 "미설정" 이다. 기존 키워드 383개가 0 이라 ge=1 로 막으면
    # 그 키워드는 이름조차 고칠 수 없다(422).
    difficulty: Optional[int] = Field(None, ge=0, le=10,
                                      description="난이도 (0=미설정, 1-10)")
    priority: Optional[int] = Field(None, ge=0, le=10,
                                    description="매칭 우선순위 (0=미설정, "
                                                "1-10, 낮을수록 먼저)")

    class Config:
        str_strip_whitespace = True


class KeywordResponse(BaseModel):
    """키워드 응답"""
    id: int
    subtopic_id: int
    name: str
    description: Optional[str] = None
    order: int
    search_volume: int = 0
    difficulty: int = 0
    priority: int = Field(default=5, description="매칭 우선순위 (1-10, 낮을수록 높은 우선순위)")
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # 상위 정보
    subtopic_name: Optional[str] = Field(default=None, description="상위 하위주제명")
    topic_name: Optional[str] = Field(default=None, description="최상위 주제명")

    class Config:
        from_attributes = True


# ===============================
# BlogCategory (블로그-카테고리 연결) 스키마
# ===============================

class BlogCategoryCreateRequest(BaseModel):
    """블로그-카테고리 연결 생성 요청"""
    blog_id: int = Field(..., gt=0, description="블로그 ID")

    # 카테고리 연결 (하나 이상 필수)
    topic_id: Optional[int] = Field(None, gt=0, description="주제 ID")
    subtopic_id: Optional[int] = Field(None, gt=0, description="하위 주제 ID")
    keyword_id: Optional[int] = Field(None, gt=0, description="키워드 ID")

    priority: int = Field(default=1, ge=1, le=10, description="우선순위 (1-10)")
    is_active: bool = Field(default=True, description="활성화 상태")

    @validator('topic_id', 'subtopic_id', 'keyword_id')
    def at_least_one_category(cls, v, values):
        """최소 하나의 카테고리는 필수"""
        if not any([values.get('topic_id'), values.get('subtopic_id'), values.get('keyword_id'), v]):
            raise ValueError('최소 하나의 카테고리(주제/하위주제/키워드)는 필수입니다')
        return v

    class Config:
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "blog_id": 1,
                "topic_id": 1,
                "subtopic_id": 1,
                "keyword_id": 1,
                "priority": 5,
                "is_active": True
            }
        }


class BlogCategoryUpdateRequest(BaseModel):
    """블로그-카테고리 연결 수정 요청"""
    topic_id: Optional[int] = Field(None, gt=0, description="주제 ID")
    subtopic_id: Optional[int] = Field(None, gt=0, description="하위 주제 ID")
    keyword_id: Optional[int] = Field(None, gt=0, description="키워드 ID")
    priority: Optional[int] = Field(None, ge=1, le=10, description="우선순위 (1-10)")
    is_active: Optional[bool] = Field(None, description="활성화 상태")


class BlogCategoryResponse(BaseModel):
    """블로그-카테고리 연결 응답"""
    id: int
    blog_id: int
    topic_id: Optional[int] = None
    subtopic_id: Optional[int] = None
    keyword_id: Optional[int] = None
    priority: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # 연결된 카테고리 정보
    topic_name: Optional[str] = Field(default=None, description="주제명")
    subtopic_name: Optional[str] = Field(default=None, description="하위 주제명")
    keyword_name: Optional[str] = Field(default=None, description="키워드명")

    # 카테고리 경로
    category_path: Optional[str] = Field(default=None, description="카테고리 경로 (예: 건강 > 질병 > 골다공증)")

    class Config:
        from_attributes = True


# ===============================
# 계층적 응답 스키마
# ===============================

class CategoryTreeResponse(BaseModel):
    """카테고리 트리 구조 응답"""
    topic: TopicResponse
    subtopics: List[Dict[str, Any]] = Field(default_factory=list, description="하위 주제와 키워드들")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "topic": {
                    "id": 1,
                    "name": "건강",
                    "subtopic_count": 2,
                    "keyword_count": 5
                },
                "subtopics": [
                    {
                        "id": 1,
                        "name": "질병",
                        "keywords": [
                            {"id": 1, "name": "골다공증"},
                            {"id": 2, "name": "고혈압"}
                        ]
                    }
                ]
            }
        }


class CategoryStatsResponse(BaseModel):
    """카테고리 통계 응답"""
    total_topics: int = Field(default=0, description="전체 주제 수")
    total_subtopics: int = Field(default=0, description="전체 하위 주제 수")
    total_keywords: int = Field(default=0, description="전체 키워드 수")
    total_blog_connections: int = Field(default=0, description="블로그 연결 수")

    class Config:
        json_schema_extra = {
            "example": {
                "total_topics": 3,
                "total_subtopics": 8,
                "total_keywords": 25,
                "total_blog_connections": 15
            }
        }


# ===============================
# 에러 응답 스키마
# ===============================

class ErrorResponse(BaseModel):
    """에러 응답"""
    detail: str = Field(..., description="에러 메시지")
    error_code: Optional[str] = Field(None, description="에러 코드")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "카테고리를 찾을 수 없습니다",
                "error_code": "CATEGORY_NOT_FOUND"
            }
        }