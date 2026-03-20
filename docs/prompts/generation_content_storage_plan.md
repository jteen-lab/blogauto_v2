# 생성 콘텐츠 저장/조회/발행 작업 계획서

> **버전**: v1.1
> **작성일**: 2026-03-19
> **상태**: Phase 1~4 구현 완료

---

## 1. 배경 및 목적

### 현재 문제점
- ContentGenerator 파이프라인에서 생성된 HTML 본문이 **DB에 저장되지 않음**
- GenerationHistory에는 `content_length`(글자수)만 저장, 실제 콘텐츠 없음
- CrawledPost에는 `content` 필드 자체가 없음
- 이미지 저장 경로가 하드코딩 (`Path(__file__).parent.parent.parent / "static" / "generated" / "images"`)
- 프론트엔드에서 생성된 콘텐츠를 확인할 방법 없음

### 목표
1. 생성된 HTML을 DB에 저장하여 조회/미리보기 가능하게 함
2. 이미지 경로를 설정 기반으로 변경
3. 프론트엔드에서 생성 결과물 확인/복사/삭제 기능 제공
4. 발행 시 이미지 URL 치환 구조 설계 (구현은 발행 모듈 작업 시)

---

## 2. 핵심 설계 결정

### 저장 형식: HTML만 저장 (마크다운 제외)

**결정 근거:**

| 검토 항목 | 판단 |
|-----------|------|
| 사용자 편집 필요성 | 완전 자동화 → 편집 거의 없음 |
| 새 플랫폼 추가 시 | 프롬프트에서 새로 생성하는 것이 역변환보다 정확 |
| 발행 시 이미지 치환 | HTML `src` 속성 치환이 더 간단 |
| 디버깅 | HTML 자체로 확인 가능 |
| 미리보기 | 변환 없이 즉시 렌더링 |
| 파이프라인 호환 | 이미 HTML까지 생성하는 구조 |

**저장 흐름:**
```
AI 생성 (마크다운)
  → 내부링크 삽입 (마크다운 상태)
  → 텍스트 치환 (마크다운 상태)
  → HTML 변환 + CSS/태그 치환
  → content_html로 CrawledPost + GenerationHistory에 저장
```

---

## 3. Phase 1: DB 스키마 + 저장 파이프라인

### 3-1. DB 스키마 변경

**CrawledPost 모델 확장:**
```python
content_html = Column(Text, nullable=True, comment="생성된 HTML 본문")
```

**GenerationHistory 모델 확장:**
```python
content_html = Column(Text, nullable=True, comment="생성된 HTML 본문 (백업)")
```

**config.py 경로 설정:**
```python
IMAGE_STORAGE_DIR: str = "app/static/generated/images"
IMAGE_URL_PREFIX: str = "/static/generated/images"
```

**Alembic 마이그레이션:** `026_add_content_html_column.py`

### 3-2. ContentGenerator 파이프라인 수정

**수정 대상:**
- `generator.py`의 `_save_results()`: content_html을 CrawledPost + GenerationHistory에 저장
- `ai_image_service.py`: 하드코딩 경로 → config.IMAGE_STORAGE_DIR 참조

### 3-3. 대상 파일

| 파일 | 작업 | 에이전트 |
|------|------|---------|
| `app/models/crawled_post.py` | content_html 컬럼 추가 | @backend |
| `app/models/generation_history.py` | content_html 컬럼 추가 | @backend |
| `app/core/config.py` | IMAGE_STORAGE_DIR, IMAGE_URL_PREFIX 추가 | @backend |
| `alembic/versions/026_add_content_html_column.py` | 마이그레이션 | @backend |
| `app/services/generation/generator.py` | _save_results에 content_html 저장 | @backend |
| `app/services/generation/ai_image_service.py` | 경로 config 참조 | @backend |

---

## 4. Phase 2: 콘텐츠 조회 API

### 4-1. API 엔드포인트

```
GET    /api/generation/content/{crawled_post_id}
       → content_html, image_url, 메타정보 반환

GET    /api/generation/content/{crawled_post_id}/html
       → HTML 문자열만 반환 (클립보드 복사용)

DELETE /api/generation/content/{crawled_post_id}
       → 콘텐츠 삭제 (CrawledPost + 이미지 파일)
```

### 4-2. 대상 파일

| 파일 | 작업 | 에이전트 |
|------|------|---------|
| `app/routers/generation_content.py` | 신규 API 라우터 | @backend |

---

## 5. Phase 3: 프론트엔드 UI

### 5-1. 생성 이력 페이지 개선

**기존 `generation/history.html` 수정:**

```
┌──────────────────────────────────────────────────────────┐
│ 생성 이력                                                │
├──────┬────────┬──────┬────────┬──────┬──────────────────┤
│ 제목  │ 블로그  │ 이미지│ 생성일  │ 상태 │ 액션            │
├──────┼────────┼──────┼────────┼──────┼──────────────────┤
│ 제목1 │ Blog A │  🖼️  │ 03-19  │ 생성 │ [보기][복사][삭제]│
│ 제목2 │ Blog B │  📝  │ 03-18  │ 발행 │ [보기]           │
└──────┴────────┴──────┴────────┴──────┴──────────────────┘

🖼️ = 이미지 있음 (hover 시 미리보기 툴팁)
📝 = 텍스트만
```

**콘텐츠 보기 모달:**

```
┌─────────────────────────────────────────┐
│ 📄 생성된 콘텐츠                    [X] │
├─────────────────────────────────────────┤
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ │   HTML 렌더링 미리보기 영역         │ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│         [HTML 복사]     [닫기]          │
└─────────────────────────────────────────┘
```

### 5-2. 대상 파일

| 파일 | 작업 | 에이전트 |
|------|------|---------|
| `app/templates/generation/history.html` | 이모지 표시, 액션 버튼, 모달 | @frontend |
| `app/static/js/generation-history.js` | 모달 로직, API 호출, 복사 기능 | @frontend |

---

## 6. Phase 4: 발행 시 이미지 업로드 (설계만)

> 이 Phase는 **설계 문서만** 작성하며, 실제 구현은 발행 모듈 작업 시 진행

### 6-1. 발행 흐름 설계

```
발행 요청
  → 이미지 존재 확인
  → 플랫폼별 이미지 업로드
     - WordPress: POST /wp-json/wp/v2/media → 원격 URL 획득
     - Blogger: 외부 스토리지 업로드 → URL 획득
  → HTML 내 이미지 src 로컬 경로 → 원격 URL 치환
  → 포스트 발행 API 호출
```

### 6-2. WordPress 이미지 업로드 (미구현)

```python
# wordpress_api.py에 추가 예정
async def upload_media(self, image_path: str) -> str:
    """로컬 이미지를 WordPress에 업로드하고 URL 반환"""
    # POST /wp-json/wp/v2/media
    # Content-Type: multipart/form-data
    # → response.source_url 반환
```

### 6-3. Blogger 이미지 (미구현)

- Blogger API는 이미지 업로드 미지원
- 대안 검토 필요: Google Drive 공유 링크, 외부 이미지 호스팅 등

---

## 7. 에이전트별 작업 분배

```
┌─────────────┬────────────────────────────────────────────┐
│ 에이전트     │ 담당 작업                                  │
├─────────────┼────────────────────────────────────────────┤
│ @backend    │ Phase 1: DB 스키마, 마이그레이션, 저장 로직  │
│             │ Phase 2: 조회/삭제 API                      │
├─────────────┼────────────────────────────────────────────┤
│ @frontend   │ Phase 3: 이력 페이지 UI, 모달, 복사 기능    │
├─────────────┼────────────────────────────────────────────┤
│ @reviewer   │ 전체 Phase 코드 리뷰 + 테스트               │
└─────────────┴────────────────────────────────────────────┘
```

---

## 8. 작업 우선순위

| Phase | 내용 | 우선순위 | 의존성 |
|-------|------|---------|--------|
| 1 | DB 스키마 + 저장 파이프라인 | 🔴 즉시 | 없음 |
| 2 | 콘텐츠 조회 API | 🔴 즉시 | Phase 1 |
| 3 | 프론트엔드 UI | 🔴 즉시 | Phase 2 |
| 4 | 발행 이미지 업로드 (설계) | 🟡 별도 | Phase 1~3 완료 후 |

**Phase 1→2는 순차, Phase 2→3은 API 완료 후 병렬 가능**
