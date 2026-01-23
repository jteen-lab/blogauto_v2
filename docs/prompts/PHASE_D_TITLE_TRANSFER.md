# Phase D: 제목 이동 모듈

> **Phase**: D  
> **목표**: 임시→정식, 정식→임시 제목 이동 기능 구현  
> **의존성**: Phase C (Title 모델 및 API)

---

## 📋 작업 개요

임시 제목과 정식 제목 간의 이동 기능을 구현합니다.
이동 시 유사도 매칭을 적용하여 자동 그룹화합니다.

---

## 📁 생성할 파일
```
services/republish/app/
├── services/
│   └── title_transfer_service.py    # 제목 이동 서비스
└── api/
    └── title_transfer.py            # 제목 이동 API
```

---

## 📝 작업 1: title_transfer_service.py 구현

파일 위치: `services/republish/app/services/title_transfer_service.py`

### 함수 명세
```python
"""
제목 이동 서비스

임시 제목 ↔ 정식 제목 간 이동을 처리합니다.
이동 시 유사도 매칭을 적용하여 자동 그룹화합니다.
"""

import uuid
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.title import Title, TitleGroup
from app.models.temp_title import TempTitle
from app.models.category import Category

# shared 서비스 import
import sys
sys.path.insert(0, '/app/shared')
from services.location_service import extract_location
from services.similarity_service import calculate_similarity, SimilarityService

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_SIMILARITY_THRESHOLD = 80.0


class TitleTransferService:
    """제목 이동 서비스"""
    
    def __init__(self, db: Session, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Args:
            db: 데이터베이스 세션
            threshold: 유사도 임계값 (0-100)
        """
        self.db = db
        self.threshold = threshold
        self.similarity_service = SimilarityService(threshold)
    
    def move_to_main(
        self,
        temp_title_ids: List[int],
        auto_group: bool = True
    ) -> Dict:
        """
        임시 제목 → 정식 제목 이동
        
        Args:
            temp_title_ids: 이동할 임시 제목 ID 목록
            auto_group: 자동 그룹화 여부
            
        Returns:
            {
                "moved": 이동된 수,
                "grouped": 그룹화된 수,
                "duplicates": 중복 제거된 수,
                "errors": 에러 목록
            }
        """
        # 구현 필요:
        # 1. 임시 제목 조회
        # 2. 중복 제거 (100% 동일 제목)
        # 3. 지역명 추출
        # 4. 같은 카테고리 내 기존 그룹과 유사도 매칭
        # 5. 임계값 이상 → 기존 그룹에 추가
        # 6. 미만 → 새 그룹 생성 (대표 제목)
        # 7. 임시 제목 삭제
        # 8. 결과 반환
        pass
    
    def move_to_temp(self, title_ids: List[int]) -> Dict:
        """
        정식 제목 → 임시 제목 이동
        
        Args:
            title_ids: 이동할 정식 제목 ID 목록
            
        Returns:
            {
                "moved": 이동된 수,
                "errors": 에러 목록
            }
        """
        # 구현 필요:
        # 1. 정식 제목 조회
        # 2. 대표 제목인 경우 그룹 내 다른 제목을 대표로 변경
        # 3. 임시 제목으로 복사
        # 4. 정식 제목 삭제
        # 5. 그룹 카운트 업데이트
        pass
    
    def auto_transfer_categorized(self) -> Dict:
        """
        카테고리가 있는 임시 제목 자동 이동
        
        수집 모듈 완료 후 호출되어 자동으로 정식 제목으로 이동합니다.
        
        Returns:
            {
                "total": 대상 제목 수,
                "moved": 이동된 수,
                "grouped": 그룹화된 수,
                "errors": 에러 목록
            }
        """
        # 구현 필요:
        # 1. 카테고리가 있는 임시 제목 조회
        # 2. move_to_main 호출
        pass
    
    def _find_matching_group(
        self,
        title: str,
        category_id: Optional[int],
        location_info: Optional[Dict]
    ) -> Optional[TitleGroup]:
        """
        제목과 매칭되는 기존 그룹 찾기
        
        Args:
            title: 제목
            category_id: 카테고리 ID
            location_info: 지역 정보
            
        Returns:
            매칭되는 그룹 또는 None
        """
        # 구현 필요:
        # 1. 같은 카테고리의 그룹 조회
        # 2. 각 그룹의 대표 제목과 유사도 계산 (지역 우선)
        # 3. 임계값 이상인 그룹 중 가장 높은 유사도 반환
        pass
    
    def _create_new_group(
        self,
        title: Title,
        location_info: Optional[Dict]
    ) -> TitleGroup:
        """
        새 그룹 생성
        
        Args:
            title: 대표 제목
            location_info: 지역 정보
            
        Returns:
            생성된 그룹
        """
        # 구현 필요
        pass
    
    def _add_to_group(
        self,
        title: Title,
        group: TitleGroup,
        similarity_score: float
    ) -> None:
        """
        기존 그룹에 제목 추가
        
        Args:
            title: 추가할 제목
            group: 대상 그룹
            similarity_score: 유사도 점수
        """
        # 구현 필요
        pass
    
    def _extract_keywords(self, title: str) -> List[str]:
        """
        제목에서 주요 키워드 추출
        
        Args:
            title: 제목
            
        Returns:
            키워드 리스트
        """
        # 구현 필요 (간단한 명사 추출)
        pass


# 편의 함수
def move_temp_to_main(
    db: Session,
    temp_title_ids: List[int],
    auto_group: bool = True,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict:
    """임시 → 정식 이동 (편의 함수)"""
    return TitleTransferService(db, threshold).move_to_main(temp_title_ids, auto_group)


def move_main_to_temp(
    db: Session,
    title_ids: List[int]
) -> Dict:
    """정식 → 임시 이동 (편의 함수)"""
    return TitleTransferService(db).move_to_temp(title_ids)


def auto_transfer_categorized_titles(
    db: Session,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict:
    """카테고리 있는 임시 제목 자동 이동 (편의 함수)"""
    return TitleTransferService(db, threshold).auto_transfer_categorized()
```

### 구현 요구사항

1. **레거시 참조**: `blogauto_new/core/services/titles_temp.py`
   - `move_to_main_titles()` (49줄) - 이동 로직 참조
2. **유사도 매칭**: Phase B의 similarity_service 사용
3. **지역명 처리**: Phase A의 location_service 사용
4. **트랜잭션**: 이동 작업은 트랜잭션으로 처리
5. **파일 크기**: 300줄 이내

---

## 📝 작업 2: title_transfer.py API 구현

파일 위치: `services/republish/app/api/title_transfer.py`
```python
"""
제목 이동 API 엔드포인트
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.services.title_transfer_service import (
    move_temp_to_main,
    move_main_to_temp,
    auto_transfer_categorized_titles,
    DEFAULT_SIMILARITY_THRESHOLD,
)

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/titles/transfer", tags=["title-transfer"])


# ===== 요청/응답 스키마 =====

class MoveToMainRequest(BaseModel):
    """임시 → 정식 이동 요청"""
    temp_title_ids: List[int]
    auto_group: bool = True
    similarity_threshold: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD


class MoveToTempRequest(BaseModel):
    """정식 → 임시 이동 요청"""
    title_ids: List[int]


class AutoTransferRequest(BaseModel):
    """자동 이동 요청"""
    similarity_threshold: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD


class TransferResponse(BaseModel):
    """이동 결과 응답"""
    success: bool
    moved: int
    grouped: int = 0
    duplicates: int = 0
    errors: List[str] = []
    message: str


# ===== API 엔드포인트 =====

@router.post("/to-main", response_model=TransferResponse)
def transfer_to_main(
    data: MoveToMainRequest,
    db: Session = Depends(get_db)
):
    """
    임시 제목 → 정식 제목 이동
    
    선택한 임시 제목들을 정식 제목으로 이동합니다.
    auto_group=True이면 유사도 매칭으로 자동 그룹화합니다.
    """
    try:
        result = move_temp_to_main(
            db=db,
            temp_title_ids=data.temp_title_ids,
            auto_group=data.auto_group,
            threshold=data.similarity_threshold
        )
        
        return TransferResponse(
            success=True,
            moved=result["moved"],
            grouped=result.get("grouped", 0),
            duplicates=result.get("duplicates", 0),
            errors=result.get("errors", []),
            message=f"{result['moved']}개 제목이 정식 제목으로 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 임시→정식 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/to-temp", response_model=TransferResponse)
def transfer_to_temp(
    data: MoveToTempRequest,
    db: Session = Depends(get_db)
):
    """
    정식 제목 → 임시 제목 이동
    
    선택한 정식 제목들을 임시 제목으로 되돌립니다.
    대표 제목인 경우 그룹 내 다른 제목이 대표가 됩니다.
    """
    try:
        result = move_main_to_temp(
            db=db,
            title_ids=data.title_ids
        )
        
        return TransferResponse(
            success=True,
            moved=result["moved"],
            errors=result.get("errors", []),
            message=f"{result['moved']}개 제목이 임시 제목으로 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 정식→임시 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto", response_model=TransferResponse)
def auto_transfer(
    data: AutoTransferRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    카테고리가 있는 임시 제목 자동 이동
    
    카테고리가 분류된 모든 임시 제목을 정식 제목으로 이동합니다.
    수집 모듈 완료 후 자동으로 호출될 수 있습니다.
    """
    try:
        result = auto_transfer_categorized_titles(
            db=db,
            threshold=data.similarity_threshold
        )
        
        return TransferResponse(
            success=True,
            moved=result["moved"],
            grouped=result.get("grouped", 0),
            duplicates=result.get("duplicates", 0),
            errors=result.get("errors", []),
            message=f"총 {result.get('total', 0)}개 중 {result['moved']}개가 이동되었습니다."
        )
    except Exception as e:
        logger.error(f"[TRANSFER] 자동 이동 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
def get_transfer_stats(db: Session = Depends(get_db)):
    """
    이동 통계 조회
    
    - 임시 제목 수 (전체/카테고리 있음/없음)
    - 정식 제목 수 (전체/그룹화된 것)
    - 그룹 수
    """
    # 구현 필요
    pass
```

---

## 📝 작업 3: main.py 라우터 등록
```python
# 기존 라우터에 추가
from app.api import title_transfer
app.include_router(title_transfer.router, prefix="/api/v1")
```

---

## ✅ 완료 조건

1. [ ] `app/services/title_transfer_service.py` 구현 (< 300줄)
2. [ ] `app/api/title_transfer.py` 구현 (< 200줄)
3. [ ] main.py 라우터 등록
4. [ ] 트랜잭션 처리 적용
5. [ ] 에러 처리 포함
6. [ ] 모든 함수에 타입 힌트, Docstring 적용

---

## 🧪 테스트 케이스
```python
# API 테스트

# 1. 임시 → 정식 이동 (자동 그룹화)
POST /api/v1/titles/transfer/to-main
{
    "temp_title_ids": [1, 2, 3, 4, 5],
    "auto_group": true,
    "similarity_threshold": 80
}
# 예상 응답
{
    "success": true,
    "moved": 5,
    "grouped": 3,
    "duplicates": 0,
    "errors": [],
    "message": "5개 제목이 정식 제목으로 이동되었습니다."
}

# 2. 정식 → 임시 이동
POST /api/v1/titles/transfer/to-temp
{
    "title_ids": [10, 11]
}

# 3. 자동 이동
POST /api/v1/titles/transfer/auto
{
    "similarity_threshold": 80
}

# 4. 통계 조회
GET /api/v1/titles/transfer/stats
```

---

## 📚 참조

- 레거시: `blogauto_new/core/services/titles_temp.py`
  - `move_to_main_titles()` (49줄)
- 레거시: `blogauto_new/core/services/titles_main.py`
  - `move_to_temp_titles_view()` (55줄)
- Phase A: `shared/services/location_service.py`
- Phase B: `shared/services/similarity_service.py`
- Phase C: `app/models/title.py`, `app/api/titles.py`

---

**다음 Phase**: Phase E (정식 제목 UI)
