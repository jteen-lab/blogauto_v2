# 플로우 UI 리팩토링 작업 계획서

> **버전**: v1.0
> **작성일**: 2026-03-23
> **목적**: 플로우 관리 UI에서 레거시 publish/republish 잔존 코드 정리, 탭 구조 개선, 카드 렌더링 개선, 모듈/블로그별 개별 실행 버튼 추가

---

## 1. 개요

### 1.1 현재 문제점

```
플로우 폼 (_form.html):
├── 7개 모듈 탭: 프롬프트, 생성, 발행, 재발행, 수집, 데이터, 성장프로파일
│   └── ❌ 발행/재발행 탭이 여전히 존재 (모듈 타입은 이미 삭제됨 → 빈 탭)
│   └── ❌ 프롬프트/생성이 별도 탭으로 분리 (실질적으로 연관 모듈)
├── 모듈 선택: 간소화된 체크박스 리스트 (관리 페이지 카드와 다른 형태)
├── 블로그 선택: 플랫폼별 탭 + 체크박스 리스트 (관리 페이지 카드와 다른 형태)
└── 실행 버튼: 플로우 카드 헤더에 "1회 실행" (플로우 전체 실행만 가능)

플로우 목록 (list.js):
└── ❌ publish/republish 아이콘/라벨/색상 맵이 7곳+ 잔존
```

### 1.2 목표 구조

```
플로우 폼 (_form.html):
├── 5개 모듈 탭: 프롬프트/생성, 수집, 데이터, 성장프로파일
│   └── ✅ 발행/재발행 탭 제거
│   └── ✅ 프롬프트/생성 탭 통합
│   └── ✅ 탭 제목에 선택 수 표시 "프롬프트/생성 (2)"
├── 모듈 선택: 카드 기반 렌더링 (행당 최대 4개, 체크박스 선택)
├── 블로그 선택: 카드 기반 렌더링 (행당 최대 4개, 체크박스 선택)
└── 실행: 모듈 카드/블로그 카드 내 개별 실행 버튼

플로우 카드 (_card.html):
└── ✅ 플로우 레벨 "1회 실행" 버튼 제거

플로우 목록 (list.js):
└── ✅ publish/republish 레거시 코드 정리
```

### 1.3 핵심 원칙

| 원칙 | 설명 |
|------|------|
| 기존 기능 보존 | 프롬프트 모듈의 블로그-카테고리 자동 연동(syncPromptModuleBlogs) 유지 |
| 점진적 개선 | 4개 Phase로 나누어 각 Phase가 독립적으로 동작하도록 구현 |
| 일관된 UI | 모듈/블로그 관리 페이지의 카드 디자인과 스타일 통일 |
| 백엔드 최소 변경 | Phase 1-2는 프론트엔드만 변경, Phase 3-4에서 백엔드 API 추가 |

### 1.4 폐지 항목

| 항목 | 사유 |
|------|------|
| 프롬프트/생성 모듈 블로그 연동을 플로우 레벨로 이전 | 양방향 연동 + 강제 연동 + 전체 토픽 분해 등 ~1,000줄 JS 로직 복제 필요, 모듈 간 카테고리 독점 관리는 모듈 레벨에서만 가능 |

---

## 2. 변경 범위 분석

### 2.1 수정 대상 파일

| 구분 | 파일 | 현재 줄 수 | 변경 내용 | Phase |
|------|------|-----------|----------|-------|
| **HTML** | `app/templates/flows/_form.html` | 396줄 | 탭 구조 변경, 카드 렌더링 | 1, 2 |
| **HTML** | `app/templates/flows/_card.html` | 210줄 | 플로우 레벨 실행 버튼 제거 | 4 |
| **HTML** | `app/templates/flows/list.html` | 474줄 | 레거시 코드 정리 | 1 |
| **JS** | `app/static/js/flows/form.js` | 761줄 | 탭 로직 변경, 카드 렌더링 JS | 1, 2 |
| **JS** | `app/static/js/flows/list.js` | 1631줄 | publish/republish 레거시 정리 | 1 |
| **Python** | `app/routers/flows_execute.py` | 1162줄 | 모듈별 개별 실행 API 추가 | 3 |
| **Python** | `app/routers/flows.py` | - | 블로그별 발행/재발행 API 추가 | 4 |

### 2.2 신규 생성 파일

| 파일 | 설명 | Phase |
|------|------|-------|
| `app/templates/flows/_module_select_card.html` | 플로우 폼 내 모듈 선택용 미니 카드 | 2 |
| `app/templates/flows/_blog_select_card.html` | 플로우 폼 내 블로그 선택용 미니 카드 | 2 |

---

## 3. Phase 별 상세 계획

### Phase 1: 탭 구조 정리 + 레거시 코드 제거 (프론트엔드만)

**목표**: publish/republish 잔존 코드 완전 제거, prompt/generate 탭 통합, 선택 수 표시

#### 3.1.1 _form.html 탭 구조 변경

**변경 전** (7개 탭):
```
프롬프트 | 생성 | 발행 | 재발행 | 수집 | 데이터 | 성장 프로파일
```

**변경 후** (4개 탭):
```
프롬프트/생성 (N) | 수집 (N) | 데이터 (N) | 성장 프로파일 (N)
```

| 작업 | 파일 | 줄 번호 | 내용 |
|------|------|---------|------|
| 발행 탭 제거 | `_form.html` | 78-83 | `publish` 탭 버튼 삭제 |
| 재발행 탭 제거 | `_form.html` | 84-89 | `republish` 탭 버튼 삭제 |
| 프롬프트+생성 탭 통합 | `_form.html` | 67-77 | 2개 탭을 1개로 합침, 아이콘: 📝✨ |
| 선택 수 표시 | `_form.html` | 67-107 | 각 탭에 `(N)` 카운트 뱃지 추가 |

**탭 제목 선택 수 표시 예시**:
```html
<button @click="activeModuleTab = 'prompt_generate'">
    📝✨ 프롬프트/생성
    <span x-show="getModuleCountByTypes(['prompt','generate']) > 0"
          class="ml-1 px-1.5 py-0.5 text-xs bg-blue-500 text-white rounded-full"
          x-text="getModuleCountByTypes(['prompt','generate'])">
    </span>
</button>
```

#### 3.1.2 form.js 수정

| 작업 | 줄 번호 | 내용 |
|------|---------|------|
| activeModuleTab 기본값 변경 | 114 | `'republish'` → `'prompt_generate'` |
| resetForm() 기본값 변경 | 159 | `'prompt'` → `'prompt_generate'` |
| getModulesByType() 수정 | - | `'prompt_generate'` 탭 클릭 시 `['prompt', 'generate']` 두 타입 반환 |
| getModuleCountByTypes() 추가 | - | 여러 타입의 선택된 모듈 수 합산 함수 |

**getModulesByType 변경**:
```javascript
// 변경 전
getModulesByType(typeCode) {
    return this.modules.filter(m => m.module_type?.code === typeCode);
}

// 변경 후
getModulesByType(typeCode) {
    if (typeCode === 'prompt_generate') {
        return this.modules.filter(m =>
            ['prompt', 'generate'].includes(m.module_type?.code)
        );
    }
    return this.modules.filter(m => m.module_type?.code === typeCode);
}
```

#### 3.1.3 list.js 레거시 코드 정리

| 작업 | 대상 코드 | 내용 |
|------|----------|------|
| 아이콘 맵 정리 | `publish: '📤'` 등 | publish/republish 키 제거 |
| 라벨 맵 정리 | `publish: '발행'` 등 | publish/republish 키 제거 |
| 색상 맵 정리 | `publish: 'bg-rose-200'` 등 | publish/republish 키 제거 |
| 모듈 정보 표시 정리 | `else if (typeCode === 'publish')` 블록 | publish/republish 분기 제거 |
| GP 단계 표시 정리 | `firstStage.publish?.enabled` 등 | 표시 로직은 유지 (GP 모듈 정보 표시용) |

#### 3.1.4 검증 항목

- [ ] 플로우 폼에서 4개 탭만 표시되는지 확인
- [ ] 프롬프트/생성 탭에서 두 타입 모듈 모두 표시되는지 확인
- [ ] 각 탭에 선택된 모듈 수가 정확히 표시되는지 확인
- [ ] 기존 플로우 수정 시 모듈 선택 상태가 올바르게 복원되는지 확인
- [ ] syncPromptModuleBlogs() 기능이 정상 동작하는지 확인
- [ ] list.js에서 기존 플로우 카드가 오류 없이 렌더링되는지 확인

---

### Phase 2: 카드 기반 렌더링 개선 (프론트엔드만)

**목표**: 모듈/블로그 선택 UI를 관리 페이지와 일관된 카드 스타일로 변경

#### 3.2.1 모듈 선택 카드 (`_module_select_card.html`)

**현재**: 간소화된 체크박스 리스트 (rounded-xl 카드지만 정보량 적음)
**변경 후**: 관리 페이지 카드 스타일 + 체크박스 + 슬라이드 정보

```
┌─────────────────────────────────┐
│ ☑ [타입아이콘] 모듈명           │ ← 헤더 (타입별 배경색)
├─────────────────────────────────┤
│ 설명 텍스트                     │
│ ┌ 블로그: Blog A · Blog B ──→ │ ← 블로그 슬라이드 (있을 경우)
│ └ 정보: 라벨: 값 ───────────→ │ ← 모듈 정보 슬라이드
└─────────────────────────────────┘
```

| 작업 | 내용 |
|------|------|
| 미니 카드 템플릿 생성 | `_module_select_card.html` - 체크박스 + 타입별 헤더색 + 정보 슬라이드 |
| 그리드 레이아웃 | xl: 4열, md: 2열, sm: 1열 (기존 모듈 관리 페이지 패턴 재사용) |
| 선택 상태 스타일 | 선택 시 `ring-2 ring-blue-500 border-blue-300` |
| 타입별 정보 표시 | prompt: 카테고리, 블로그 / generate: AI모델 / collect: 수집 타입 / data: 이동 대상 |

**그리드 레이아웃**:
```html
<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
    <template x-for="module in getModulesByType(activeModuleTab)">
        {% include 'flows/_module_select_card.html' %}
    </template>
</div>
```

#### 3.2.2 블로그 선택 카드 (`_blog_select_card.html`)

**현재**: 플랫폼별 탭 + 체크박스 리스트
**변경 후**: 관리 페이지 블로그 카드 스타일 + 체크박스 + 4열 그리드

```
┌─────────────────────────────────┐
│ ☑ [WP] 블로그명                 │ ← 헤더 (플랫폼별 배경색)
├─────────────────────────────────┤
│ https://blog-url.com            │
│ 🏷 프롬프트 연동 (자동 선택됨)  │ ← 프롬프트 연동 블로그인 경우
└─────────────────────────────────┘
```

| 작업 | 내용 |
|------|------|
| 미니 카드 템플릿 생성 | `_blog_select_card.html` - 체크박스 + 플랫폼 아이콘 + URL |
| 그리드 레이아웃 | xl: 4열, md: 2열, sm: 1열 |
| 프롬프트 연동 표시 | `isPromptLinkedBlog(blog.id)` 시 배지 표시 + 체크박스 비활성화 (기존 로직 유지) |
| 플랫폼별 탭 제거 | WordPress/Blogger 구분 없이 한 그리드에 표시, 플랫폼은 아이콘으로 구분 |

#### 3.2.3 _form.html 수정

| 작업 | 현재 줄 | 내용 |
|------|---------|------|
| 모듈 선택 영역 교체 | 120-185 | 기존 체크박스 리스트 → 카드 그리드 + include |
| 블로그 선택 영역 교체 | 218-299 | 플랫폼별 탭 + 리스트 → 카드 그리드 + include |
| max-h-80 조정 | 119 | 카드 4열일 경우 높이 제한 재조정 (max-h-96 또는 제거) |

#### 3.2.4 form.js 수정

| 작업 | 내용 |
|------|------|
| 모듈 카드 정보 함수 | `getModuleCardInfo(module)` - 타입별 표시 정보 반환 |
| 블로그 카드 정보 함수 | `getBlogCardInfo(blog)` - 플랫폼 아이콘/색상 반환 |

#### 3.2.5 CSS 재활용

| 기존 CSS | 재활용 내용 |
|----------|-----------|
| `flow-card-slide.css` | 모듈 정보 슬라이드 애니메이션 |
| `components.css` | 카드 기본 스타일, hover 효과 |
| Tailwind 유틸리티 | 그리드, 색상, 반응형 |

#### 3.2.6 검증 항목

- [ ] 모듈 카드가 4열 그리드로 표시되는지 확인
- [ ] 블로그 카드가 4열 그리드로 표시되는지 확인
- [ ] 모듈 선택/해제가 정상 동작하는지 확인
- [ ] 블로그 선택/해제가 정상 동작하는지 확인
- [ ] 프롬프트 연동 블로그 비활성화가 유지되는지 확인
- [ ] 반응형 레이아웃 (모바일 1열, 태블릿 2열, 데스크탑 4열) 확인
- [ ] 슬라이드 애니메이션이 카드 내에서 정상 동작하는지 확인

---

### Phase 3: 모듈별 개별 실행 API + UI (프론트엔드 + 백엔드)

**목표**: 플로우 내 각 모듈을 개별적으로 실행할 수 있는 API와 버튼 추가

#### 3.3.1 백엔드 API 추가

**새 엔드포인트**: `POST /api/v1/flows/{flow_id}/modules/{module_id}/execute`

```python
@router.post("/{flow_id}/modules/{module_id}/execute")
async def execute_single_module(
    flow_id: int,
    module_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    플로우 내 특정 모듈을 개별 실행합니다.

    - prompt/generate: 1회 생성 (블로그별)
    - collect: 1회 수집
    - data: 1회 이동
    - growth_profile: 실행 불가 (400 반환)
    """
```

**실행 로직 (모듈 타입별)**:

| 모듈 타입 | 실행 내용 | 블로그 필요 | GP 필요 |
|----------|----------|-----------|---------|
| prompt | FlowGenerateExecutor로 각 블로그별 1회 생성 | ✅ Flow.blog_links | ✅ StageParams |
| generate | FlowGenerateExecutor로 각 블로그별 1회 생성 | ✅ Flow.blog_links | ✅ StageParams |
| collect | _execute_collect_module() 1회 실행 | ❌ | ❌ |
| data | _execute_data_module() 1회 실행 | ❌ | ❌ |
| growth_profile | 400 Bad Request ("GP는 개별 실행 불가") | - | - |

**응답 형식**:
```json
{
    "status": "completed",
    "module_type": "collect",
    "module_name": "키워드 수집",
    "results": [
        {"blog_name": "-", "status": "success", "detail": "3건 수집"}
    ],
    "duration_ms": 1500
}
```

#### 3.3.2 flows_execute.py 리팩토링

현재 `_execute_flow_background()`에서 모듈 타입별 실행 블록이 하나의 함수에 통합되어 있음 (1162줄).
개별 실행을 위해 모듈 타입별 실행 로직을 분리합니다.

| 함수 | 추출 원본 | 역할 |
|------|----------|------|
| `_execute_collect_single(module, db)` | 기존 collect 블록 | collect 모듈 단독 실행 |
| `_execute_data_single(module, db)` | 기존 data 블록 | data 모듈 단독 실행 |
| `_execute_prompt_single(module, flow, blogs, gp_context, db)` | 기존 prompt 블록 | prompt 모듈 단독 실행 |

#### 3.3.3 프론트엔드 - 모듈 카드 실행 버튼

Phase 2에서 생성한 `_module_select_card.html`에 실행 버튼을 추가합니다.

| 모듈 타입 | 버튼 텍스트 | 아이콘 | 색상 |
|----------|-----------|--------|------|
| prompt | 1회 생성 | ▶️ | green |
| generate | 1회 생성 | ▶️ | green |
| collect | 1회 수집 | ▶️ | purple |
| data | 1회 이동 | ▶️ | teal |
| growth_profile | (버튼 없음) | - | - |

**버튼 동작**:
```javascript
async executeModule(flowId, moduleId) {
    const resp = await fetch(
        `/api/v1/flows/${flowId}/modules/${moduleId}/execute`,
        { method: 'POST', credentials: 'include' }
    );
    const result = await resp.json();
    // 결과 토스트 메시지 표시
}
```

**조건**: 플로우가 저장된 상태에서만 실행 가능 (신규 생성 중에는 비활성화)

#### 3.3.4 검증 항목

- [ ] collect 모듈 개별 실행이 정상 동작하는지 확인
- [ ] data 모듈 개별 실행이 정상 동작하는지 확인
- [ ] prompt 모듈 개별 실행 시 Flow.blog_links의 블로그별로 실행되는지 확인
- [ ] growth_profile 실행 시 400 에러가 반환되는지 확인
- [ ] 실행 중 버튼 비활성화 + 스피너 표시되는지 확인
- [ ] 실행 결과 토스트 메시지가 정상 표시되는지 확인

---

### Phase 4: 블로그별 발행/재발행 버튼 + 플로우 실행 버튼 이전 (프론트엔드 + 백엔드)

**목표**: 블로그 카드에 발행/재발행 개별 실행 버튼 추가, 플로우 카드의 실행 버튼 제거

#### 3.4.1 백엔드 API 추가

**새 엔드포인트 1**: `POST /api/v1/flows/{flow_id}/blogs/{blog_id}/publish`

```python
@router.post("/{flow_id}/blogs/{blog_id}/publish")
async def publish_single_blog(
    flow_id: int,
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    플로우 내 특정 블로그에 대해 1회 발행을 실행합니다.
    GP의 stage_params.publish 설정을 사용합니다.
    """
```

**새 엔드포인트 2**: `POST /api/v1/flows/{flow_id}/blogs/{blog_id}/republish`

```python
@router.post("/{flow_id}/blogs/{blog_id}/republish")
async def republish_single_blog(
    flow_id: int,
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    플로우 내 특정 블로그에 대해 1회 재발행을 실행합니다.
    GP의 stage_params.republish 설정을 사용합니다.
    """
```

**실행 전제조건**:
- 플로우에 GP 모듈이 존재해야 함 (없으면 400)
- 해당 블로그가 Flow.blog_links에 포함되어야 함 (없으면 404)
- GP 스테이지에서 publish/republish가 enabled여야 함 (아니면 409 Conflict)

**응답 형식**:
```json
{
    "status": "completed",
    "action": "publish",
    "blog_name": "내 블로그",
    "result": {
        "success": true,
        "post_title": "발행된 글 제목",
        "post_url": "https://...",
        "detail": "1건 발행 완료"
    },
    "duration_ms": 3200
}
```

#### 3.4.2 프론트엔드 - 블로그 카드 발행/재발행 버튼

Phase 2에서 생성한 `_blog_select_card.html`에 버튼을 추가합니다.

```
┌─────────────────────────────────┐
│ ☑ [WP] 블로그명                 │
├─────────────────────────────────┤
│ https://blog-url.com            │
│ 🏷 프롬프트 연동                │
│                                 │
│ [📤 1회 발행]  [🔄 1회 재발행]  │ ← 실행 버튼
└─────────────────────────────────┘
```

| 버튼 | 텍스트 | 아이콘 | 색상 | 조건 |
|------|--------|--------|------|------|
| 발행 | 1회 발행 | 📤 | rose | 플로우 저장 상태 + GP 존재 |
| 재발행 | 1회 재발행 | 🔄 | sky | 플로우 저장 상태 + GP 존재 |

**조건**:
- 플로우가 저장된 상태에서만 표시
- GP 모듈이 플로우에 포함되어 있을 때만 표시
- 해당 블로그가 Flow.blog_links에 포함되어야 함

#### 3.4.3 플로우 카드 실행 버튼 제거

| 작업 | 파일 | 줄 번호 | 내용 |
|------|------|---------|------|
| 1회 실행 버튼 제거 | `_card.html` | 15-31 | 초록색 ▶️ 버튼 제거 |
| executeFlow() 유지 | `list.js` | 996-1037 | 함수는 유지 (다른 곳에서 사용 가능) |

#### 3.4.4 검증 항목

- [ ] 블로그 카드에 발행/재발행 버튼이 표시되는지 확인
- [ ] GP 모듈 없는 플로우에서는 버튼이 숨겨지는지 확인
- [ ] 1회 발행 실행이 정상 동작하는지 확인
- [ ] 1회 재발행 실행이 정상 동작하는지 확인
- [ ] GP stage에서 비활성 시 적절한 에러 메시지가 표시되는지 확인
- [ ] 플로우 카드에서 실행 버튼이 제거되었는지 확인
- [ ] 실행 중 버튼 비활성화 + 스피너 표시되는지 확인

---

## 4. Phase 별 의존 관계

```
Phase 1: 탭 정리 + 레거시 제거
    │     (프론트엔드만, 독립적)
    │
    ▼
Phase 2: 카드 기반 렌더링
    │     (프론트엔드만, Phase 1 완료 필요)
    │
    ├──────────────────┐
    ▼                  ▼
Phase 3:            Phase 4:
모듈 개별 실행       블로그 발행/재발행
(백엔드+프론트)      (백엔드+프론트)
(Phase 2 완료 필요)  (Phase 2 완료 필요)
(Phase 3, 4는 병렬 가능)
```

---

## 5. 영향 범위

### 5.1 영향받지 않는 기능 (보존)

| 기능 | 파일 | 보존 이유 |
|------|------|----------|
| syncPromptModuleBlogs() | form.js 452-503 | 프롬프트 모듈 블로그 자동 연동 유지 |
| 프롬프트 연동 블로그 비활성화 | _form.html | isPromptLinkedBlog() 로직 유지 |
| 플로우 전체 실행 API | flows_execute.py | POST /api/v1/flows/{id}/execute 유지 |
| GP 기반 발행/재발행 | flows_execute.py | _execute_publish_action() 등 유지 |
| 오토런 시스템 | autorun/ | 변경 없음 |
| 모듈 관리 페이지 | modules/ | 변경 없음 |
| 블로그 관리 페이지 | blogs/ | 변경 없음 |

### 5.2 위험 요소

| 위험 | 확률 | 영향 | 대응 |
|------|------|------|------|
| 기존 플로우 폼 데이터 호환성 | 낮음 | 높음 | Phase 1에서 기존 selectedModules 데이터 구조 유지 |
| 카드 렌더링 성능 | 낮음 | 중간 | 모듈/블로그 수가 많을 때 가상 스크롤 검토 |
| 개별 실행 API 보안 | 중간 | 높음 | 플로우 소유자 권한 검증 필수 |
| 실행 중 충돌 | 중간 | 중간 | 동시 실행 방지 (executingModuleId 상태 관리) |

---

## 6. 데이터 플로우

### 6.1 모듈 개별 실행 (Phase 3)

```
사용자 → [1회 생성] 클릭
    │
    ▼
POST /api/v1/flows/{flow_id}/modules/{module_id}/execute
    │
    ▼
flows_execute.py:
    ├── 플로우 + 모듈 조회
    ├── 소유자 권한 확인
    ├── 모듈 타입 판별
    │
    ├── collect → _execute_collect_single()
    ├── data    → _execute_data_single()
    └── prompt  → Flow.blog_links 로드
                   ├── GP 컨텍스트 구성
                   └── 블로그별 FlowGenerateExecutor.execute_for_blog()
    │
    ▼
JSON 응답 → 프론트엔드 토스트 메시지
```

### 6.2 블로그별 발행/재발행 (Phase 4)

```
사용자 → [1회 발행] 클릭
    │
    ▼
POST /api/v1/flows/{flow_id}/blogs/{blog_id}/publish
    │
    ▼
flows_execute.py:
    ├── 플로우 + 블로그 조회
    ├── 소유자 권한 + blog_links 포함 여부 확인
    ├── GP 모듈 조회 + stage_params 결정
    ├── publish.enabled 확인
    └── 기존 _execute_publish_for_blog() 호출
    │
    ▼
JSON 응답 → 프론트엔드 토스트 메시지
```
