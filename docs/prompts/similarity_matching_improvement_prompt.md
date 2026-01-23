# BlogAuto V2 유사도 매칭 시스템 개선 프롬프트

> **버전**: v1.0.0  
> **작성일**: 2025-01-22  
> **대상**: Claude Code Multi-Agent System  
> **목적**: 임시제목 → 정식제목 이동 시 유사도 매칭 및 그룹핑 기능 개선

---

## 📋 작업 개요

### 현재 문제점

1. **임계값 설정이 무시됨**
   - 데이터 모듈에서 75% 설정 → 실제 80% 사용
   - `flows_execute.py:735`에서 threshold 파라미터 전달 누락
   - `shared/services/similarity_service.py:32`에 80% 하드코딩

2. **유사도 매칭 로직이 문맥을 이해하지 못함**
   - 단순 토큰 정렬 + 문자열 유사도 방식
   - "경조화환", "근조화환", "장례식화환"을 다른 단어로 인식
   - 동일한 장소+주제임에도 74% 이하로 계산

3. **그룹 시스템 설계가 요구사항과 다름**
   - 활성 그룹 / 일반 그룹 구분 없음
   - 대표 제목 표시 방식이 다름 (★ 이모지 vs 배경색)

4. **레거시 기능 미포팅**
   - 캐노니컬 키 완전일치 로직 없음
   - 형태소 분석 없음

### 테스트 케이스 (반드시 이 제목들로 테스트)

```
제목1: 경북 경주 동국대학교경주병원 장례식장 근조화환 경조화환 경조사화환
제목2: 경상북도 경주시 동국대학교경주병원 장례식장 근조화환 장례식조화가격 근조화환조화배달
제목3: 경북 경주 동국대학교경주병원 장례식장 장례식화환 근조화환당일 근조화환오브제
```

**예상 결과**: 세 제목 모두 동일한 활성 그룹으로 묶여야 함

---

## 🎯 구현 목표

### Phase 1: 즉시 수정 (버그 픽스)

1. **임계값 전달 버그 수정**
   - 파일: `services/republish/app/api/flows_execute.py`
   - 위치: 약 735번째 줄
   - 문제: `move_to_main()` 호출 시 threshold 파라미터 누락
   - 해결: threshold 파라미터 전달 추가

2. **기본 임계값 통일**
   - 파일: `shared/services/similarity_service.py`
   - 위치: 32번째 줄
   - 문제: `DEFAULT_SIMILARITY_THRESHOLD = 80.0` 하드코딩
   - 해결: 75.0으로 변경 또는 설정에서 가져오도록 수정

### Phase 2: 핵심 개선 (다단계 유사도 시스템)

#### 2.1 지역명 호환성 검사 모듈

**새 파일 생성**: `shared/services/location_service.py`

```python
"""
지역명 추출 및 호환성 검사 서비스

4가지 케이스 처리:
- Case 1: 양쪽 지역 있음 + 일치 → 그룹핑 진행 (패널티 0%)
- Case 2: 양쪽 지역 있음 + 불일치 → 그룹핑 불가
- Case 3: 한쪽만 지역 있음 → 그룹핑 진행 (패널티 15%)
- Case 4: 양쪽 지역 없음 → 그룹핑 진행 (패널티 0%)
"""

from typing import List, Dict, Optional
import re

# 지역명 정규화 매핑
LOCATION_ALIASES = {
    # 시/도 단위
    "경북": ["경상북도", "경북"],
    "경남": ["경상남도", "경남"],
    "전북": ["전라북도", "전북", "전북특별자치도"],
    "전남": ["전라남도", "전남"],
    "충북": ["충청북도", "충북"],
    "충남": ["충청남도", "충남"],
    "강원": ["강원도", "강원", "강원특별자치도"],
    "경기": ["경기도", "경기"],
    "제주": ["제주도", "제주", "제주특별자치도"],
    "서울": ["서울시", "서울특별시", "서울"],
    "부산": ["부산시", "부산광역시", "부산"],
    "대구": ["대구시", "대구광역시", "대구"],
    "인천": ["인천시", "인천광역시", "인천"],
    "광주": ["광주시", "광주광역시", "광주"],
    "대전": ["대전시", "대전광역시", "대전"],
    "울산": ["울산시", "울산광역시", "울산"],
    "세종": ["세종시", "세종특별자치시", "세종"],
}

# 주요 시/군/구 목록 (확장 가능)
CITY_PATTERNS = [
    r"(\w+시)",  # OO시
    r"(\w+군)",  # OO군
    r"(\w+구)",  # OO구
]


def extract_locations(title: str) -> List[str]:
    """
    제목에서 지역명 추출
    
    Args:
        title: 제목 문자열
        
    Returns:
        추출된 지역명 리스트 (정규화 전)
    """
    locations = []
    
    # 시/도 단위 추출
    for standard, aliases in LOCATION_ALIASES.items():
        for alias in aliases:
            if alias in title:
                locations.append(alias)
                break
    
    # 시/군/구 패턴 추출
    for pattern in CITY_PATTERNS:
        matches = re.findall(pattern, title)
        locations.extend(matches)
    
    return list(set(locations))


def normalize_locations(locations: List[str]) -> List[str]:
    """
    지역명 정규화 (다양한 표현 → 표준 표현)
    
    Args:
        locations: 추출된 지역명 리스트
        
    Returns:
        정규화된 지역명 리스트
    """
    normalized = []
    for loc in locations:
        matched = False
        for standard, aliases in LOCATION_ALIASES.items():
            if loc in aliases:
                normalized.append(standard)
                matched = True
                break
        if not matched:
            normalized.append(loc)
    return list(set(normalized))


def check_location_compatibility(title1: str, title2: str) -> Dict:
    """
    두 제목의 지역 호환성 검사
    
    Args:
        title1: 첫 번째 제목
        title2: 두 번째 제목
        
    Returns:
        {
            "compatible": bool,      # 그룹핑 가능 여부
            "penalty": float,        # 유사도 감점 비율 (0 ~ 1)
            "reason": str,           # 판정 사유
            "locations1": List[str], # 제목1의 지역
            "locations2": List[str]  # 제목2의 지역
        }
    """
    loc1_raw = extract_locations(title1)
    loc2_raw = extract_locations(title2)
    
    loc1 = set(normalize_locations(loc1_raw))
    loc2 = set(normalize_locations(loc2_raw))
    
    has_loc1 = len(loc1) > 0
    has_loc2 = len(loc2) > 0
    
    result = {
        "locations1": list(loc1),
        "locations2": list(loc2)
    }
    
    # Case 4: 둘 다 지역명 없음
    if not has_loc1 and not has_loc2:
        return {
            **result,
            "compatible": True,
            "penalty": 0.0,
            "reason": "지역명 미사용 제목들"
        }
    
    # Case 1 & 2: 둘 다 지역명 있음
    if has_loc1 and has_loc2:
        intersection = loc1 & loc2
        if intersection:
            # Case 1: 일치
            return {
                **result,
                "compatible": True,
                "penalty": 0.0,
                "reason": f"지역 일치: {intersection}"
            }
        else:
            # Case 2: 불일치
            return {
                **result,
                "compatible": False,
                "penalty": 1.0,
                "reason": f"지역 불일치: {loc1} vs {loc2}"
            }
    
    # Case 3: 한쪽만 지역명 있음
    return {
        **result,
        "compatible": True,
        "penalty": 0.15,  # 15% 패널티
        "reason": "한쪽만 지역명 존재 - 불확실성 패널티 적용"
    }
```

#### 2.2 캐노니컬 키 시스템

**새 파일 생성**: `shared/services/canonical_key_service.py`

```python
"""
캐노니컬 키 생성 및 비교 서비스

캐노니컬 키: 제목의 핵심 요소를 정규화한 고유 식별자
형식: {지역}|{장소}|{주제}

캐노니컬 키가 완전 일치하면 100% 유사도로 즉시 그룹핑
"""

from typing import Optional, List
import re
from kiwipiepy import Kiwi  # 형태소 분석기

# Kiwi 초기화 (전역)
kiwi = Kiwi()


def extract_nouns(text: str) -> List[str]:
    """형태소 분석으로 명사 추출"""
    result = kiwi.analyze(text)
    nouns = []
    for token, pos, _, _ in result[0][0]:
        if pos.startswith('NN'):  # 명사류
            nouns.append(token)
    return nouns


def normalize_text(text: str) -> str:
    """텍스트 정규화 (공백, 특수문자 제거)"""
    # 공백 제거
    text = re.sub(r'\s+', '', text)
    # 특수문자 제거 (한글, 영문, 숫자만 유지)
    text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
    return text.lower()


def generate_canonical_key(
    title: str,
    location: Optional[str] = None,
    place: Optional[str] = None,
    topic: Optional[str] = None
) -> str:
    """
    제목에서 캐노니컬 키 생성
    
    Args:
        title: 원본 제목
        location: 미리 추출된 지역명 (없으면 자동 추출)
        place: 미리 추출된 장소명 (없으면 자동 추출)
        topic: 미리 추출된 주제 (없으면 자동 추출)
        
    Returns:
        캐노니컬 키 문자열 (예: "경북경주|동국대학교경주병원장례식장|근조화환")
    """
    # 지역명 추출 (location_service 활용)
    if location is None:
        from shared.services.location_service import extract_locations, normalize_locations
        locs = normalize_locations(extract_locations(title))
        location = ''.join(sorted(locs)) if locs else ''
    
    # 장소명 추출 (병원, 장례식장 등 포함된 명사구)
    if place is None:
        nouns = extract_nouns(title)
        place_keywords = ['병원', '장례식장', '예식장', '센터', '회관', '호텔']
        place_parts = []
        for noun in nouns:
            if any(kw in noun for kw in place_keywords):
                place_parts.append(noun)
        place = ''.join(place_parts)
    
    # 주제 추출 (화환, 꽃, 배달 등)
    if topic is None:
        topic_keywords = ['화환', '꽃', '조화', '근조', '경조', '축하', '배달']
        nouns = extract_nouns(title)
        topic_parts = []
        for noun in nouns:
            if any(kw in noun for kw in topic_keywords):
                topic_parts.append(noun)
        # 대표 주제 하나만 선택 (첫 번째)
        topic = topic_parts[0] if topic_parts else ''
    
    # 정규화
    location = normalize_text(location)
    place = normalize_text(place)
    topic = normalize_text(topic)
    
    return f"{location}|{place}|{topic}"


def compare_canonical_keys(key1: str, key2: str) -> bool:
    """두 캐노니컬 키가 일치하는지 확인"""
    if not key1 or not key2:
        return False
    return key1 == key2
```

#### 2.3 개선된 유사도 서비스

**파일 수정**: `shared/services/similarity_service.py`

```python
"""
하이브리드 유사도 매칭 서비스

다단계 유사도 계산:
- Stage 0: 지역명 호환성 검사 (필터링)
- Stage 1: 캐노니컬 키 완전 일치 검사 (100%)
- Stage 2: 키워드 기반 유사도 (TF-IDF + 코사인)
- Stage 3: 시맨틱 유사도 (선택적, SBERT)
- Stage 4: 가중 합산 + 패널티 적용
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

# 내부 서비스 임포트
from shared.services.location_service import check_location_compatibility
from shared.services.canonical_key_service import generate_canonical_key, compare_canonical_keys

logger = logging.getLogger(__name__)

# 기본 임계값 (모듈 설정에서 오버라이드 가능)
DEFAULT_SIMILARITY_THRESHOLD = 75.0  # 75%로 통일!


@dataclass
class SimilarityResult:
    """유사도 계산 결과"""
    score: float                    # 최종 유사도 점수 (0-100)
    groupable: bool                 # 그룹핑 가능 여부
    reason: str                     # 판정 사유
    
    # 상세 점수
    base_score: Optional[float] = None
    keyword_score: Optional[float] = None
    semantic_score: Optional[float] = None
    location_penalty: float = 0.0
    
    # 추가 정보
    canonical_key_match: bool = False
    location_compatible: bool = True


def calculate_keyword_similarity(title1: str, title2: str) -> float:
    """
    키워드 기반 유사도 계산 (TF-IDF + 코사인 유사도)
    
    기존 로직 개선:
    - 형태소 분석으로 명사 추출
    - TF-IDF 가중치 적용
    - 코사인 유사도 계산
    """
    from kiwipiepy import Kiwi
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    kiwi = Kiwi()
    
    def tokenize(text: str) -> str:
        """형태소 분석 후 명사만 추출하여 공백으로 연결"""
        result = kiwi.analyze(text)
        nouns = []
        for token, pos, _, _ in result[0][0]:
            if pos.startswith('NN'):  # 명사류
                nouns.append(token)
        return ' '.join(nouns)
    
    # 토큰화
    tokens1 = tokenize(title1)
    tokens2 = tokenize(title2)
    
    if not tokens1 or not tokens2:
        return 0.0
    
    # TF-IDF 벡터화
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform([tokens1, tokens2])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return similarity * 100  # 퍼센트로 변환
    except Exception as e:
        logger.warning(f"TF-IDF 계산 실패: {e}")
        return 0.0


def calculate_semantic_similarity(title1: str, title2: str) -> float:
    """
    시맨틱 유사도 계산 (한국어 SBERT)
    
    선택적 기능: sentence-transformers 설치 필요
    설치 안 된 경우 키워드 유사도로 대체
    """
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 한국어 SBERT 모델 (최초 호출 시 다운로드)
        model = SentenceTransformer('jhgan/ko-sbert-sts')
        
        embeddings = model.encode([title1, title2])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return similarity * 100
        
    except ImportError:
        logger.info("sentence-transformers 미설치, 키워드 유사도로 대체")
        return calculate_keyword_similarity(title1, title2)
    except Exception as e:
        logger.warning(f"시맨틱 유사도 계산 실패: {e}")
        return calculate_keyword_similarity(title1, title2)


def calculate_similarity(
    title1: str,
    title2: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    use_semantic: bool = False
) -> SimilarityResult:
    """
    하이브리드 유사도 계산 (메인 함수)
    
    Args:
        title1: 첫 번째 제목
        title2: 두 번째 제목
        threshold: 그룹핑 임계값 (기본 75%)
        use_semantic: 시맨틱 유사도 사용 여부 (느림, 더 정확)
        
    Returns:
        SimilarityResult 객체
    """
    logger.debug(f"유사도 계산 시작: '{title1[:30]}...' vs '{title2[:30]}...'")
    
    # Stage 0: 지역명 호환성 검사
    location_check = check_location_compatibility(title1, title2)
    
    if not location_check["compatible"]:
        logger.debug(f"지역 불일치로 그룹핑 불가: {location_check['reason']}")
        return SimilarityResult(
            score=0.0,
            groupable=False,
            reason=location_check["reason"],
            location_compatible=False
        )
    
    # Stage 1: 캐노니컬 키 완전 일치 검사
    key1 = generate_canonical_key(title1)
    key2 = generate_canonical_key(title2)
    
    if compare_canonical_keys(key1, key2):
        logger.debug(f"캐노니컬 키 일치: {key1}")
        return SimilarityResult(
            score=100.0,
            groupable=True,
            reason="캐노니컬 키 완전 일치",
            canonical_key_match=True
        )
    
    # Stage 2: 키워드 기반 유사도
    keyword_sim = calculate_keyword_similarity(title1, title2)
    
    # Stage 3: 시맨틱 유사도 (선택적)
    if use_semantic:
        semantic_sim = calculate_semantic_similarity(title1, title2)
        # 가중 합산: 키워드 40% + 시맨틱 60%
        base_score = (keyword_sim * 0.4) + (semantic_sim * 0.6)
    else:
        semantic_sim = None
        base_score = keyword_sim
    
    # Stage 4: 지역 패널티 적용
    penalty = location_check["penalty"]
    final_score = base_score * (1 - penalty)
    
    # 그룹핑 가능 여부 판정
    groupable = final_score >= threshold
    
    result = SimilarityResult(
        score=round(final_score, 2),
        groupable=groupable,
        reason=f"하이브리드 유사도: {final_score:.1f}% (임계값: {threshold}%)",
        base_score=round(base_score, 2),
        keyword_score=round(keyword_sim, 2),
        semantic_score=round(semantic_sim, 2) if semantic_sim else None,
        location_penalty=penalty
    )
    
    logger.debug(f"유사도 계산 완료: {result}")
    return result


def find_similar_titles(
    new_title: str,
    existing_titles: List[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    use_semantic: bool = False
) -> List[Tuple[str, SimilarityResult]]:
    """
    새 제목과 유사한 기존 제목들 찾기
    
    Args:
        new_title: 새로 추가될 제목
        existing_titles: 기존 정식제목 리스트
        threshold: 그룹핑 임계값
        use_semantic: 시맨틱 유사도 사용 여부
        
    Returns:
        [(기존제목, SimilarityResult), ...] 유사도 높은 순 정렬
    """
    results = []
    
    for existing in existing_titles:
        result = calculate_similarity(
            new_title,
            existing,
            threshold=threshold,
            use_semantic=use_semantic
        )
        if result.score > 0:  # 점수가 0보다 큰 것만
            results.append((existing, result))
    
    # 유사도 높은 순 정렬
    results.sort(key=lambda x: x[1].score, reverse=True)
    
    return results
```

#### 2.4 flows_execute.py 수정

**파일 수정**: `services/republish/app/api/flows_execute.py`

약 735번째 줄 부근 수정:

```python
# 기존 코드 (문제)
transfer_result = await service.move_to_main(temp_ids, auto_group=auto_group)

# 수정 후
threshold = settings.get("similarity_threshold", 75)  # 651번째 줄에서 가져온 값
use_semantic = settings.get("use_semantic_similarity", False)

transfer_result = await service.move_to_main(
    temp_ids,
    auto_group=auto_group,
    similarity_threshold=threshold,
    use_semantic=use_semantic
)
```

---

## 📁 파일 구조

```
shared/
├── services/
│   ├── __init__.py
│   ├── location_service.py      # 새로 생성
│   ├── canonical_key_service.py # 새로 생성
│   └── similarity_service.py    # 대폭 수정

services/republish/app/
├── api/
│   └── flows_execute.py         # threshold 전달 버그 수정
```

---

## 📦 필요한 패키지

```txt
# requirements.txt에 추가
kiwipiepy>=0.14.0           # 한국어 형태소 분석
scikit-learn>=1.3.0         # TF-IDF, 코사인 유사도

# 선택적 (시맨틱 유사도 사용 시)
sentence-transformers>=2.2.0  # 한국어 SBERT
torch>=2.0.0                  # PyTorch (SBERT 의존)
```

---

## ✅ 테스트 체크리스트

### 단위 테스트

- [ ] `location_service.py`
  - [ ] 지역명 추출 테스트 (경북, 경상북도, 서울시 등)
  - [ ] 지역명 정규화 테스트
  - [ ] 4가지 케이스별 호환성 검사 테스트

- [ ] `canonical_key_service.py`
  - [ ] 캐노니컬 키 생성 테스트
  - [ ] 캐노니컬 키 비교 테스트

- [ ] `similarity_service.py`
  - [ ] 키워드 유사도 테스트
  - [ ] 하이브리드 유사도 테스트
  - [ ] 테스트 케이스 3개 제목 그룹핑 테스트

### 통합 테스트

- [ ] 임시제목 → 정식제목 이동 시 자동 그룹핑 테스트
- [ ] 데이터 모듈 임계값 설정이 실제로 적용되는지 테스트
- [ ] 지역명 다른 제목이 그룹핑되지 않는지 테스트

---

## 📋 작업 지시사항

### @explorer-agent 작업

1. `blogauto_new/` 레거시 코드에서 다음 분석:
   - 캐노니컬 키 생성 로직
   - 유사도 매칭 로직
   - 그룹핑 로직
   - 학습 데이터 시스템 (있다면)

### @backend-agent 작업

1. Phase 1 버그 수정
2. `location_service.py` 구현
3. `canonical_key_service.py` 구현
4. `similarity_service.py` 개선
5. `flows_execute.py` threshold 전달 수정

### @reviewer-agent 작업

1. 각 파일 500줄 미만 확인
2. 각 함수 50줄 미만 확인
3. 타입 힌트 확인
4. Docstring 확인
5. 테스트 케이스 3개 제목으로 실제 테스트

### @frontend-agent 작업 (Phase 3 이후)

1. 활성 그룹 / 일반 그룹 UI 구분
2. 대표 제목 배경색 표시
3. 그룹 클릭 시 팝업 기능

---

## ⚠️ 주의사항

1. **파일 크기 제한**: 모든 파일 500줄 미만, 함수 50줄 미만
2. **기존 코드 유지**: 레거시 `blogauto_new/` 절대 수정 금지
3. **점진적 배포**: Phase 1 완료 후 테스트, Phase 2 완료 후 테스트
4. **패키지 의존성**: 새 패키지 추가 시 requirements.txt 업데이트
5. **로깅**: 모든 주요 동작에 로깅 추가

---

## 🔗 참고 자료

- [ko-sentence-transformers](https://github.com/jhgan00/ko-sentence-transformers)
- [KoSentenceBERT-SKT](https://github.com/BM-K/KoSentenceBERT-SKT)
- [kiwipiepy](https://github.com/bab2min/kiwipiepy)
- CLAUDE.md, DEVELOPMENT_GUIDE.md 참조

---

**작성일**: 2025-01-22  
**버전**: v1.0.0
