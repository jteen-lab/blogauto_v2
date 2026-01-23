# 🔧 BlogAuto V2 유사도 매칭 시스템 개선 프롬프트

> **버전**: v1.0.0  
> **작성일**: 2025-01-22  
> **목적**: 임시제목 → 정식제목 이동 시 유사도 매칭 및 그룹핑 기능 개선

---

## 📋 작업 개요

### 현재 문제점

1. **임계값 전달 누락**
   - `flows_execute.py:651`에서 75% 설정
   - `flows_execute.py:735`에서 서비스 호출 시 threshold 파라미터 미전달
   - `similarity_service.py:32`에서 80%로 하드코딩

2. **단순 문자열 유사도의 한계**
   - 현재: 토큰 정렬 + 문자열 유사도 방식
   - "경조화환", "근조화환", "장례식화환"을 다른 단어로 인식
   - 문맥적 의미(semantic meaning)를 이해하지 못함

3. **지역명 처리 부재**
   - 지역명만 다르고 나머지 동일 → 잘못된 그룹핑 발생 가능
   - 지역명 없는 제목 처리 로직 없음

4. **그룹 시스템 미구현**
   - 활성 그룹 (2개 이상 제목 매칭) / 일반 그룹 구분 없음
   - 대표 제목 표시 방식 미흡

---

## 🎯 구현 목표

### Phase 1: 긴급 버그 수정 (우선순위: 높음)

#### Task 1-1: 임계값 전달 버그 수정

**파일**: `services/republish/app/api/flows_execute.py`

```python
# 수정 전 (line 735 근처)
transfer_result = await service.move_to_main(temp_ids, auto_group=auto_group)

# 수정 후
transfer_result = await service.move_to_main(
    temp_ids, 
    auto_group=auto_group,
    threshold=threshold  # 임계값 전달 추가
)
```

#### Task 1-2: 기본 임계값 통일

**파일**: `services/republish/shared/services/similarity_service.py`

```python
# 수정 전 (line 32)
DEFAULT_SIMILARITY_THRESHOLD = 80.0

# 수정 후
DEFAULT_SIMILARITY_THRESHOLD = 75.0  # 데이터 모듈 설정과 통일
```

---

### Phase 2: 다단계 하이브리드 유사도 시스템 구현

#### 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    다단계 유사도 매칭 시스템                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stage 0: 지역명 호환성 검사 (필터링/패널티)                    │
│  ├─ 양쪽 모두 지역 있고 일치 → 통과 (패널티 0%)                │
│  ├─ 양쪽 모두 지역 있고 불일치 → 차단 (유사도 0)               │
│  ├─ 한쪽만 지역 있음 → 통과 (패널티 15%)                       │
│  └─ 양쪽 모두 지역 없음 → 통과 (패널티 0%)                     │
│                                                             │
│  Stage 1: 캐노니컬 키 완전 일치                               │
│  ├─ 정규화된 키(지역+장소+주제) 생성                           │
│  └─ 일치 시 → 100% 유사도 (즉시 그룹핑)                       │
│                                                             │
│  Stage 2: 키워드 기반 유사도 (개선)                           │
│  ├─ 형태소 분석으로 핵심 키워드 추출                           │
│  ├─ TF-IDF 가중치 적용                                       │
│  └─ 코사인 유사도 계산                                        │
│                                                             │
│  Stage 3: 시맨틱 유사도 (선택적 - Phase 3에서 구현)            │
│  ├─ 한국어 Sentence-BERT 임베딩                              │
│  └─ 벡터 코사인 유사도                                        │
│                                                             │
│  Stage 4: 최종 점수 계산                                      │
│  └─ 가중 합산 - 지역 패널티 적용                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Task 2-1: 지역명 추출 및 호환성 검사 모듈

**새 파일 생성**: `services/republish/shared/services/location_service.py`

```python
"""
지역명 추출 및 호환성 검사 서비스

기능:
1. 제목에서 지역명 추출 (정규식 기반)
2. 지역명 정규화 (경상북도 → 경북)
3. 두 제목 간 지역 호환성 검사
"""

from typing import List, Dict, Optional
import re

# 지역명 정규화 사전
LOCATION_ALIASES = {
    # 광역시/도
    "서울": ["서울시", "서울특별시", "서울"],
    "부산": ["부산시", "부산광역시", "부산"],
    "대구": ["대구시", "대구광역시", "대구"],
    "인천": ["인천시", "인천광역시", "인천"],
    "광주": ["광주시", "광주광역시", "광주"],
    "대전": ["대전시", "대전광역시", "대전"],
    "울산": ["울산시", "울산광역시", "울산"],
    "세종": ["세종시", "세종특별자치시", "세종"],
    "경기": ["경기도", "경기"],
    "강원": ["강원도", "강원특별자치도", "강원"],
    "충북": ["충청북도", "충북"],
    "충남": ["충청남도", "충남"],
    "전북": ["전라북도", "전북특별자치도", "전북"],
    "전남": ["전라남도", "전남"],
    "경북": ["경상북도", "경북"],
    "경남": ["경상남도", "경남"],
    "제주": ["제주도", "제주특별자치도", "제주"],
}

# 시/군/구 목록 (주요 도시만 - 필요시 확장)
CITY_NAMES = [
    # 경북
    "경주", "경주시", "포항", "포항시", "구미", "구미시", "김천", "김천시",
    "안동", "안동시", "영주", "영주시", "상주", "상주시", "문경", "문경시",
    # 경남
    "창원", "창원시", "진주", "진주시", "통영", "통영시", "김해", "김해시",
    "밀양", "밀양시", "거제", "거제시", "양산", "양산시",
    # 서울 구
    "강남", "강남구", "강북", "강북구", "강서", "강서구", "강동", "강동구",
    "서초", "서초구", "송파", "송파구", "마포", "마포구", "영등포", "영등포구",
    # 기타 주요 도시 추가 가능
]


class LocationService:
    """지역명 처리 서비스"""
    
    def __init__(self):
        self._build_location_patterns()
    
    def _build_location_patterns(self):
        """지역명 추출용 정규식 패턴 생성"""
        # 광역시/도 패턴
        province_terms = []
        for aliases in LOCATION_ALIASES.values():
            province_terms.extend(aliases)
        
        # 시/군/구 패턴
        city_terms = CITY_NAMES
        
        # 전체 지역명 패턴
        all_terms = province_terms + city_terms
        all_terms_sorted = sorted(all_terms, key=len, reverse=True)  # 긴 것 먼저 매칭
        
        self.location_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(t) for t in all_terms_sorted) + r')\b'
        )
    
    def extract_locations(self, title: str) -> List[str]:
        """
        제목에서 지역명 추출
        
        Args:
            title: 분석할 제목
            
        Returns:
            추출된 지역명 리스트 (정규화됨)
        """
        if not title:
            return []
        
        matches = self.location_pattern.findall(title)
        normalized = [self._normalize_location(loc) for loc in matches]
        
        # 중복 제거 및 순서 유지
        seen = set()
        result = []
        for loc in normalized:
            if loc not in seen:
                seen.add(loc)
                result.append(loc)
        
        return result
    
    def _normalize_location(self, location: str) -> str:
        """지역명 정규화"""
        for standard, aliases in LOCATION_ALIASES.items():
            if location in aliases:
                return standard
        
        # 시/군/구에서 접미사 제거
        for suffix in ["시", "군", "구"]:
            if location.endswith(suffix) and len(location) > 2:
                base = location[:-1]
                if base + suffix in CITY_NAMES:
                    return base
        
        return location
    
    def check_location_compatibility(
        self, 
        title1: str, 
        title2: str
    ) -> Dict:
        """
        두 제목 간 지역 호환성 검사
        
        Returns:
            {
                "compatible": bool,      # 그룹핑 가능 여부
                "penalty": float,        # 유사도 감점 비율 (0 ~ 1)
                "reason": str,           # 판정 사유
                "locations1": list,      # 제목1의 지역명
                "locations2": list       # 제목2의 지역명
            }
        """
        loc1 = self.extract_locations(title1)
        loc2 = self.extract_locations(title2)
        
        has_loc1 = len(loc1) > 0
        has_loc2 = len(loc2) > 0
        
        # Case 4: 둘 다 지역명 없음 → 정상 진행
        if not has_loc1 and not has_loc2:
            return {
                "compatible": True,
                "penalty": 0.0,
                "reason": "지역명 미사용 제목",
                "locations1": loc1,
                "locations2": loc2
            }
        
        # Case 1 & 2: 둘 다 지역명 있음
        if has_loc1 and has_loc2:
            loc1_set = set(loc1)
            loc2_set = set(loc2)
            
            # 교집합 존재 → 일치
            common = loc1_set & loc2_set
            if common:
                return {
                    "compatible": True,
                    "penalty": 0.0,
                    "reason": f"지역 일치: {common}",
                    "locations1": loc1,
                    "locations2": loc2
                }
            else:
                # Case 2: 불일치 → 그룹핑 불가
                return {
                    "compatible": False,
                    "penalty": 1.0,
                    "reason": f"지역 불일치: {loc1_set} vs {loc2_set}",
                    "locations1": loc1,
                    "locations2": loc2
                }
        
        # Case 3: 한쪽만 지역명 있음 → 진행하되 패널티
        return {
            "compatible": True,
            "penalty": 0.15,  # 15% 감점
            "reason": "한쪽만 지역명 존재 - 불확실성 패널티 적용",
            "locations1": loc1,
            "locations2": loc2
        }


# 싱글톤 인스턴스
_location_service: Optional[LocationService] = None

def get_location_service() -> LocationService:
    """LocationService 싱글톤 인스턴스 반환"""
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service
```

#### Task 2-2: 캐노니컬 키 생성 모듈

**새 파일 생성**: `services/republish/shared/services/canonical_key_service.py`

```python
"""
캐노니컬 키 생성 서비스

캐노니컬 키: 제목의 핵심 요소를 정규화한 고유 식별자
형식: {지역}|{장소}|{주제}

완전 일치 시 100% 유사도로 즉시 그룹핑
"""

from typing import Optional, List
import re
from .location_service import get_location_service


class CanonicalKeyService:
    """캐노니컬 키 생성 서비스"""
    
    def __init__(self):
        self.location_service = get_location_service()
        self._build_patterns()
    
    def _build_patterns(self):
        """키워드 추출용 패턴"""
        # 장소/기관 키워드 (확장 가능)
        self.place_keywords = [
            "병원", "의원", "장례식장", "예식장", "호텔", "리조트",
            "대학교", "대학", "고등학교", "중학교", "초등학교",
            "아파트", "빌라", "오피스텔", "주상복합",
            "백화점", "마트", "쇼핑몰", "시장",
            "교회", "성당", "사찰", "절",
        ]
        
        # 서비스/주제 키워드 (확장 가능)
        self.service_keywords = [
            # 화환 관련
            "근조화환", "경조화환", "장례식화환", "조화", "화환",
            "축하화환", "개업화환", "취임화환",
            # 꽃배달
            "꽃배달", "플라워", "꽃바구니", "꽃다발",
            # 기타 서비스
            "배달", "주문", "예약",
        ]
    
    def generate_canonical_key(self, title: str) -> Optional[str]:
        """
        제목에서 캐노니컬 키 생성
        
        Args:
            title: 원본 제목
            
        Returns:
            캐노니컬 키 (형식: "지역|장소|주제") 또는 None
        """
        if not title:
            return None
        
        # 1. 지역 추출
        locations = self.location_service.extract_locations(title)
        location_key = "_".join(locations) if locations else ""
        
        # 2. 장소/기관 추출
        places = self._extract_places(title)
        place_key = "_".join(places) if places else ""
        
        # 3. 서비스/주제 추출
        services = self._extract_services(title)
        service_key = "_".join(services) if services else ""
        
        # 키 생성 (최소 하나 이상의 요소 필요)
        if not any([location_key, place_key, service_key]):
            return None
        
        return f"{location_key}|{place_key}|{service_key}"
    
    def _extract_places(self, title: str) -> List[str]:
        """장소/기관명 추출"""
        found = []
        title_lower = title.lower()
        
        for keyword in self.place_keywords:
            if keyword in title_lower:
                # 키워드 앞의 고유명사도 함께 추출 시도
                pattern = rf'(\S*{re.escape(keyword)})'
                matches = re.findall(pattern, title)
                for match in matches:
                    # 정규화: 공백 제거
                    normalized = match.replace(" ", "")
                    if normalized and normalized not in found:
                        found.append(normalized)
        
        return found
    
    def _extract_services(self, title: str) -> List[str]:
        """서비스/주제 키워드 추출"""
        found = []
        
        for keyword in self.service_keywords:
            if keyword in title:
                if keyword not in found:
                    found.append(keyword)
        
        # 우선순위 정렬 (더 구체적인 것 우선)
        found.sort(key=len, reverse=True)
        
        return found[:2]  # 상위 2개만
    
    def check_canonical_match(self, title1: str, title2: str) -> dict:
        """
        두 제목의 캐노니컬 키 일치 여부 확인
        
        Returns:
            {
                "match": bool,
                "key1": str or None,
                "key2": str or None
            }
        """
        key1 = self.generate_canonical_key(title1)
        key2 = self.generate_canonical_key(title2)
        
        # 둘 다 키가 있고 완전 일치
        match = (
            key1 is not None and 
            key2 is not None and 
            key1 == key2
        )
        
        return {
            "match": match,
            "key1": key1,
            "key2": key2
        }


# 싱글톤 인스턴스
_canonical_service: Optional[CanonicalKeyService] = None

def get_canonical_key_service() -> CanonicalKeyService:
    """CanonicalKeyService 싱글톤 인스턴스 반환"""
    global _canonical_service
    if _canonical_service is None:
        _canonical_service = CanonicalKeyService()
    return _canonical_service
```

#### Task 2-3: 개선된 유사도 서비스

**파일 수정**: `services/republish/shared/services/similarity_service.py`

기존 `calculate_similarity_v2` 함수를 개선하여 다단계 하이브리드 방식으로 변경:

```python
"""
개선된 유사도 매칭 서비스

다단계 하이브리드 접근:
- Stage 0: 지역명 호환성 검사
- Stage 1: 캐노니컬 키 완전 일치
- Stage 2: 키워드 기반 유사도
- Stage 4: 최종 점수 계산 (지역 패널티 적용)
"""

from typing import Dict, List, Optional, Tuple
from .location_service import get_location_service
from .canonical_key_service import get_canonical_key_service

# 기본 임계값 (데이터 모듈 설정과 통일)
DEFAULT_SIMILARITY_THRESHOLD = 75.0


class SimilarityService:
    """개선된 유사도 매칭 서비스"""
    
    def __init__(self):
        self.location_service = get_location_service()
        self.canonical_service = get_canonical_key_service()
    
    def calculate_similarity(
        self,
        title1: str,
        title2: str,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> Dict:
        """
        다단계 하이브리드 유사도 계산
        
        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목
            threshold: 그룹핑 임계값
            
        Returns:
            {
                "score": float,           # 최종 유사도 점수
                "groupable": bool,        # 그룹핑 가능 여부
                "reason": str,            # 판정 사유
                "details": {              # 상세 정보
                    "stage": str,         # 최종 판정 단계
                    "location_check": dict,
                    "canonical_check": dict,
                    "keyword_score": float,
                    "location_penalty": float,
                    "base_score": float
                }
            }
        """
        # Stage 0: 지역명 호환성 검사
        location_check = self.location_service.check_location_compatibility(
            title1, title2
        )
        
        if not location_check["compatible"]:
            return {
                "score": 0,
                "groupable": False,
                "reason": location_check["reason"],
                "details": {
                    "stage": "Stage 0: 지역 불일치로 차단",
                    "location_check": location_check,
                    "canonical_check": None,
                    "keyword_score": 0,
                    "location_penalty": 1.0,
                    "base_score": 0
                }
            }
        
        # Stage 1: 캐노니컬 키 완전 일치
        canonical_check = self.canonical_service.check_canonical_match(
            title1, title2
        )
        
        if canonical_check["match"]:
            return {
                "score": 100.0,
                "groupable": True,
                "reason": f"캐노니컬 키 완전 일치: {canonical_check['key1']}",
                "details": {
                    "stage": "Stage 1: 캐노니컬 키 일치",
                    "location_check": location_check,
                    "canonical_check": canonical_check,
                    "keyword_score": 100,
                    "location_penalty": 0,
                    "base_score": 100
                }
            }
        
        # Stage 2: 키워드 기반 유사도
        keyword_score = self._calculate_keyword_similarity(title1, title2)
        
        # Stage 4: 최종 점수 계산 (지역 패널티 적용)
        penalty = location_check["penalty"]
        final_score = keyword_score * (1 - penalty)
        
        return {
            "score": round(final_score, 2),
            "groupable": final_score >= threshold,
            "reason": location_check["reason"],
            "details": {
                "stage": "Stage 2: 키워드 유사도",
                "location_check": location_check,
                "canonical_check": canonical_check,
                "keyword_score": round(keyword_score, 2),
                "location_penalty": penalty,
                "base_score": round(keyword_score, 2)
            }
        }
    
    def _calculate_keyword_similarity(
        self,
        title1: str,
        title2: str
    ) -> float:
        """
        키워드 기반 유사도 계산 (개선된 버전)
        
        기존 token_sort_ratio 방식을 유지하되,
        추가 가중치 로직 적용
        """
        from rapidfuzz import fuzz
        
        # 기본 유사도 (기존 로직 유지)
        base_score = fuzz.token_sort_ratio(title1, title2)
        
        # 추가: 공통 키워드 보너스
        keywords1 = set(self._extract_keywords(title1))
        keywords2 = set(self._extract_keywords(title2))
        
        if keywords1 and keywords2:
            common = keywords1 & keywords2
            total = keywords1 | keywords2
            
            if total:
                keyword_overlap = len(common) / len(total)
                # 키워드 겹침이 많으면 보너스 (최대 10점)
                bonus = keyword_overlap * 10
                base_score = min(100, base_score + bonus)
        
        return base_score
    
    def _extract_keywords(self, title: str) -> List[str]:
        """핵심 키워드 추출 (간단 버전)"""
        # 불용어 제거
        stopwords = {"의", "에서", "을", "를", "이", "가", "은", "는", "및", "또는"}
        
        # 공백 기준 토큰화
        tokens = title.split()
        
        # 2글자 이상, 불용어 제외
        keywords = [
            t for t in tokens 
            if len(t) >= 2 and t not in stopwords
        ]
        
        return keywords
    
    async def find_similar_titles(
        self,
        target_title: str,
        candidate_titles: List[Tuple[int, str]],
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> List[Dict]:
        """
        대상 제목과 유사한 후보 제목들 찾기
        
        Args:
            target_title: 대상 제목
            candidate_titles: [(id, title), ...] 형태의 후보 목록
            threshold: 유사도 임계값
            
        Returns:
            유사한 제목 목록 (유사도 내림차순 정렬)
        """
        results = []
        
        for title_id, candidate_title in candidate_titles:
            similarity = self.calculate_similarity(
                target_title,
                candidate_title,
                threshold
            )
            
            if similarity["groupable"]:
                results.append({
                    "id": title_id,
                    "title": candidate_title,
                    "similarity": similarity
                })
        
        # 유사도 내림차순 정렬
        results.sort(key=lambda x: x["similarity"]["score"], reverse=True)
        
        return results


# 싱글톤 인스턴스
_similarity_service: Optional[SimilarityService] = None

def get_similarity_service() -> SimilarityService:
    """SimilarityService 싱글톤 인스턴스 반환"""
    global _similarity_service
    if _similarity_service is None:
        _similarity_service = SimilarityService()
    return _similarity_service
```

---

### Phase 3: 활성 그룹 시스템 구현 (선택)

#### Task 3-1: 그룹 모델 확장

- 기존 그룹 모델에 `is_active` 필드 추가 (2개 이상 제목 = 활성)
- 대표 제목 관리 로직 구현

#### Task 3-2: 그룹 UI 개선

- 활성 그룹: 📁 폴더 이모지 + 클릭 시 멤버 목록 팝업
- 대표 제목: 배경색 강조 (★ 이모지 대신)

---

## 📁 파일 구조

```
services/republish/
├── shared/
│   └── services/
│       ├── location_service.py      # [신규] 지역명 처리
│       ├── canonical_key_service.py # [신규] 캐노니컬 키
│       └── similarity_service.py    # [수정] 개선된 유사도
│
├── app/
│   └── api/
│       └── flows_execute.py         # [수정] 임계값 전달 버그 수정
```

---

## ✅ 체크리스트

### Phase 1 완료 조건
- [ ] `flows_execute.py`에서 threshold 파라미터 전달
- [ ] `similarity_service.py` 기본값 75%로 통일
- [ ] 기존 테스트 통과

### Phase 2 완료 조건
- [ ] `location_service.py` 생성 및 테스트
- [ ] `canonical_key_service.py` 생성 및 테스트
- [ ] `similarity_service.py` 다단계 방식으로 개선
- [ ] 예시 제목 테스트 통과:
  - 경북 경주 동국대학교경주병원 장례식장 근조화환 경조화환
  - 경상북도 경주시 동국대학교경주병원 장례식장 근조화환 장례식조화가격
  - 경북 경주 동국대학교경주병원 장례식장 장례식화환 근조화환당일
  - → 모두 동일 그룹으로 매칭 (유사도 90%+)

### 코드 품질
- [ ] 파일당 < 500줄
- [ ] 함수당 < 50줄
- [ ] 타입 힌트 완료
- [ ] Docstring 완료
- [ ] 에러 처리 완료

---

## 📚 참고 자료

### 한국어 NLP 라이브러리
- rapidfuzz: 문자열 유사도 (기존 사용 중)
- kiwipiepy: 한국어 형태소 분석 (Phase 3에서 고려)
- ko-sentence-transformers: 시맨틱 임베딩 (Phase 3에서 고려)

### 레거시 참조 (복사 금지, 로직만 참조)
- `blogauto_new/core/` 내 유사도 관련 코드
- 캐노니컬 키 생성 로직
- 학습 데이터 기반 매칭 로직

---

## 🚀 실행 순서

1. Phase 1 긴급 버그 수정 먼저 진행
2. 로컬 Docker 테스트
3. Phase 2 신규 모듈 구현
4. 통합 테스트
5. Oracle 서버 배포

---

**작성자**: Claude Chat (네오)  
**검토 필요**: @backend-agent, @reviewer-agent
