# Phase B: 유사도 매칭 서비스 V2

> **Phase**: B  
> **목표**: 지역명 우선 처리하는 향상된 유사도 매칭 서비스 구현  
> **의존성**: Phase A (location_service)

---

## 📋 작업 개요

기존 유사도 매칭 로직을 개선하여 지역명을 우선 처리하는 V2 서비스를 구현합니다.
핵심 원칙: "지역명이 다르면 절대 그룹화하지 않음"

---

## 📁 생성할 파일
```
shared/services/
└── similarity_service.py    # 유사도 매칭 서비스 V2
```

---

## 📝 작업 1: similarity_service.py 구현

파일 위치: `shared/services/similarity_service.py`

### 함수 명세
```python
"""
유사도 매칭 서비스 V2

지역명 우선 처리를 적용한 향상된 유사도 매칭 서비스입니다.
여러 기능에서 공통으로 사용됩니다:
- 임시 제목 → 정식 제목 이동 시 그룹화
- 블로그 크롤링 제목과 정식 제목 매칭
- 그룹 내 제목 재매칭
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

# rapidfuzz 사용 (설치된 경우)
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

from .location_service import extract_location, is_same_location, remove_location

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_SIMILARITY_THRESHOLD = 80.0
KOREAN_STOPWORDS = [
    '및', '과', '에', '에서', '으로', '와', '은', '는', '이', '가', '을', '를',
    '대한', '관한', '위한', '통한', '따른', '인한', '등', '또는',
    '방법', '원인', '증상', '치료', '효과', '정보', '종류', '가격', '비교', '정리',
    '추천', '순위', '후기', '리뷰', '총정리', '완벽정리',
]


class SimilarityService:
    """유사도 매칭 서비스 V2"""
    
    def __init__(self, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Args:
            threshold: 유사도 임계값 (0-100, 기본 80)
        """
        self.threshold = threshold
    
    def normalize_text(self, text: str) -> str:
        """
        텍스트 정규화
        
        Args:
            text: 원본 텍스트
            
        Returns:
            정규화된 텍스트
        """
        # 구현 필요:
        # 1. 공백 정규화
        # 2. 특수문자 제거/통일
        # 3. 소문자 변환
        # 4. 불용어 제거 (선택적)
        pass
    
    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        순수 텍스트 유사도 계산 (지역명 처리 없음)
        
        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트
            
        Returns:
            유사도 점수 (0-100)
        """
        # 구현 필요:
        # 1. 정규화
        # 2. 완전 일치 체크 → 100
        # 3. 포함 관계 체크 → 85-95
        # 4. rapidfuzz 또는 SequenceMatcher 사용
        pass
    
    def calculate_similarity_v2(self, title1: str, title2: str) -> float:
        """
        V2 유사도 계산 (지역명 우선 처리)
        
        핵심 로직:
        1. 지역명 추출
        2. 지역명이 다르면 → 0점 반환
        3. 지역명 제거 후 텍스트 유사도 계산
        
        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목
            
        Returns:
            유사도 점수 (0-100)
        """
        # 구현 필요
        pass
    
    def find_best_match(
        self, 
        target_title: str, 
        candidate_titles: List[str],
        min_threshold: Optional[float] = None
    ) -> Optional[Tuple[str, float]]:
        """
        후보 제목들 중 가장 유사한 제목 찾기
        
        Args:
            target_title: 대상 제목
            candidate_titles: 후보 제목 리스트
            min_threshold: 최소 임계값 (None이면 self.threshold 사용)
            
        Returns:
            (가장 유사한 제목, 유사도) 또는 None
        """
        # 구현 필요
        pass
    
    def find_similar_group(
        self,
        title: str,
        groups: List[Dict],
        category_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        제목이 속할 수 있는 그룹 찾기
        
        Args:
            title: 대상 제목
            groups: 그룹 리스트 [{"id": 1, "representative_title": "...", "category_id": 1}, ...]
            category_id: 카테고리 필터 (None이면 전체)
            
        Returns:
            매칭된 그룹 정보 또는 None
        """
        # 구현 필요:
        # 1. 카테고리 필터링
        # 2. 각 그룹의 대표 제목과 유사도 계산
        # 3. 임계값 이상인 그룹 중 가장 높은 유사도 반환
        pass
    
    def batch_group_titles(
        self,
        titles: List[Dict],
        existing_groups: Optional[List[Dict]] = None
    ) -> Dict[str, List[Dict]]:
        """
        제목들을 배치로 그룹화
        
        Args:
            titles: 제목 리스트 [{"id": 1, "title": "...", "category_id": 1}, ...]
            existing_groups: 기존 그룹 리스트 (None이면 새로 그룹화)
            
        Returns:
            {
                "new_groups": [{"representative": {...}, "members": [...]}],
                "added_to_existing": [{"group_id": 1, "titles": [...]}],
                "ungrouped": [...]
            }
        """
        # 구현 필요:
        # 1. 기존 그룹에 매칭 시도
        # 2. 매칭 안 된 것들끼리 새 그룹 생성
        # 3. 그룹 안 된 것들은 개별 처리
        pass


# 편의 함수
def calculate_similarity(title1: str, title2: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> float:
    """제목 유사도 계산 (편의 함수)"""
    return SimilarityService(threshold).calculate_similarity_v2(title1, title2)


def find_best_match(
    target: str, 
    candidates: List[str], 
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Optional[Tuple[str, float]]:
    """가장 유사한 제목 찾기 (편의 함수)"""
    return SimilarityService(threshold).find_best_match(target, candidates)


def batch_group_titles(
    titles: List[Dict],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict[str, List[Dict]]:
    """제목 배치 그룹화 (편의 함수)"""
    return SimilarityService(threshold).batch_group_titles(titles)
```

### 구현 요구사항

1. **지역명 우선 처리**: 지역이 다르면 무조건 0점
2. **레거시 참조**: `blogauto_new/core/similarity_utils.py`
   - `calculate_title_similarity()` (1258줄) - 기본 로직 참조
   - `normalize_for_similarity()` (98줄) - 정규화 로직 참조
3. **rapidfuzz 사용**: 설치된 경우 사용, 아니면 difflib 폴백
4. **파일 크기**: 300줄 이내

---

## 📝 작업 2: __init__.py 업데이트

파일 위치: `shared/services/__init__.py`
```python
"""
BlogAuto V2 공유 서비스 모듈
"""

from .location_service import (
    LocationService,
    extract_location,
    is_same_location,
    remove_location,
)

from .similarity_service import (
    SimilarityService,
    calculate_similarity,
    find_best_match,
    batch_group_titles,
    DEFAULT_SIMILARITY_THRESHOLD,
)

__all__ = [
    # Location
    "LocationService",
    "extract_location",
    "is_same_location",
    "remove_location",
    # Similarity
    "SimilarityService",
    "calculate_similarity",
    "find_best_match",
    "batch_group_titles",
    "DEFAULT_SIMILARITY_THRESHOLD",
]
```

---

## ✅ 완료 조건

1. [ ] `shared/services/similarity_service.py` 구현 (< 300줄)
2. [ ] `shared/services/__init__.py` 업데이트
3. [ ] 지역명 우선 처리 로직 적용
4. [ ] 모든 함수에 타입 힌트 적용
5. [ ] 모든 함수에 Docstring 작성
6. [ ] 에러 처리 포함

---

## 🧪 테스트 케이스
```python
from shared.services import calculate_similarity, find_best_match

# 테스트 1: 지역이 다르면 0점
score1 = calculate_similarity(
    "포항 이삿짐센터 포장이사 업체추천",
    "일산 이삿짐센터 포장이사 업체추천"
)
assert score1 == 0.0, "지역이 다르면 0점이어야 함"

# 테스트 2: 같은 지역이면 유사도 계산
score2 = calculate_similarity(
    "포항 이삿짐센터 포장이사 업체추천",
    "경북 포항시 북구 이삿짐센터 이사비용"
)
assert score2 > 50.0, "같은 지역이면 유사도 계산되어야 함"

# 테스트 3: 지역 없는 제목끼리 비교
score3 = calculate_similarity(
    "이삭토스트 맛집탐방 영업시간 인기메뉴 총정리",
    "이삭토스트 맛집탐방 인기메뉴와 영업시간 총정리"
)
assert score3 > 80.0, "유사한 제목은 높은 점수"

# 테스트 4: 지역 없는 것 + 지역 있는 것
score4 = calculate_similarity(
    "이삭토스트 맛집탐방 총정리",
    "서울 이삭토스트 맛집탐방 총정리"
)
assert score4 > 0.0, "한쪽만 지역 있으면 매칭 가능"

# 테스트 5: 최적 매칭 찾기
candidates = [
    "일산 이삿짐센터 업체추천",
    "포항 이삿짐센터 가격비교",
    "대구 이삿짐센터 후기"
]
result = find_best_match("경북 포항 이삿짐센터 추천", candidates)
assert result is not None
assert "포항" in result[0], "같은 지역이 매칭되어야 함"
```

---

## 📚 참조

- 레거시: `blogauto_new/core/similarity_utils.py`
  - `calculate_title_similarity()` (1258줄)
  - `normalize_for_similarity()` (98줄)
  - `normalize_text()` (220줄)
- Phase A: `shared/services/location_service.py`

---

**다음 Phase**: Phase C (정식 제목 모델 및 API)
