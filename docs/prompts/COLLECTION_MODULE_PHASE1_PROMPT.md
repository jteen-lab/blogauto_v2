# Phase 1: 수집 모듈 기본 구조 구현 프롬프트

> **Phase**: 1 - 기본 구조  
> **목표**: 수집 모듈의 DB 스키마, API, UI 기본 구조 구현  
> **예상 소요**: 2-3일  
> **작성일**: 2025-01-17

---

## 📋 작업 개요

수집 모듈(Collection Module)의 기본 인프라를 구축합니다.

---

## 🎯 구현 목표

### 1. 데이터베이스 모델 (5개 테이블)
```
app/models/
├── keyword.py           # 키워드 모델
├── title.py             # 제목 모델  
├── category.py          # 카테고리 모델
├── filter.py            # 필터 모델
└── collection_setting.py # 수집 설정 모델
```

### 2. API 엔드포인트
```
app/api/
├── keywords.py          # 키워드 CRUD API
├── titles.py            # 제목 CRUD API
├── categories.py        # 카테고리 CRUD API
└── filters.py           # 필터 CRUD API
```

### 3. UI 페이지
```
app/templates/collection/
├── index.html           # 데이터 관리 메인 (탭 컨테이너)
├── keywords.html        # 키워드 탭 (partial)
└── titles.html          # 임시제목 탭 (partial)
```

---

## 📝 상세 구현 명세

### 1. Keyword 모델 (app/models/keyword.py)
```python
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(200), nullable=False, index=True)
    search_volume = Column(Integer, nullable=True)
    competition = Column(Float, nullable=True)
    difficulty = Column(Float, nullable=True)
    intent = Column(String(20), nullable=True)
    trend = Column(String(20), nullable=True)
    source = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### 2. Title 모델 (app/models/title.py)
```python
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Title(Base):
    __tablename__ = "titles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    source_url = Column(String(1000), nullable=True)
    source_type = Column(String(50), nullable=False)  # search/rss/newsletter/manual
    status = Column(String(20), nullable=False, default="temp")  # temp/official
    quality_score = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    category = relationship("Category", back_populates="titles")
```

### 3. Category 모델 (app/models/category.py)
```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    keywords = Column(Text, nullable=True)  # JSON: ["키워드1", "키워드2"]
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    parent = relationship("Category", remote_side=[id], backref="children")
    titles = relationship("Title", back_populates="category")
```

### 4. Filter 모델 (app/models/filter.py)
```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class Filter(Base):
    __tablename__ = "filters"
    
    id = Column(Integer, primary_key=True, index=True)
    filter_type = Column(String(50), nullable=False, index=True)
    filter_value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### 5. CollectionSetting 모델 (app/models/collection_setting.py)
```python
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class CollectionSetting(Base):
    __tablename__ = "collection_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), nullable=False, unique=True)
    setting_value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

---

## API 엔드포인트 명세

### 키워드 API (app/api/keywords.py)
- GET /api/v1/keywords - 목록 조회 (페이지네이션, 검색)
- GET /api/v1/keywords/{id} - 단건 조회
- POST /api/v1/keywords - 생성
- PUT /api/v1/keywords/{id} - 수정
- DELETE /api/v1/keywords/{id} - 삭제 (soft delete)
- POST /api/v1/keywords/bulk - 일괄 생성
- DELETE /api/v1/keywords/bulk - 일괄 삭제

### 제목 API (app/api/titles.py)
- GET /api/v1/titles - 목록 조회 (status 필터: temp/official)
- GET /api/v1/titles/{id} - 단건 조회
- POST /api/v1/titles - 생성
- PUT /api/v1/titles/{id} - 수정
- DELETE /api/v1/titles/{id} - 삭제
- PUT /api/v1/titles/{id}/promote - 임시 → 정식 승격

### 카테고리 API (app/api/categories.py)
- GET /api/v1/categories - 목록 조회
- GET /api/v1/categories/{id} - 단건 조회
- POST /api/v1/categories - 생성
- PUT /api/v1/categories/{id} - 수정
- DELETE /api/v1/categories/{id} - 삭제
- GET /api/v1/categories/tree - 트리 구조 조회

### 필터 API (app/api/filters.py)
- GET /api/v1/filters - 목록 조회
- GET /api/v1/filters/{id} - 단건 조회
- POST /api/v1/filters - 생성
- PUT /api/v1/filters/{id} - 수정
- DELETE /api/v1/filters/{id} - 삭제 (is_system=True면 불가)

---

## UI 구현

### 데이터 관리 메인 페이지 (app/templates/collection/index.html)
- Alpine.js 탭 컴포넌트
- 탭: 키워드 / 임시제목 / 정식제목 / 소스관리 / 필터설정
- 기존 flow 카드 스타일 참조

### 키워드 탭 (app/templates/collection/keywords.html)
- 테이블: 번호 | 키워드 | 검색량 | 경쟁도 | 소스 | 수집일 | 액션
- 검색/필터 기능
- 페이지네이션
- 일괄 선택/삭제

### 임시제목 탭 (app/templates/collection/titles.html)
- 테이블: 번호 | 제목 | 카테고리 | 작성일 | 비고 | 액션
- 카테고리: "대분류 > 중분류" 또는 "미분류"
- 카테고리 필터 드롭다운

---

## ⚠️ 필수 작업

1. **모델 등록**: app/models/__init__.py에 새 모델 5개 등록
```python
   from app.models.keyword import Keyword
   from app.models.title import Title
   from app.models.category import Category
   from app.models.filter import Filter
   from app.models.collection_setting import CollectionSetting
```

2. **라우터 등록**: main.py에 새 API 라우터 등록
```python
   from app.api import keywords, titles, categories, filters
   app.include_router(keywords.router)
   app.include_router(titles.router)
   app.include_router(categories.router)
   app.include_router(filters.router)
```

3. **네비게이션 추가**: 사이드바에 "데이터 관리" 메뉴 추가 (/collection)

---

## ✅ 완료 조건

- [ ] 5개 테이블 생성 완료
- [ ] 키워드 CRUD API 동작 확인
- [ ] 제목 CRUD API 동작 확인
- [ ] 카테고리 CRUD API 동작 확인
- [ ] 필터 CRUD API 동작 확인
- [ ] 데이터 관리 페이지 접근 가능 (/collection)
- [ ] 탭 전환 동작
- [ ] 모든 파일 < 300줄
- [ ] 타입 힌트 100%
- [ ] Docstring 100%

---

## 📂 예상 파일 구조
```
services/republish/app/
├── models/
│   ├── __init__.py          # 모델 등록 수정
│   ├── keyword.py           # 신규
│   ├── title.py             # 신규
│   ├── category.py          # 신규
│   ├── filter.py            # 신규
│   └── collection_setting.py # 신규
├── schemas/
│   ├── keyword.py           # 신규
│   ├── title.py             # 신규
│   ├── category.py          # 신규
│   └── filter.py            # 신규
├── api/
│   ├── keywords.py          # 신규
│   ├── titles.py            # 신규
│   ├── categories.py        # 신규
│   └── filters.py           # 신규
└── templates/collection/
    ├── index.html           # 신규
    ├── keywords.html        # 신규
    └── titles.html          # 신규
```

---

**프롬프트 버전**: v1.0.0  
**작성일**: 2025-01-17
