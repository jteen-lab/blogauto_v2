# 정식 제목 관리 기능 개발 계획

> **버전**: v1.0.0  
> **작성일**: 2025-01-20  
> **목적**: 임시 제목 → 정식 제목 이동 및 유사도 매칭 시스템 구현

---

## 📋 개요

### 목표
- 임시 제목에서 정식 제목으로 자동/수동 이동 기능 구현
- 지역명 인식 기반의 향상된 유사도 매칭 시스템 구축
- 정식 제목 관리 UI 추가

### 핵심 원칙
- 지역명이 다르면 절대 그룹화하지 않음
- 유사도 매칭은 공통 서비스로 구현 (여러 기능에서 재사용)
- 자동/수동 조작 모두 지원

---

## 🔧 Phase 구성

| Phase | 내용 | 예상 기간 | 의존성 |
|-------|------|----------|--------|
| A | 지역명 DB 및 추출 서비스 | 2-3일 | 없음 |
| B | 유사도 매칭 서비스 V2 | 2-3일 | Phase A |
| C | 정식 제목 모델 및 API | 2-3일 | Phase B |
| D | 제목 이동 모듈 | 2-3일 | Phase C |
| E | 정식 제목 UI | 2-3일 | Phase D |
| F | 테스트 및 튜닝 | 2-3일 | Phase E |

---

## 📁 파일 구조 (예상)
```
blogauto_v2/
├── shared/
│   ├── data/
│   │   └── korean_locations.json      # Phase A: 지역명 DB
│   └── services/
│       ├── location_service.py        # Phase A: 지역명 추출
│       └── similarity_service.py      # Phase B: 유사도 매칭 V2
│
├── services/republish/app/
│   ├── models/
│   │   └── title.py                   # Phase C: Title, TitleGroup 모델
│   ├── schemas/
│   │   └── title.py                   # Phase C: Title 스키마
│   ├── api/
│   │   └── titles.py                  # Phase C: Title API
│   ├── services/
│   │   └── title_transfer_service.py  # Phase D: 제목 이동 서비스
│   └── templates/
│       └── data_management/
│           └── titles_main.html       # Phase E: 정식 제목 UI
```

---

## Phase A: 지역명 DB 및 추출 서비스

### 목표
- 한국 행정구역 데이터베이스 구축
- 제목에서 지역명 추출하는 서비스 구현

### 세부 작업
1. 한국 행정구역 JSON 데이터 생성
   - 시/도 (17개)
   - 시/군/구 (약 250개)
   - 읍/면/동 (주요 지역)
   - 약칭 매핑 (경북↔경상북도)

2. location_service.py 구현
   - `extract_location(title)` - 제목에서 지역명 추출
   - `normalize_location(location)` - 지역명 정규화
   - `is_same_location(loc1, loc2)` - 지역 동일성 비교

### 참조
- 레거시: 없음 (신규 기능)

---

## Phase B: 유사도 매칭 서비스 V2

### 목표
- 지역명 우선 처리하는 향상된 유사도 매칭 구현
- 기존 로직 기반으로 개선

### 세부 작업
1. similarity_service.py 구현
   - `calculate_similarity_v2(title1, title2)` - 향상된 유사도 계산
   - `batch_similarity_match_v2(titles)` - 배치 매칭
   - `find_similar_group(title, existing_groups)` - 그룹 찾기

2. 매칭 로직
```
   1단계: 지역명 추출
   2단계: 지역명 비교 (다르면 0점 반환)
   3단계: 지역명 제외 후 텍스트 유사도 계산
   4단계: 주제 키워드 보너스 점수
```

### 참조
- 레거시: `blogauto_new/core/similarity_utils.py`
  - `calculate_title_similarity()` (1258줄)
  - `normalize_for_similarity()` (98줄)

---

## Phase C: 정식 제목 모델 및 API

### 목표
- Title, TitleGroup 모델 구현
- CRUD API 구현

### 세부 작업
1. 모델 구현
```python
   Title:
   - id, title, category_id
   - group_id, is_representative
   - group_similarity_score, grouped_at
   - location_info, keywords
   - status, source
   
   TitleGroup:
   - id, category_id
   - representative_title_id
   - location, main_keyword
   - title_count
```

2. API 엔드포인트
   - `GET /api/v1/titles` - 목록 조회
   - `GET /api/v1/titles/{id}` - 상세 조회
   - `POST /api/v1/titles` - 생성
   - `PUT /api/v1/titles/{id}` - 수정
   - `DELETE /api/v1/titles/{id}` - 삭제
   - `GET /api/v1/title-groups` - 그룹 목록
   - `PUT /api/v1/title-groups/{id}/representative` - 대표 변경

### 참조
- 레거시: `blogauto_new/core/models.py`
  - `Title` (445줄)
  - `TempTitle` (432줄)

---

## Phase D: 제목 이동 모듈

### 목표
- 임시→정식, 정식→임시 이동 기능 구현
- 자동/수동 이동 지원

### 세부 작업
1. title_transfer_service.py 구현
   - `move_to_main(temp_title_ids, user)` - 임시→정식
   - `move_to_temp(title_ids, user)` - 정식→임시
   - `auto_transfer_categorized()` - 자동 이동 (카테고리 있는 것만)

2. 이동 로직
```
   1. 중복 제거 (100% 동일)
   2. 지역명 추출
   3. 같은 카테고리+같은 지역 내에서 유사도 매칭
   4. 임계값 이상 → 기존 그룹에 추가
   5. 미만 → 새 대표 제목 생성
```

3. API 엔드포인트
   - `POST /api/v1/titles/transfer/to-main` - 임시→정식
   - `POST /api/v1/titles/transfer/to-temp` - 정식→임시
   - `POST /api/v1/titles/transfer/auto` - 자동 이동

### 참조
- 레거시: `blogauto_new/core/services/titles_temp.py`
  - `move_to_main_titles()` (49줄)
- 레거시: `blogauto_new/core/services/titles_main.py`
  - `move_to_temp_titles_view()` (55줄)

---

## Phase E: 정식 제목 UI

### 목표
- 데이터 관리 페이지에 "정식 제목" 탭 추가
- 그룹별/카테고리별 보기 지원

### 세부 작업
1. 탭 구조
```
   데이터 관리
   ├── 임시 제목 (기존)
   ├── 정식 제목 (신규) ← 추가
   └── 필터 설정 (기존)
```

2. 정식 제목 화면 기능
   - 전체 목록 보기
   - 그룹별 보기 (접기/펼치기)
   - 카테고리별 필터
   - 제목 선택 → 임시로 이동/수정/삭제
   - 그룹 대표 변경
   - 수동 그룹 지정/해제

### 참조
- 기존 UI: `app/templates/data_management/` 구조 참조

---

## Phase F: 테스트 및 튜닝

### 목표
- 전체 기능 테스트
- 유사도 임계값 튜닝
- 성능 최적화

### 세부 작업
1. 단위 테스트
   - 지역명 추출 테스트
   - 유사도 매칭 테스트
   - 제목 이동 테스트

2. 통합 테스트
   - 전체 워크플로우 테스트
   - UI 기능 테스트

3. 튜닝
   - 유사도 임계값 조정 (기본 80%)
   - 지역명 DB 보완
   - 성능 측정 및 최적화

---

## 🔄 레거시 참조 파일 요약

| 파일 | 참조 내용 |
|------|----------|
| `similarity_utils.py` | 유사도 계산, 정규화 로직 |
| `models.py` | Title, TempTitle 모델 구조 |
| `titles_temp.py` | 임시→정식 이동 로직 |
| `titles_main.py` | 정식→임시 이동, 매칭 로직 |
| `title_group_service.py` | 그룹 관리 로직 |

---

## ⚠️ 주의사항

1. 파일 크기 < 500줄 유지
2. 함수 크기 < 50줄 유지
3. 레거시 코드 복사 금지, 참조만
4. 타입 힌트, Docstring 필수
5. 에러 처리 필수

---

**다음 단계**: Phase A 프롬프트 실행
