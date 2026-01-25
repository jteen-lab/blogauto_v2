# 크롤링 포스트 매칭 시스템 설계 문서

> **버전**: v1.0.0
> **작성일**: 2025-01-25
> **상태**: 설계 검토 중

---

## 1. 개요

### 1.1 목적

블로그에 발행된 제목(크롤링 포스트)과 정식 제목(메인타이틀) 간의 유사도 매칭을 자동화하여, AI 글 생성 대상인 **독립포스트**를 식별하는 시스템을 구현합니다.

### 1.2 핵심 개념 정의

| 용어 | 정의 |
|------|------|
| **크롤링 포스트** | 블로그에서 크롤링한 실제 발행된 제목 데이터 |
| **메인타이틀** | 정식 제목으로 등록된 제목 (임시제목에서 이동) |
| **활성 그룹** | 유사한 메인타이틀들의 그룹 (대표 제목 존재) |
| **독립포스트** | 메인타이틀 중 크롤링 포스트와 매칭되지 않은 제목 → **AI 글 생성 대상** |
| **미매칭** | 크롤링 포스트 중 메인타이틀과 매칭되지 않은 제목 (기존 운영 블로그의 독자 발행 글) |

### 1.3 전체 워크플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                    생성 직전 자동화 파이프라인                      │
└─────────────────────────────────────────────────────────────────┘

1. Flow에 블로그 추가됨
   ↓
2. [자동] 블로그 크롤링 (최초 1회)
   → CrawledPost 데이터 생성
   ↓
3. [자동] 유사도 매칭
   → MainTitle ↔ CrawledPost 매칭
   ↓
4. [자동] 분류
   ├── 매칭 (score ≥ 94): CrawledPost와 MainTitle 연결
   ├── 대기 (70 ≤ score < 94): 검토 필요
   ├── 미매칭 (score < 70): 기존 운영 블로그의 독자 발행
   └── 독립포스트: MainTitle 중 매칭 안 된 것 → 생성 대상
   ↓
5. [자동] 생성 모듈 실행
   → 독립포스트 대상으로 AI 글 생성 → 발행
```

---

## 2. 시스템 아키텍처

### 2.1 권장 아키텍처: Flow 실행 시점 자동화

```
┌─────────────────────────────────────────────────────────────┐
│                     Flow 실행 파이프라인                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [Pre-Execution Stage]  ← 새로 추가되는 영역                │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  1. CrawlSyncService                                │   │
│   │     - 블로그별 최초/증분 크롤링 판단                  │   │
│   │     - CrawledPost 데이터 생성/업데이트               │   │
│   │                                                     │   │
│   │  2. HybridMatchingService                           │   │
│   │     - 유사도 매칭 실행                               │   │
│   │     - 매칭/대기/미매칭 분류                          │   │
│   │     - 독립포스트 식별                                │   │
│   └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│   [Module Execution Stage]  ← 기존 영역                     │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Module 1: generate (생성 모듈)                     │   │
│   │     - 독립포스트 기반 AI 글 생성                     │   │
│   │                                                     │   │
│   │  Module 2: republish (재발행 모듈)                  │   │
│   │     - 기존 로직 유지                                 │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 자동화 vs 수동 테스트 비교

| 기능 | 자동화 (Flow 실행 시) | 수동 (블로그 선택 시) |
|------|---------------------|---------------------|
| **크롤링** | 필요시 자동 실행 | 블로그 선택 → 없으면 자동 크롤링 |
| **매칭** | 자동 실행 | 블로그 선택 → 자동 매칭 |
| **결과 확인** | 로그에 기록 | 테이블 UI 실시간 표시 |
| **매칭 확정** | 자동 확정 (≥94점) | 대기 상태 수동 확정/거부 |
| **미매칭 처리** | - | [1:1 매칭] / [독립포스트 추가] |
| **독립포스트** | 전체 대상 | 선택 가능 |

---

## 3. 데이터 모델 설계

### 3.1 CrawledPost (신규)

```python
class CrawledPost(Base):
    """블로그에서 크롤링한 발행된 포스트"""
    __tablename__ = "crawled_posts"

    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False)

    # 포스트 정보
    title = Column(String(500), nullable=False)
    url = Column(String(1000), unique=True)
    published_at = Column(DateTime)  # 블로그에서의 실제 발행일

    # 매칭 정보
    match_status = Column(String(20), default="pending")
    # pending | matched | waiting | unmatched
    matched_main_title_id = Column(Integer, ForeignKey("main_titles.id"))
    matched_group_id = Column(Integer, ForeignKey("title_groups.id"))
    match_score = Column(Float)

    # 메타데이터
    crawled_at = Column(DateTime, default=func.now())
    last_matched_at = Column(DateTime)

    # 관계
    blog = relationship("Blog", back_populates="crawled_posts")
    matched_main_title = relationship("MainTitle")
    matched_group = relationship("TitleGroup")
```

### 3.2 Blog 모델 확장

```python
class Blog(Base):
    # 기존 필드...

    # 크롤링 상태 추가
    last_crawled_at = Column(DateTime)  # 마지막 크롤링 시간
    crawl_status = Column(String(20), default="never")
    # never | synced | outdated | error

    crawled_posts = relationship("CrawledPost", back_populates="blog")
```

### 3.3 매칭 상태 흐름

```
CrawledPost.match_status:

  pending ──┬── 자동매칭 ──┬── score ≥ 94 ──→ matched (자동확정)
            │              │
            │              ├── 70 ≤ score < 94 ──→ waiting (검토대기)
            │              │
            │              └── score < 70 ──→ unmatched (미매칭)
            │
            └── 수동조작 ──┬── 대기 확정 ──→ matched
                          │
                          ├── 대기 거부 ──→ unmatched
                          │
                          ├── 1:1 매칭 ──→ matched (독립포스트와 연결)
                          │
                          └── 독립포스트 생성 ──→ matched (새 MainTitle 생성)
```

---

## 4. 유사도 매칭 알고리즘

### 4.1 하이브리드 매칭 전략

v2 지역명 필터링 + v1 성능 최적화를 조합한 하이브리드 방식 채택

#### 핵심 최적화 포인트

1. **이미 매칭된 제목 제외**: `matched_main_title_id` 존재 시 매칭 비교 제외
2. **활성 그룹 대표 제목만 매칭**: 그룹 내 모든 제목 대신 대표 제목만 비교
3. **v2 지역명 필터링 (Stage 0)**: 지역 불일치 시 즉시 차단
4. **캐노니컬 키 기반 빠른 완전 일치**: 정규화된 키 비교로 100% 매칭

### 4.2 매칭 알고리즘 플로우

```
┌─────────────────────────────────────────────────────────────┐
│              HybridMatchingService.match_blog_titles()       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1: 크롤링 포스트 조회                                  │
│  ├─ CrawledPost 존재? → DB 조회                             │
│  └─ 없음? → 크롤링 실행 후 저장                              │
│                                                             │
│  Step 2: 매칭 대상 필터링                                    │
│  └─ matched_main_title_id가 NULL인 것만 선택                 │
│                                                             │
│  Step 3: 메인타이틀 조회 (최적화)                            │
│  ├─ 활성 그룹 → 대표 제목만 조회                             │
│  └─ 그룹 없는 제목 → 전체 조회                               │
│                                                             │
│  Step 4: 유사도 매칭 실행                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ for each crawled_post:                              │    │
│  │   for each main_title:                              │    │
│  │     ├─ Stage 0: 지역명 호환성 검사                   │    │
│  │     │   └─ 불일치 → continue (스킵)                 │    │
│  │     │                                               │    │
│  │     ├─ Stage 1: 캐노니컬 키 완전 일치               │    │
│  │     │   └─ 일치 → score = 100                      │    │
│  │     │                                               │    │
│  │     └─ Stage 2: 하이브리드 유사도 계산              │    │
│  │         └─ calculate_similarity_v3()                │    │
│  │         └─ 지역 패널티 적용                         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  Step 5: 결과 분류                                          │
│  ├─ score ≥ 94 → matched (자동 확정)                        │
│  ├─ 70 ≤ score < 94 → waiting (검토 대기)                   │
│  └─ score < 70 → unmatched (미매칭)                         │
│                                                             │
│  Step 6: 독립포스트 식별                                     │
│  └─ MainTitle 중 CrawledPost와 매칭되지 않은 것              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 지역명 필터링 (v2 신규 기능)

```python
def _check_location_compatibility(title1, title2) -> Dict:
    """
    지역명 호환성 검사 (4가지 케이스)

    Case 1: 둘 다 지역명 있음 + 일치 → compatible=True, penalty=0
    Case 2: 둘 다 지역명 있음 + 불일치 → compatible=False (그룹화 차단!)
    Case 3: 한쪽만 지역명 있음 → compatible=True, penalty=0.30
    Case 4: 둘 다 지역명 없음 → compatible=True, penalty=0
    """
```

**예시:**

| Case | Title1 | Title2 | Result | Reason |
|------|--------|--------|--------|--------|
| 1 | 경북 포항 화환 | 경북 포항시 화환 | ✅ 일치 | 지역 동일, penalty=0 |
| 2 | 경북 포항 화환 | 전남 광주 화환 | ❌ 불일치 | 지역 다름, **차단** |
| 3 | 경북 포항 화환 | 화환 판매처 | ⚠️ 불확실 | 한쪽만 지역, penalty=30% |
| 4 | 화환 판매처 | 꽃배달 서비스 | ✅ 가능 | 지역 없음, penalty=0 |

### 4.4 임계값 설정

```python
class HybridMatchingService:
    AUTO_CONFIRM_THRESHOLD = 94   # 자동 확정
    WAITING_THRESHOLD = 70        # 대기 (검토 필요)
    # < 70: 미매칭
```

---

## 5. 수동 조작 기능

### 5.1 대기 → 매칭 확정/거부

```python
async def confirm_waiting_match(
    self,
    crawled_post_id: int,
    main_title_id: int,
    confirmed: bool = True
) -> CrawledPost:
    """
    대기 상태의 매칭을 수동 확정/거부
    """
```

### 5.2 미매칭 → 독립포스트 1:1 매칭

```python
async def manual_match_to_independent(
    self,
    crawled_post_id: int,
    independent_title_id: int
) -> CrawledPost:
    """
    미매칭 크롤링 포스트를 독립포스트와 1:1 수동 매칭
    (활성 그룹 매칭과 유사한 방식)
    """
```

### 5.3 미매칭 → 새 독립포스트 생성

```python
async def create_independent_from_unmatched(
    self,
    crawled_post_id: int
) -> Tuple[MainTitle, CrawledPost]:
    """
    미매칭 제목을 새 독립포스트로 등록하고 100% 매칭

    사용 케이스: 미매칭 제목이 기존 독립포스트와 전혀 유사하지 않을 때
    → 동일한 제목의 MainTitle 생성 + 100% 매칭
    """
```

---

## 6. UI/UX 설계

### 6.1 정식 제목 관리 페이지 확장

```
┌──────────────────────────────────────────────────────────────────────┐
│  정식 제목 관리                                                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [블로그 선택] ▼ 내 블로그 1      [새로고침] [전체 재매칭]             │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ 📊 매칭 현황 (자동 갱신)                                        │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ • 크롤링 포스트: 120개       • 매칭 완료: 85개 (71%)            │  │
│  │ • 검토 대기: 15개            • 미매칭: 20개                     │  │
│  │ • 독립포스트 (생성 대상): 50개                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  [탭: 매칭됨 | 검토대기 | 미매칭 | 독립포스트 | 전체]                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 탭별 UI 구성

#### 검토대기 탭

```
┌────┬─────────────────┬─────────────────┬──────┬────────────────┐
│ #  │ 크롤링 제목      │ 매칭 후보        │ 점수 │ 액션           │
├────┼─────────────────┼─────────────────┼──────┼────────────────┤
│ 1  │ 부산 여행 후기   │ 부산 여행 코스   │ 78%  │ [확정] [거부]  │
│ 2  │ 서울 맛집 탐방   │ 서울 카페 투어   │ 72%  │ [확정] [거부]  │
└────┴─────────────────┴─────────────────┴──────┴────────────────┘
```

#### 미매칭 탭

```
┌────┬─────────────────┬──────────────────────────────────────────┐
│ #  │ 크롤링 제목      │ 액션                                     │
├────┼─────────────────┼──────────────────────────────────────────┤
│ 1  │ 기존 블로그 글1  │ [독립포스트 선택 ▼] [새 독립포스트 생성] │
│ 2  │ 기존 블로그 글2  │ [독립포스트 선택 ▼] [새 독립포스트 생성] │
└────┴─────────────────┴──────────────────────────────────────────┘
```

#### 독립포스트 탭

```
┌────┬─────────────────┬────────────┬────────────────────────────┐
│ ☑  │ 제목             │ 카테고리   │ 상태                       │
├────┼─────────────────┼────────────┼────────────────────────────┤
│ ☑  │ 강남 맛집 추천   │ 맛집      │ 🟢 생성 대상               │
│ ☑  │ 서울 카페 투어   │ 카페      │ 🟢 생성 대상               │
│ ☐  │ 부산 여행 코스   │ 여행      │ 🟡 매칭 연결됨             │
└────┴─────────────────┴────────────┴────────────────────────────┘

선택된 독립포스트: 2개                      [선택 항목으로 글 생성]
```

### 6.3 블로그 선택 시 자동 동작

```
┌───────────────────────────────────────────────────────────────────┐
│               정식 제목 관리 - 블로그 선택 시 동작                   │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│   [블로그 선택] ▼ 내 블로그 1                                      │
│          │                                                        │
│          ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────┐ │
│   │ Step 1: CrawledPost 존재 확인                               │ │
│   │   ├─ 있음 → DB에서 호출                                     │ │
│   │   └─ 없음 → 크롤링 실행 (자동)                              │ │
│   └─────────────────────────────────────────────────────────────┘ │
│          │                                                        │
│          ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────┐ │
│   │ Step 2: 유사도 매칭 (자동)                                  │ │
│   │   ├─ 이미 매칭된 제목 → 제외 (matched_id 있음)              │ │
│   │   ├─ 활성 그룹 → 대표 제목만 매칭                           │ │
│   │   └─ v2 지역명 필터링 + v1 최적화 조합                      │ │
│   └─────────────────────────────────────────────────────────────┘ │
│          │                                                        │
│          ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────┐ │
│   │ Step 3: 결과 테이블 UI 표시                                 │ │
│   │   ├─ 매칭 (≥94점): 자동 확정                                │ │
│   │   ├─ 대기 (70~93점): [수동 확정] 버튼                       │ │
│   │   ├─ 미매칭 (<70점): [1:1 매칭] 또는 [독립포스트 추가]      │ │
│   │   └─ 독립포스트: 생성 대상 표시                             │ │
│   └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 7. API 설계

### 7.1 엔드포인트 목록

```python
# 블로그 선택 시 자동 호출 (크롤링 + 매칭)
GET /api/v1/matching/blog/{blog_id}/status
# Response: 매칭 현황 + 각 카테고리별 카운트

# 대기 → 매칭 확정/거부
POST /api/v1/matching/confirm
# Body: { crawled_post_id, main_title_id, confirmed: bool }

# 미매칭 → 독립포스트 1:1 매칭
POST /api/v1/matching/manual-match
# Body: { crawled_post_id, independent_title_id }

# 미매칭 → 새 독립포스트 생성
POST /api/v1/matching/create-independent
# Body: { crawled_post_id }

# 독립포스트 목록 (선택 가능)
GET /api/v1/titles/independent?blog_id={blog_id}
# Response: 생성 대상 독립포스트 목록

# 전체 재매칭 (force)
POST /api/v1/matching/blog/{blog_id}/rematch
```

### 7.2 Response 스키마

```python
class MatchingStatusResponse(BaseModel):
    """블로그 매칭 현황"""
    blog_id: int
    blog_name: str

    # 카운트
    total_crawled: int
    matched_count: int
    waiting_count: int
    unmatched_count: int
    independent_count: int

    # 상세 데이터
    matched: List[MatchedPairResponse]
    waiting: List[MatchedPairResponse]
    unmatched: List[CrawledPostResponse]
    independent: List[MainTitleResponse]

    # 메타데이터
    last_crawled_at: Optional[datetime]
    last_matched_at: Optional[datetime]

class MatchedPairResponse(BaseModel):
    """매칭된 쌍 정보"""
    crawled_post: CrawledPostResponse
    main_title: MainTitleResponse
    score: float
    match_status: str  # matched | waiting
```

---

## 8. 파일 구조

```
services/republish/app/
├── models/
│   ├── crawled_post.py          # [신규] 크롤링 포스트 모델
│   └── blog.py                  # [수정] 크롤링 상태 필드 추가
│
├── schemas/
│   ├── crawled_post.py          # [신규] 크롤링 포스트 스키마
│   └── matching.py              # [신규] 매칭 결과 스키마
│
├── services/
│   ├── hybrid_matching_service.py  # [신규] 하이브리드 매칭
│   ├── crawl_service.py            # [신규] 블로그 크롤링
│   └── independent_post_service.py # [신규] 독립포스트 관리
│
├── routers/
│   └── matching.py              # [신규] 매칭 관련 API
│
└── templates/titles/
    └── matching_panel.html      # [신규] 매칭 패널 UI
```

---

## 9. 구현 순서

### Phase 1: 기반 구조

- [ ] CrawledPost 모델 생성
- [ ] Blog 모델 확장 (크롤링 상태 필드)
- [ ] 기본 스키마 정의 (CrawledPostSchema, MatchingSchema)
- [ ] DB 마이그레이션

### Phase 2: 핵심 서비스

- [ ] CrawlService 구현 (블로그 크롤링)
- [ ] HybridMatchingService 구현
  - [ ] 지역명 필터링 로직 (v2)
  - [ ] 대표 제목만 매칭 최적화 (v1)
  - [ ] 이미 매칭된 제목 제외 로직
- [ ] IndependentPostService 구현

### Phase 3: API & 수동 테스트

- [ ] 매칭 현황 조회 API
- [ ] 수동 확정/거부 API
- [ ] 1:1 매칭 API
- [ ] 독립포스트 생성 API
- [ ] 매칭 패널 UI 구현

### Phase 4: 자동화 통합

- [ ] PreExecutionService 구현
- [ ] Flow 실행 파이프라인 통합
- [ ] 생성 모듈과 연동
- [ ] 통합 테스트

---

## 10. 레거시 코드 참조

### 10.1 v1 유사도 매칭 (blogauto_new)

**파일**: `blogauto_new/core/similarity_utils.py`

**주요 함수**:
- `batch_similarity_match()`: 기본 배치 매칭
- `enhanced_batch_similarity_match()`: 학습 패턴 적용
- `two_stage_representative_matching()`: 캐싱 최적화 2단계 매칭
- `group_based_similarity_match()`: 그룹 ID 기반 매칭

### 10.2 v2 유사도 매칭 (현재)

**파일**: `shared/services/similarity_service.py`

**주요 메서드**:
- `calculate_similarity_v3()`: 다단계 하이브리드 (지역명 필터링 포함)
- `_check_location_compatibility()`: 지역명 호환성 검사

### 10.3 v1 vs v2 차이점

| 항목 | v1 (레거시) | v2 (현재) |
|------|-----------|-----------|
| 지역 불일치 | ⚠️ 매칭 가능 | ✅ **0점 차단** |
| 지역 부분 일치 | ⚠️ 패널티 없음 | ✅ 30% 감점 |
| 학습 모델 | ✅ MatchingLearning | ❌ 제거됨 |
| 캐노니컬 키 | 단순 정규화 | 3-요소 계층 |

---

## 11. 결정 필요 사항

### 11.1 크롤링 플랫폼

- [ ] 티스토리 API
- [ ] 네이버 블로그
- [ ] Blogger

→ **우선 지원 범위 결정 필요**

### 11.2 임계값 조정

- 자동 확정: 94점 (레거시 유지?)
- 대기: 70~93점 (적절?)

→ **테스트 후 조정 가능**

### 11.3 학습 데이터

- v1의 MatchingLearning 모델 도입 여부
- 수동 확정 시 학습 패턴 저장 여부

→ **추후 검토**

---

## 12. 참고 문서

- [v1 레거시 분석 보고서](./legacy_similarity_analysis.md) (필요시 생성)
- [정식 제목 관리 설계](./main_title_management.md) (필요시 생성)
- [Flow/Module 시스템 설계](./flow_module_system.md) (필요시 생성)

---

**문서 작성**: Claude Code
**최종 수정**: 2025-01-25
