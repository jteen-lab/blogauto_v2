# Phase C: 정식 제목 모델 및 API

> **Phase**: C  
> **목표**: Title, TitleGroup 모델 및 CRUD API 구현  
> **의존성**: Phase B (similarity_service)

---

## 📋 작업 개요

정식 제목과 그룹을 관리하는 모델 및 API를 구현합니다.
레거시의 Title 모델 구조를 참조하되 V2에 맞게 개선합니다.

---

## 📁 생성할 파일
```
services/republish/app/
├── models/
│   └── title.py           # Title, TitleGroup 모델
├── schemas/
│   └── title.py           # Pydantic 스키마
└── api/
    └── titles.py          # Title API 엔드포인트
```

---

## 📝 작업 1: Title 모델 구현

파일 위치: `services/republish/app/models/title.py`

### 모델 명세
```python
"""
정식 제목 및 그룹 모델

임시 제목에서 이동된 정식 제목과 그룹화 정보를 저장합니다.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class TitleGroup(Base):
    """제목 그룹 모델"""
    __tablename__ = "title_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 그룹 식별
    group_uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # 카테고리 연결
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # 그룹 메타데이터
    location = Column(String(100), nullable=True, comment="공통 지역명")
    main_keyword = Column(String(200), nullable=True, comment="공통 주제 키워드")
    
    # 통계
    title_count = Column(Integer, default=1, comment="그룹 내 제목 수")
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    titles = relationship("Title", back_populates="group", lazy="dynamic")
    category = relationship("Category", back_populates="title_groups")
    
    def __repr__(self):
        return f"<TitleGroup(id={self.id}, count={self.title_count})>"
    
    def get_representative(self) -> Optional["Title"]:
        """대표 제목 반환"""
        return self.titles.filter_by(is_representative=True).first()
    
    def update_count(self) -> int:
        """제목 수 업데이트"""
        self.title_count = self.titles.count()
        return self.title_count


class Title(Base):
    """정식 제목 모델"""
    __tablename__ = "titles"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 제목 내용
    title = Column(String(500), nullable=False, index=True)
    
    # 카테고리
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    sub_category_id = Column(Integer, ForeignKey("sub_categories.id"), nullable=True)
    
    # 그룹핑
    group_id = Column(Integer, ForeignKey("title_groups.id"), nullable=True, index=True)
    is_representative = Column(Boolean, default=False, index=True, comment="그룹 대표 여부")
    similarity_score = Column(Float, nullable=True, comment="대표 제목과의 유사도")
    grouped_at = Column(DateTime, nullable=True, comment="그룹핑된 시간")
    
    # 지역 정보 (JSON 문자열)
    location_info = Column(Text, nullable=True, comment="추출된 지역 정보 JSON")
    
    # 키워드 (JSON 문자열)
    keywords = Column(Text, nullable=True, comment="추출된 키워드 JSON")
    
    # 상태
    status = Column(String(20), default="active", index=True, comment="active/used/disabled")
    source = Column(String(50), default="transfer", comment="transfer/manual/crawl")
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    group = relationship("TitleGroup", back_populates="titles")
    category = relationship("Category", back_populates="titles")
    sub_category = relationship("SubCategory", back_populates="titles")
    
    # 인덱스
    __table_args__ = (
        Index("ix_titles_group_rep", "group_id", "is_representative"),
        Index("ix_titles_category_status", "category_id", "status"),
    )
    
    def __repr__(self):
        return f"<Title(id={self.id}, title='{self.title[:30]}...')>"
    
    def set_as_representative(self, session) -> None:
        """현재 제목을 그룹 대표로 설정"""
        if self.group_id:
            # 기존 대표 해제
            session.query(Title).filter(
                Title.group_id == self.group_id,
                Title.is_representative == True,
                Title.id != self.id
            ).update({"is_representative": False})
            
            # 현재 제목을 대표로
            self.is_representative = True
    
    def get_group_titles(self, session) -> List["Title"]:
        """같은 그룹의 모든 제목 반환"""
        if not self.group_id:
            return [self]
        return session.query(Title).filter(Title.group_id == self.group_id).all()
```

### 구현 요구사항

1. **레거시 참조**: `blogauto_new/core/models.py`
   - `Title` (445줄) - 필드 구조 참조
   - `TempTitle` (432줄) - 필드 구조 참조
2. **그룹 UUID**: group_uuid로 외부 참조 가능
3. **인덱스**: 자주 조회되는 필드에 인덱스 추가
4. **파일 크기**: 200줄 이내

---

## 📝 작업 2: Title 스키마 구현

파일 위치: `services/republish/app/schemas/title.py`
```python
"""
정식 제목 Pydantic 스키마
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ===== TitleGroup 스키마 =====

class TitleGroupBase(BaseModel):
    """TitleGroup 기본 스키마"""
    category_id: Optional[int] = None
    location: Optional[str] = None
    main_keyword: Optional[str] = None


class TitleGroupCreate(TitleGroupBase):
    """TitleGroup 생성 스키마"""
    pass


class TitleGroupResponse(TitleGroupBase):
    """TitleGroup 응답 스키마"""
    id: int
    group_uuid: str
    title_count: int
    created_at: datetime
    representative_title: Optional[str] = None
    
    class Config:
        from_attributes = True


# ===== Title 스키마 =====

class TitleBase(BaseModel):
    """Title 기본 스키마"""
    title: str = Field(..., min_length=1, max_length=500)
    category_id: Optional[int] = None
    sub_category_id: Optional[int] = None


class TitleCreate(TitleBase):
    """Title 생성 스키마"""
    source: str = "manual"


class TitleUpdate(BaseModel):
    """Title 수정 스키마"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category_id: Optional[int] = None
    sub_category_id: Optional[int] = None
    status: Optional[str] = None


class TitleResponse(TitleBase):
    """Title 응답 스키마"""
    id: int
    group_id: Optional[int] = None
    is_representative: bool
    similarity_score: Optional[float] = None
    location_info: Optional[str] = None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    
    # 추가 정보
    group_count: Optional[int] = None
    category_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class TitleListResponse(BaseModel):
    """Title 목록 응답 스키마"""
    items: List[TitleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ===== 그룹 관련 스키마 =====

class TitleGroupDetailResponse(TitleGroupResponse):
    """TitleGroup 상세 응답 (제목 목록 포함)"""
    titles: List[TitleResponse] = []


class ChangeRepresentativeRequest(BaseModel):
    """대표 제목 변경 요청"""
    new_representative_id: int


class AddToGroupRequest(BaseModel):
    """그룹에 제목 추가 요청"""
    title_ids: List[int]
    group_id: int


class RemoveFromGroupRequest(BaseModel):
    """그룹에서 제목 제거 요청"""
    title_ids: List[int]
```

---

## 📝 작업 3: Title API 구현

파일 위치: `services/republish/app/api/titles.py`
```python
"""
정식 제목 API 엔드포인트
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.title import Title, TitleGroup
from app.schemas.title import (
    TitleCreate,
    TitleUpdate,
    TitleResponse,
    TitleListResponse,
    TitleGroupResponse,
    TitleGroupDetailResponse,
    ChangeRepresentativeRequest,
    AddToGroupRequest,
    RemoveFromGroupRequest,
)

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/titles", tags=["titles"])


# ===== Title CRUD =====

@router.get("", response_model=TitleListResponse)
def get_titles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    group_view: bool = False,
    db: Session = Depends(get_db)
):
    """
    정식 제목 목록 조회
    
    - group_view=True: 그룹별로 묶어서 반환 (대표 제목만)
    - group_view=False: 전체 제목 반환
    """
    # 구현 필요
    pass


@router.get("/{title_id}", response_model=TitleResponse)
def get_title(title_id: int, db: Session = Depends(get_db)):
    """정식 제목 상세 조회"""
    # 구현 필요
    pass


@router.post("", response_model=TitleResponse)
def create_title(data: TitleCreate, db: Session = Depends(get_db)):
    """정식 제목 수동 생성"""
    # 구현 필요
    pass


@router.put("/{title_id}", response_model=TitleResponse)
def update_title(title_id: int, data: TitleUpdate, db: Session = Depends(get_db)):
    """정식 제목 수정"""
    # 구현 필요
    pass


@router.delete("/{title_id}")
def delete_title(title_id: int, db: Session = Depends(get_db)):
    """정식 제목 삭제"""
    # 구현 필요
    pass


@router.post("/bulk-delete")
def bulk_delete_titles(title_ids: List[int], db: Session = Depends(get_db)):
    """정식 제목 일괄 삭제"""
    # 구현 필요
    pass


# ===== TitleGroup API =====

@router.get("/groups", response_model=List[TitleGroupResponse])
def get_title_groups(
    category_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """제목 그룹 목록 조회"""
    # 구현 필요
    pass


@router.get("/groups/{group_id}", response_model=TitleGroupDetailResponse)
def get_title_group(group_id: int, db: Session = Depends(get_db)):
    """제목 그룹 상세 조회 (그룹 내 제목 포함)"""
    # 구현 필요
    pass


@router.put("/groups/{group_id}/representative")
def change_representative(
    group_id: int,
    data: ChangeRepresentativeRequest,
    db: Session = Depends(get_db)
):
    """그룹 대표 제목 변경"""
    # 구현 필요
    pass


@router.post("/groups/{group_id}/add")
def add_titles_to_group(
    group_id: int,
    data: AddToGroupRequest,
    db: Session = Depends(get_db)
):
    """그룹에 제목 추가"""
    # 구현 필요
    pass


@router.post("/groups/{group_id}/remove")
def remove_titles_from_group(
    group_id: int,
    data: RemoveFromGroupRequest,
    db: Session = Depends(get_db)
):
    """그룹에서 제목 제거 (개별 제목으로 분리)"""
    # 구현 필요
    pass
```

### 구현 요구사항

1. **레거시 참조**: 
   - `blogauto_new/core/services/title_group_service.py` - 그룹 관리 로직
2. **페이지네이션**: 목록 조회 시 페이지네이션 필수
3. **필터링**: 카테고리, 상태, 검색어 필터
4. **파일 크기**: 각 파일 300줄 이내

---

## 📝 작업 4: models/__init__.py 업데이트
```python
# 기존 내용에 추가
from .title import Title, TitleGroup
```

---

## 📝 작업 5: main.py 라우터 등록
```python
# 기존 라우터에 추가
from app.api import titles
app.include_router(titles.router, prefix="/api/v1")
```

---

## ✅ 완료 조건

1. [ ] `app/models/title.py` 구현 (< 200줄)
2. [ ] `app/schemas/title.py` 구현 (< 150줄)
3. [ ] `app/api/titles.py` 구현 (< 300줄)
4. [ ] models/__init__.py 업데이트
5. [ ] main.py 라우터 등록
6. [ ] 마이그레이션 파일 생성
7. [ ] 모든 함수에 타입 힌트, Docstring 적용

---

## 🧪 테스트 케이스
```python
# API 테스트
# 1. 제목 생성
POST /api/v1/titles
{"title": "테스트 제목", "category_id": 1}

# 2. 제목 목록 조회
GET /api/v1/titles?page=1&page_size=20

# 3. 그룹별 조회
GET /api/v1/titles?group_view=true

# 4. 그룹 상세 조회
GET /api/v1/titles/groups/1

# 5. 대표 제목 변경
PUT /api/v1/titles/groups/1/representative
{"new_representative_id": 5}
```

---

## 📚 참조

- 레거시: `blogauto_new/core/models.py`
  - `Title` (445줄)
  - `TempTitle` (432줄)
- 레거시: `blogauto_new/core/services/title_group_service.py`
  - `add_to_group()` (132줄)
  - `exclude_from_group()` (64줄)
  - `swap_representative_title()` (244줄)

---

**다음 Phase**: Phase D (제목 이동 모듈)
