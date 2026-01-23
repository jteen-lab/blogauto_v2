# Phase A: 지역명 DB 및 추출 서비스

> **Phase**: A  
> **목표**: 한국 행정구역 DB 구축 및 지역명 추출 서비스 구현  
> **의존성**: 없음

---

## 📋 작업 개요

제목에서 지역명을 추출하고 비교하는 서비스를 구현합니다.
이 서비스는 유사도 매칭 시 "지역이 다르면 그룹화하지 않음" 원칙을 적용하기 위한 기반입니다.

---

## 📁 생성할 파일
```
shared/
├── data/
│   └── korean_locations.json    # 한국 행정구역 DB
└── services/
    ├── __init__.py
    └── location_service.py      # 지역명 추출 서비스
```

---

## 📝 작업 1: 디렉토리 생성
```bash
mkdir -p ~/blogauto_v2/shared/data
mkdir -p ~/blogauto_v2/shared/services
```

---

## 📝 작업 2: korean_locations.json 생성

파일 위치: `shared/data/korean_locations.json`

### 데이터 구조
```json
{
  "provinces": {
    "서울": {"aliases": ["서울시", "서울특별시"], "type": "특별시"},
    "부산": {"aliases": ["부산시", "부산광역시"], "type": "광역시"},
    "대구": {"aliases": ["대구시", "대구광역시"], "type": "광역시"},
    "인천": {"aliases": ["인천시", "인천광역시"], "type": "광역시"},
    "광주": {"aliases": ["광주시", "광주광역시"], "type": "광역시"},
    "대전": {"aliases": ["대전시", "대전광역시"], "type": "광역시"},
    "울산": {"aliases": ["울산시", "울산광역시"], "type": "광역시"},
    "세종": {"aliases": ["세종시", "세종특별자치시"], "type": "특별자치시"},
    "경기": {"aliases": ["경기도"], "type": "도"},
    "강원": {"aliases": ["강원도", "강원특별자치도"], "type": "도"},
    "충북": {"aliases": ["충청북도"], "type": "도"},
    "충남": {"aliases": ["충청남도"], "type": "도"},
    "전북": {"aliases": ["전라북도", "전북특별자치도"], "type": "도"},
    "전남": {"aliases": ["전라남도"], "type": "도"},
    "경북": {"aliases": ["경상북도"], "type": "도"},
    "경남": {"aliases": ["경상남도"], "type": "도"},
    "제주": {"aliases": ["제주도", "제주특별자치도"], "type": "특별자치도"}
  },
  "cities": {
    "포항": {"province": "경북", "aliases": ["포항시"]},
    "경주": {"province": "경북", "aliases": ["경주시"]},
    "김천": {"province": "경북", "aliases": ["김천시"]},
    "안동": {"province": "경북", "aliases": ["안동시"]},
    "구미": {"province": "경북", "aliases": ["구미시"]},
    "영주": {"province": "경북", "aliases": ["영주시"]},
    "영천": {"province": "경북", "aliases": ["영천시"]},
    "상주": {"province": "경북", "aliases": ["상주시"]},
    "문경": {"province": "경북", "aliases": ["문경시"]},
    "경산": {"province": "경북", "aliases": ["경산시"]},
    "칠곡": {"province": "경북", "aliases": ["칠곡군"]},
    "일산": {"province": "경기", "aliases": ["일산구", "일산동구", "일산서구"]},
    "분당": {"province": "경기", "aliases": ["분당구"]},
    "수원": {"province": "경기", "aliases": ["수원시"]},
    "성남": {"province": "경기", "aliases": ["성남시"]},
    "고양": {"province": "경기", "aliases": ["고양시"]},
    "용인": {"province": "경기", "aliases": ["용인시"]},
    "부천": {"province": "경기", "aliases": ["부천시"]},
    "안산": {"province": "경기", "aliases": ["안산시"]},
    "안양": {"province": "경기", "aliases": ["안양시"]},
    "남양주": {"province": "경기", "aliases": ["남양주시"]},
    "화성": {"province": "경기", "aliases": ["화성시"]},
    "평택": {"province": "경기", "aliases": ["평택시"]},
    "의정부": {"province": "경기", "aliases": ["의정부시"]},
    "시흥": {"province": "경기", "aliases": ["시흥시"]},
    "파주": {"province": "경기", "aliases": ["파주시"]},
    "광명": {"province": "경기", "aliases": ["광명시"]},
    "김포": {"province": "경기", "aliases": ["김포시"]},
    "군포": {"province": "경기", "aliases": ["군포시"]},
    "광주": {"province": "경기", "aliases": ["광주시"]},
    "이천": {"province": "경기", "aliases": ["이천시"]},
    "양주": {"province": "경기", "aliases": ["양주시"]},
    "오산": {"province": "경기", "aliases": ["오산시"]},
    "구리": {"province": "경기", "aliases": ["구리시"]},
    "안성": {"province": "경기", "aliases": ["안성시"]},
    "포천": {"province": "경기", "aliases": ["포천시"]},
    "의왕": {"province": "경기", "aliases": ["의왕시"]},
    "하남": {"province": "경기", "aliases": ["하남시"]},
    "여주": {"province": "경기", "aliases": ["여주시"]},
    "동두천": {"province": "경기", "aliases": ["동두천시"]},
    "과천": {"province": "경기", "aliases": ["과천시"]},
    "창원": {"province": "경남", "aliases": ["창원시"]},
    "김해": {"province": "경남", "aliases": ["김해시"]},
    "진주": {"province": "경남", "aliases": ["진주시"]},
    "양산": {"province": "경남", "aliases": ["양산시"]},
    "거제": {"province": "경남", "aliases": ["거제시"]},
    "통영": {"province": "경남", "aliases": ["통영시"]},
    "사천": {"province": "경남", "aliases": ["사천시"]},
    "밀양": {"province": "경남", "aliases": ["밀양시"]},
    "강진": {"province": "전남", "aliases": ["강진군"]}
  },
  "districts": {
    "북구": {"cities": ["포항", "대구", "광주", "울산"]},
    "남구": {"cities": ["포항", "대구", "광주", "울산", "부산"]},
    "동구": {"cities": ["대구", "광주", "울산", "부산", "대전"]},
    "서구": {"cities": ["대구", "광주", "부산", "대전", "인천"]},
    "중구": {"cities": ["대구", "부산", "대전", "인천", "서울"]},
    "강남구": {"cities": ["서울"]},
    "강북구": {"cities": ["서울"]},
    "강서구": {"cities": ["서울", "부산"]},
    "강동구": {"cities": ["서울"]}
  },
  "sub_districts": [
    "도암면", "덕서리", "도산면", "오륜리", "기북면", "대곡리"
  ]
}
```

### 요구사항
- 주요 시/도 17개 모두 포함
- 주요 시/군/구 최소 100개 이상
- 약칭과 정식 명칭 매핑
- 확장 가능한 구조

---

## 📝 작업 3: location_service.py 구현

파일 위치: `shared/services/location_service.py`

### 함수 명세
```python
"""
지역명 추출 및 비교 서비스

제목에서 한국 행정구역명을 추출하고 비교하는 기능을 제공합니다.
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class LocationService:
    """지역명 추출 및 비교 서비스"""
    
    _instance = None
    _location_data = None
    
    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._location_data is None:
            self._load_location_data()
    
    def _load_location_data(self) -> None:
        """지역명 데이터 로드"""
        # 구현 필요
        pass
    
    def extract_location(self, title: str) -> Optional[Dict]:
        """
        제목에서 지역명 추출
        
        Args:
            title: 분석할 제목
            
        Returns:
            추출된 지역 정보 딕셔너리 또는 None
            {
                "province": "경북",
                "city": "포항",
                "district": "북구",
                "sub_district": "기북면",
                "raw_text": "경북 포항시 북구 기북면"
            }
        """
        # 구현 필요
        pass
    
    def normalize_location(self, location: Dict) -> str:
        """
        지역 정보를 표준화된 문자열로 변환
        
        Args:
            location: extract_location 결과
            
        Returns:
            표준화된 지역명 (예: "경북-포항")
        """
        # 구현 필요
        pass
    
    def is_same_location(self, loc1: Optional[Dict], loc2: Optional[Dict]) -> bool:
        """
        두 지역이 동일한지 비교
        
        규칙:
        1. 둘 다 None이면 True (지역 없음끼리는 매칭 가능)
        2. 하나만 None이면 True (지역 없는 것과 있는 것은 매칭 가능)
        3. 둘 다 있으면 province+city 기준으로 비교
        
        Args:
            loc1: 첫 번째 지역 정보
            loc2: 두 번째 지역 정보
            
        Returns:
            동일 여부
        """
        # 구현 필요
        pass
    
    def remove_location_from_title(self, title: str, location: Optional[Dict]) -> str:
        """
        제목에서 지역명 부분 제거
        
        Args:
            title: 원본 제목
            location: 추출된 지역 정보
            
        Returns:
            지역명이 제거된 제목
        """
        # 구현 필요
        pass


# 편의 함수
def extract_location(title: str) -> Optional[Dict]:
    """제목에서 지역명 추출 (편의 함수)"""
    return LocationService().extract_location(title)


def is_same_location(loc1: Optional[Dict], loc2: Optional[Dict]) -> bool:
    """두 지역 동일성 비교 (편의 함수)"""
    return LocationService().is_same_location(loc1, loc2)


def remove_location(title: str, location: Optional[Dict]) -> str:
    """제목에서 지역명 제거 (편의 함수)"""
    return LocationService().remove_location_from_title(title, location)
```

### 구현 요구사항

1. **싱글톤 패턴**: JSON 데이터를 한 번만 로드
2. **지역명 추출 우선순위**:
   - 시/도 → 시/군/구 → 구 → 읍/면/동/리
3. **약칭 처리**: "경북" = "경상북도"
4. **부분 일치 처리**: "포항시 북구" → city="포항", district="북구"
5. **로깅**: 추출 과정 디버그 로그

---

## 📝 작업 4: __init__.py 생성

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

__all__ = [
    "LocationService",
    "extract_location",
    "is_same_location",
    "remove_location",
]
```

---

## ✅ 완료 조건

1. [ ] `shared/data/korean_locations.json` 생성 (100개 이상 지역)
2. [ ] `shared/services/location_service.py` 구현 (< 300줄)
3. [ ] `shared/services/__init__.py` 생성
4. [ ] 모든 함수에 타입 힌트 적용
5. [ ] 모든 함수에 Docstring 작성
6. [ ] 에러 처리 포함

---

## 🧪 테스트 케이스
```python
# 테스트 1: 지역명 추출
title1 = "포항 이삿짐센터 포장이사 업체추천"
loc1 = extract_location(title1)
assert loc1["city"] == "포항"

# 테스트 2: 다른 지역 비교
title2 = "일산 이삿짐센터 포장이사 업체추천"
loc2 = extract_location(title2)
assert is_same_location(loc1, loc2) == False

# 테스트 3: 같은 지역 비교
title3 = "경북 포항시 북구 이삿짐센터"
loc3 = extract_location(title3)
assert is_same_location(loc1, loc3) == True

# 테스트 4: 지역명 제거
cleaned = remove_location(title1, loc1)
assert "포항" not in cleaned

# 테스트 5: 지역 없는 제목
title5 = "이삭토스트 맛집탐방 인기메뉴"
loc5 = extract_location(title5)
assert loc5 is None
```

---

## 📚 참조

- 레거시: 없음 (신규 기능)
- 한국 행정구역 정보: 행정안전부 자료 참고

---

**다음 Phase**: Phase B (유사도 매칭 서비스 V2)
