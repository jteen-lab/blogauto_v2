# 동작로그 시인성 개선 + 제목 일괄 단어 치환 구현 계획서

> **버전**: v1.0.0 | **작성일**: 2026-04-23 | **상태**: 계획

---

## 1. 개요

본 문서는 두 가지 독립 기능의 구현 계획을 통합 정리한다.

| # | 기능 | 목적 | 난이도 |
|---|------|------|--------|
| 1 | 동작로그 시인성 개선 | 로그 액션 타입별 색상 배지 + 좌측 보더로 시각적 구분 | 중 |
| 2 | 제목 일괄 단어 치환 | 임시/정식 제목에서 특정 단어를 일괄 검색/치환 | 중 |

두 기능은 서로 독립적이므로 병렬 구현 가능하다.

---

## 2. Feature 1: 동작로그 시인성 개선

### 2.1 현재 문제

- 로그 바(`bg-gray-900`)와 확장 패널 모두 동일한 회색 텍스트로 표시
- 생성/발행/재발행/수집 등 액션 타입을 텍스트를 직접 읽어야만 구분 가능
- 필터 탭(`전체`/`작업`/`활동`/`생성`)에 시각적 구분 요소 없음
- ERROR 행이 일반 행과 동일한 배경색

### 2.2 디자인: Option A + B 하이브리드

#### 2.2.1 액션 타입 배지 색상표

| 액션 타입 | 배지 배경 | 배지 텍스트 | 라벨 |
|-----------|-----------|-------------|------|
| 생성 (generate) | `bg-emerald-800/60` | `text-emerald-300` | 생성 |
| 발행 (publish) | `bg-blue-800/60` | `text-blue-300` | 발행 |
| 재발행 (republish) | `bg-violet-800/60` | `text-violet-300` | 재발행 |
| 수집 (collect) | `bg-cyan-800/60` | `text-cyan-300` | 수집 |
| 데이터 (data) | `bg-amber-800/60` | `text-amber-300` | 데이터 |
| 시스템 (기타) | `bg-gray-700/60` | `text-gray-400` | 시스템 |

#### 2.2.2 좌측 보더 색상표

| 액션 타입 | 보더 클래스 |
|-----------|------------|
| 생성 | `border-l-[3px] border-emerald-400` |
| 발행 | `border-l-[3px] border-blue-400` |
| 재발행 | `border-l-[3px] border-violet-400` |
| 수집 | `border-l-[3px] border-cyan-400` |
| 데이터 | `border-l-[3px] border-amber-400` |
| 시스템 | `border-l-[3px] border-gray-600` |

#### 2.2.3 ERROR 행 배경

- `bg-red-950/20` 클래스를 ERROR 레벨 행에 추가

#### 2.2.4 필터 탭 색상 점

필터 탭 라벨 앞에 2px 원형 점 추가:

| 탭 | 점 색상 |
|----|---------|
| 전체 | 없음 (기존 유지) |
| 작업 | `bg-blue-400` |
| 활동 | `bg-amber-400` |
| 생성 | `bg-emerald-400` |

### 2.3 ASCII 목업

#### 로그 바 (개선 후)

```
+-----------------------------------------------------------------------------------+
| bg-gray-900                                                                        |
|  ┌─ emerald-400 보더                                                              |
|  │ 14:32:05  SUCCESS  [생성]  [워]블로그A - 제목재조합 완료 - 성공                    |
|  ├─ blue-400 보더                                                                  |
|  │ 14:31:22  SUCCESS  [발행]  [구]블로그B - 발행 성공                                |
|  ├─ violet-400 보더                                                                |
|  │ 14:30:15  ERROR    [재발행] [워]블로그C - 재발행 실패(API 오류)  ← bg-red-950/20  |
+-----------------------------------------------------------------------------------+
```

#### 확장 패널 (개선 후)

```
+-----------------------------------------------------------------------------------+
| [전체]  [● 작업]  [● 활동]  [● 생성]               [검색...]                        |
|         blue     amber    emerald                                                 |
|                                                                                   |
|  ┌─ emerald-400                                                                   |
|  │ 14:32:05  SUCCESS  [생성]  [워]블로그A - 제목재조합 완료 - 성공                    |
|  ├─ blue-400                                                                      |
|  │ 14:31:22  SUCCESS  [발행]  [구]블로그B - 발행 성공                                |
|  ├─ violet-400                                                                    |
|  │ 14:30:15  ERROR    [재발행] [워]블로그C - 재발행 실패   ← bg-red-950/20 배경      |
|  ├─ cyan-400                                                                      |
|  │ 14:29:00  INFO     [수집]  제목 수집 - 건너뜀(재고 충분)                          |
|  ├─ gray-600                                                                      |
|  │ 14:28:30  INFO     [시스템] 플로우 초기화 - 성공                                  |
+-----------------------------------------------------------------------------------+
```

### 2.4 구현 단계

#### Phase 1: API에 `action_type` 필드 추가

**파일**: `app/routers/dashboard_logs.py`

현재 `_serialize_autorun_log()` 반환 딕셔너리의 `metadata.category`에 액션 값이 있지만,
최상위 레벨에 `action_type` 필드를 명시적으로 추가한다.

```python
# _serialize_autorun_log() 반환값에 추가
return {
    "id": f"action_{log.id}",
    "type": "action",
    "action_type": _get_action_type(log.action),  # 신규
    "timestamp": ...,
    "level": level,
    "title": title,
    ...
}
```

`_get_action_type()` 매핑:
- `generate` -> `"generate"`
- `publish` -> `"publish"`
- `republish` -> `"republish"`
- `collect` -> `"collect"`
- `data` -> `"data"`
- 그 외 -> `"system"`

**파일**: `app/routers/dashboard.py`

`/logs` 엔드포인트도 동일하게 `action_type` 필드 추가.
(dashboard.py의 로그 응답이 dashboard_logs.py와 동일한 형식을 사용하는지 확인 후 적용)

- [ ] `_get_action_type()` 헬퍼 함수 작성
- [ ] `_serialize_autorun_log()` 반환값에 `action_type` 추가
- [ ] `dashboard.py`의 `/logs` 응답에도 `action_type` 추가
- [ ] 기존 API 응답 하위 호환성 확인

#### Phase 2: JS 헬퍼 함수 추가

**파일**: `app/static/js/components/GlobalSummary.js`

3개 메서드를 `globalSummary()` 컴포넌트에 추가:

```javascript
// 액션 배지 Tailwind 클래스
getActionBadgeClass(actionType) {
    const map = {
        generate:  'bg-emerald-800/60 text-emerald-300',
        publish:   'bg-blue-800/60 text-blue-300',
        republish: 'bg-violet-800/60 text-violet-300',
        collect:   'bg-cyan-800/60 text-cyan-300',
        data:      'bg-amber-800/60 text-amber-300',
        system:    'bg-gray-700/60 text-gray-400',
    };
    return map[actionType] || map.system;
},

// 액션 라벨 텍스트
getActionLabel(actionType) {
    const map = {
        generate: '생성', publish: '발행', republish: '재발행',
        collect: '수집', data: '데이터', system: '시스템',
    };
    return map[actionType] || '시스템';
},

// 로그 행 좌측 보더 클래스
getLogRowBorderClass(actionType) {
    const map = {
        generate:  'border-l-[3px] border-emerald-400',
        publish:   'border-l-[3px] border-blue-400',
        republish: 'border-l-[3px] border-violet-400',
        collect:   'border-l-[3px] border-cyan-400',
        data:      'border-l-[3px] border-amber-400',
        system:    'border-l-[3px] border-gray-600',
    };
    return map[actionType] || map.system;
},

// ERROR 행 배경 클래스
getLogRowBgClass(level) {
    return level === 'ERROR' ? 'bg-red-950/20' : '';
},
```

- [ ] `getActionBadgeClass()` 메서드 추가
- [ ] `getActionLabel()` 메서드 추가
- [ ] `getLogRowBorderClass()` 메서드 추가
- [ ] `getLogRowBgClass()` 메서드 추가

#### Phase 3: 로그 바 + 확장 패널 템플릿 수정

**파일**: `app/templates/components/global_summary.html`

**(A) 로그 바 영역 (88~129행 부근)**

현재:
```html
<div class="log-row text-xs">
```

변경 후:
```html
<div class="log-row text-xs pl-1"
     :class="[getLogRowBorderClass(log.action_type), getLogRowBgClass(log.level)]">
```

레벨 배지 뒤에 액션 배지 `<span>` 추가:
```html
<span class="log-level-badge" ...>...</span>
<!-- 액션 타입 배지 (신규) -->
<span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
      :class="getActionBadgeClass(log.action_type)"
      x-text="getActionLabel(log.action_type)"></span>
```

**(B) 확장 패널 로그 목록 (174~188행 부근)**

현재:
```html
<div class="flex items-start gap-2 py-1 border-b border-gray-800/50 text-xs">
```

변경 후:
```html
<div class="flex items-start gap-2 py-1 border-b border-gray-800/50 text-xs pl-1"
     :class="[getLogRowBorderClass(log.action_type), getLogRowBgClass(log.level)]">
```

레벨 배지 뒤에 액션 배지 추가 (로그 바와 동일한 패턴).

- [ ] 로그 바 `log-row` div에 보더/배경 클래스 바인딩
- [ ] 로그 바에 액션 타입 배지 span 삽입
- [ ] 확장 패널 로그 행에 보더/배경 클래스 바인딩
- [ ] 확장 패널에 액션 타입 배지 span 삽입
- [ ] PC/모바일 양쪽에서 시각적 확인

#### Phase 4: 필터 탭 색상 점 추가

**파일**: `app/templates/components/global_summary.html`

현재 필터 탭 (151~157행):
```html
<template x-for="f in [{key:'all',label:'전체'},{key:'action',label:'작업'},
  {key:'activity',label:'활동'},{key:'generation',label:'생성'}]">
    <button ...>
        <span x-text="f.label"></span>
    </button>
</template>
```

변경: 각 필터 객체에 `dot` 속성 추가, 라벨 앞에 점 표시:
```html
<template x-for="f in [
    {key:'all',label:'전체',dot:''},
    {key:'action',label:'작업',dot:'bg-blue-400'},
    {key:'activity',label:'활동',dot:'bg-amber-400'},
    {key:'generation',label:'생성',dot:'bg-emerald-400'}
]" :key="f.key">
    <button ...>
        <span x-show="f.dot" class="w-1.5 h-1.5 rounded-full inline-block mr-1" :class="f.dot"></span>
        <span x-text="f.label"></span>
    </button>
</template>
```

- [ ] 필터 탭 데이터에 `dot` 속성 추가
- [ ] 점 표시 span 삽입
- [ ] 활성/비활성 상태에서 점 색상 확인

### 2.5 파일 변경 목록

| 파일 | 변경 내용 | 예상 줄 수 |
|------|----------|-----------|
| `app/routers/dashboard_logs.py` | `_get_action_type()` + 응답 필드 추가 | +15줄 |
| `app/routers/dashboard.py` | `/logs` 응답에 `action_type` 추가 | +10줄 |
| `app/static/js/components/GlobalSummary.js` | 4개 헬퍼 메서드 추가 | +35줄 |
| `app/templates/components/global_summary.html` | 배지/보더/배경/필터 수정 | +20줄 |

---

## 3. Feature 2: 제목 일괄 단어 치환

### 3.1 기능 설명

임시제목(TempTitle) 또는 정식제목(MainTitle)에서 특정 단어를 일괄 검색하여
다른 단어로 치환하거나 삭제하는 기능.

**핵심 사용 사례**:
- "2025년" 제거: "2025년 성공을 위한 방법" -> "성공을 위한 방법"
- 특정 단어 교체: "블로그" -> "사이트"

### 3.2 핵심 요구사항: 앞쪽 공백 제거

> **CRITICAL**: 치환 후 제목 맨 앞에 빈칸(공백)이 절대 남아서는 안 된다.

```
입력: "2025년 성공을 위한 수행 방법 5가지"
치환: "2025년" -> "" (삭제)

잘못된 결과: " 성공을 위한 수행 방법 5가지"   (앞쪽 공백 O)
올바른 결과: "성공을 위한 수행 방법 5가지"     (앞쪽 공백 X)
```

처리 순서:
1. `re.sub()` 로 치환 수행
2. `result.strip()` 으로 앞뒤 공백 제거
3. 연속 공백 정규화: `re.sub(r'\s+', ' ', result)`

### 3.3 UI 설계

#### 3.3.1 버튼 위치

임시제목/정식제목 탭의 액션 버튼 영역(`p-3 bg-gray-50 border-b`)에 추가:

```
+------------------------------------------------------------------+
| [중복 제거]  [카테고리 재분류]  [단어 치환]  [전체 삭제 (N)]        |
|  yellow       emerald          indigo        red                  |
+------------------------------------------------------------------+
```

버튼 스타일: `border-2 border-indigo-500 text-indigo-700 bg-white hover:bg-indigo-50`

#### 3.3.2 모달 목업

```
+-----------------------------------------------------------+
|  제목 단어 일괄 치환                                   [X]  |
+-----------------------------------------------------------+
|                                                           |
|  검색어 (필수)                                             |
|  +-----------------------------------------------------+ |
|  | 2025년                                               | |
|  +-----------------------------------------------------+ |
|                                                           |
|  치환어 (비우면 삭제)                                       |
|  +-----------------------------------------------------+ |
|  |                                                      | |
|  +-----------------------------------------------------+ |
|                                                           |
|  [ ] 대소문자 구분                                         |
|                                                           |
|  +---------------------------------------------------+   |
|  | [미리보기]                              [적용하기] |   |
|  +---------------------------------------------------+   |
|                                                           |
|  --- 미리보기 결과 (23건 영향) -----------------------     |
|                                                           |
|  #101  2025년 성공을 위한 방법                              |
|     -> 성공을 위한 방법                                    |
|                                                           |
|  #102  2025년 최고의 전략 10선                              |
|     -> 최고의 전략 10선                                    |
|                                                           |
|  ⚠ 중복 경고: 2건이 기존 제목과 중복됩니다                    |
|  ⚠ 빈 제목 경고: 0건                                       |
|                                                           |
|  --- 적용 확인 ---                                        |
|  [취소]                             [23건 치환 확정하기]    |
|                                                           |
+-----------------------------------------------------------+
```

### 3.4 API 설계

#### 3.4.1 엔드포인트

```
POST /api/v1/data/titles/bulk-replace
```

#### 3.4.2 요청 스키마

```python
class BulkReplaceRequest(BaseModel):
    """제목 일괄 치환 요청"""
    target: str              # "temp" | "main"
    find_text: str           # 검색어 (필수, 1자 이상)
    replace_text: str = ""   # 치환어 (빈 문자열 = 삭제 모드)
    case_sensitive: bool = False  # 대소문자 구분
    mode: str                # "preview" | "apply"
    title_ids: Optional[List[int]] = None  # None = 전체, 배열 = 선택된 것만
```

#### 3.4.3 응답 스키마 - Preview 모드

```json
{
    "mode": "preview",
    "total_affected": 23,
    "previews": [
        {
            "id": 101,
            "original": "2025년 성공을 위한 수행 방법 5가지",
            "replaced": "성공을 위한 수행 방법 5가지"
        }
    ],
    "duplicates_warning": 2,
    "empty_warning": 0
}
```

#### 3.4.4 응답 스키마 - Apply 모드

```json
{
    "mode": "apply",
    "updated": 23,
    "skipped_duplicates": 2,
    "skipped_empty": 0,
    "message": "23개 제목이 변경되었습니다"
}
```

### 3.5 처리 규칙

#### 3.5.1 치환 로직 (Python 의사코드)

```python
import re

def bulk_replace_titles(titles, find_text, replace_text, case_sensitive):
    """제목 일괄 치환 핵심 로직"""
    # 1. 안전한 정규식 패턴 생성
    pattern = re.escape(find_text)
    flags = 0 if case_sensitive else re.IGNORECASE

    results = []
    duplicates = set()
    empty_count = 0

    for title in titles:
        # 2. 치환 수행
        new_text = re.sub(pattern, replace_text, title.title, flags=flags)

        # 3. [CRITICAL] 앞뒤 공백 제거
        new_text = new_text.strip()

        # 4. 연속 공백 정규화
        new_text = re.sub(r'\s+', ' ', new_text)

        # 5. 빈 제목/너무 짧은 제목 건너뛰기
        if len(new_text) < 2:
            empty_count += 1
            continue

        # 6. 중복 제목 건너뛰기
        if is_duplicate(new_text, existing_titles):
            duplicates.add(title.id)
            continue

        results.append((title.id, title.title, new_text))

    return results, len(duplicates), empty_count
```

#### 3.5.2 엣지 케이스 처리

| 상황 | 처리 방식 |
|------|----------|
| 치환어 비어있음 | 삭제 모드 (해당 단어 제거) |
| 치환 후 앞쪽 공백 | `strip()` 으로 제거 **(필수)** |
| 치환 후 연속 공백 | `re.sub(r'\s+', ' ', text)` 로 정규화 |
| 치환 결과 빈 문자열 | 건너뛰기 + `empty_warning` 카운트 |
| 치환 결과 < 2자 | 건너뛰기 + `empty_warning` 카운트 |
| 치환 결과 중복 제목 | 건너뛰기 + `duplicates_warning` 카운트 |
| 검색어 없음 | 400 에러 반환 |
| 정규식 특수문자 | `re.escape()` 로 안전 처리 |

#### 3.5.3 트랜잭션 처리

- Preview 모드: 읽기 전용, DB 변경 없음
- Apply 모드: 단일 트랜잭션으로 모든 변경사항 커밋
- 실패 시 전체 롤백

### 3.6 구현 단계

#### Phase 1: Backend API 구현

**파일**: `app/routers/data_titles.py`

- [ ] `BulkReplaceRequest` Pydantic 스키마 추가
- [ ] `BulkReplacePreview` 응답 스키마 추가
- [ ] `POST /bulk-replace` 엔드포인트 구현
- [ ] `_perform_bulk_replace()` 핵심 로직 함수 구현
- [ ] Preview 모드 구현 (읽기 전용)
- [ ] Apply 모드 구현 (트랜잭션)
- [ ] `strip()` + 연속 공백 정규화 적용
- [ ] 중복 감지 로직 구현
- [ ] 빈 제목 감지 로직 구현
- [ ] 에러 핸들링 + 로깅

예상 추가 분량: ~120줄

#### Phase 2: UI 버튼 추가

**파일**: `app/templates/collection/_titles.html` (임시제목)

```html
<!-- 단어 치환 버튼 -->
<button
    x-show="stats.temp?.total > 0"
    @click="openBulkReplace('temp')"
    class="inline-flex items-center justify-center px-3 py-2
           border-2 border-indigo-500 rounded-lg text-sm font-medium
           text-indigo-700 bg-white hover:bg-indigo-50 transition-colors">
    <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/>
    </svg>
    <span class="hidden sm:inline">단어 치환</span>
    <span class="sm:hidden">치환</span>
</button>
```

**파일**: `app/templates/collection/_titles_main.html` (정식제목)

동일 패턴으로 버튼 추가. `@click="openBulkReplace('main')"` 으로 target 구분.

- [ ] `_titles.html` 에 단어 치환 버튼 추가
- [ ] `_titles_main.html` 에 단어 치환 버튼 추가

#### Phase 3: 모달 + JS 구현

**파일**: `app/templates/collection/index.html`

모달 HTML + Alpine.js 로직을 페이지 하단에 추가:

```javascript
// Alpine.js 데이터 (collection 컴포넌트 내부)
bulkReplace: {
    open: false,
    target: 'temp',     // 'temp' | 'main'
    findText: '',
    replaceText: '',
    caseSensitive: false,
    loading: false,
    previews: [],
    totalAffected: 0,
    duplicatesWarning: 0,
    emptyWarning: 0,
    previewLoaded: false,
    applyConfirm: false,
},

openBulkReplace(target) {
    this.bulkReplace = {
        open: true, target,
        findText: '', replaceText: '',
        caseSensitive: false, loading: false,
        previews: [], totalAffected: 0,
        duplicatesWarning: 0, emptyWarning: 0,
        previewLoaded: false, applyConfirm: false,
    };
},

async previewBulkReplace() {
    if (!this.bulkReplace.findText.trim()) return;
    this.bulkReplace.loading = true;
    try {
        const resp = await fetch('/api/v1/data/titles/bulk-replace', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target: this.bulkReplace.target,
                find_text: this.bulkReplace.findText,
                replace_text: this.bulkReplace.replaceText,
                case_sensitive: this.bulkReplace.caseSensitive,
                mode: 'preview',
            }),
        });
        const data = await resp.json();
        Object.assign(this.bulkReplace, {
            previews: data.previews || [],
            totalAffected: data.total_affected || 0,
            duplicatesWarning: data.duplicates_warning || 0,
            emptyWarning: data.empty_warning || 0,
            previewLoaded: true,
        });
    } finally {
        this.bulkReplace.loading = false;
    }
},

async applyBulkReplace() {
    this.bulkReplace.loading = true;
    try {
        const resp = await fetch('/api/v1/data/titles/bulk-replace', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target: this.bulkReplace.target,
                find_text: this.bulkReplace.findText,
                replace_text: this.bulkReplace.replaceText,
                case_sensitive: this.bulkReplace.caseSensitive,
                mode: 'apply',
            }),
        });
        const data = await resp.json();
        // 성공 알림 + 목록 새로고침
        this.showToast(`${data.updated}개 제목이 변경되었습니다`, 'success');
        this.bulkReplace.open = false;
        this.loadTitles();  // 또는 loadMainTitles()
    } finally {
        this.bulkReplace.loading = false;
    }
},
```

- [ ] 모달 HTML 템플릿 작성
- [ ] `openBulkReplace()` 메서드 구현
- [ ] `previewBulkReplace()` 메서드 구현
- [ ] `applyBulkReplace()` 메서드 구현
- [ ] 미리보기 결과 렌더링 (변경 전 -> 변경 후)
- [ ] 경고 표시 (중복, 빈 제목)
- [ ] 확인 단계 UI (적용 전 최종 확인)
- [ ] 로딩 스피너 표시

### 3.7 파일 변경 목록

| 파일 | 변경 내용 | 예상 줄 수 |
|------|----------|-----------|
| `app/routers/data_titles.py` | `BulkReplaceRequest` + `POST /bulk-replace` | +120줄 |
| `app/templates/collection/_titles.html` | 단어 치환 버튼 | +15줄 |
| `app/templates/collection/_titles_main.html` | 단어 치환 버튼 | +15줄 |
| `app/templates/collection/index.html` | 모달 HTML + JS 함수 | +150줄 |

---

## 4. 통합 파일 변경 목록

| # | 파일 경로 | Feature | 변경 유형 |
|---|----------|---------|----------|
| 1 | `app/routers/dashboard_logs.py` | F1 | 수정 |
| 2 | `app/routers/dashboard.py` | F1 | 수정 |
| 3 | `app/static/js/components/GlobalSummary.js` | F1 | 수정 |
| 4 | `app/templates/components/global_summary.html` | F1 | 수정 |
| 5 | `app/routers/data_titles.py` | F2 | 수정 |
| 6 | `app/templates/collection/_titles.html` | F2 | 수정 |
| 7 | `app/templates/collection/_titles_main.html` | F2 | 수정 |
| 8 | `app/templates/collection/index.html` | F2 | 수정 |

총 8개 파일 변경. 신규 파일 없음.

---

## 5. 테스트 계획

### 5.1 Feature 1: 동작로그 시인성

| # | 테스트 항목 | 검증 방법 |
|---|-----------|----------|
| 1 | API 응답에 `action_type` 필드 포함 | `GET /dashboard/unified-logs` 호출 후 응답 확인 |
| 2 | 각 액션 타입별 올바른 배지 색상 | 브라우저에서 시각적 확인 (생성/발행/재발행/수집/데이터/시스템) |
| 3 | 좌측 보더 색상 정확성 | 로그 바 + 확장 패널에서 시각적 확인 |
| 4 | ERROR 행 빨간 배경 | ERROR 로그 발생 후 배경색 확인 |
| 5 | 필터 탭 색상 점 | 필터 탭에서 점 표시 확인 |
| 6 | 모바일 반응형 | 모바일 뷰포트에서 배지/보더 깨짐 확인 |

### 5.2 Feature 2: 제목 일괄 치환

| # | 테스트 항목 | 검증 방법 |
|---|-----------|----------|
| 1 | Preview 모드 정상 동작 | 미리보기 요청 후 결과 확인, DB 미변경 확인 |
| 2 | Apply 모드 정상 동작 | 적용 후 DB 실제 변경 확인 |
| 3 | 앞쪽 공백 제거 | "2025년 성공..." -> "성공..." (공백 없음) |
| 4 | 연속 공백 정규화 | "A  B" -> "A B" |
| 5 | 빈 제목 건너뛰기 | 치환 결과 빈 문자열일 때 `empty_warning` 반환 |
| 6 | 중복 제목 건너뛰기 | 치환 결과 기존 제목과 동일할 때 `duplicates_warning` 반환 |
| 7 | 대소문자 구분 옵션 | `case_sensitive=true` 시 정확히 매칭 |
| 8 | 특수문자 안전 처리 | "(", ")" 등 정규식 특수문자 포함 검색어 |
| 9 | 임시제목/정식제목 구분 | `target=temp`/`target=main` 각각 올바른 테이블 조회 |
| 10 | 트랜잭션 롤백 | 중간 오류 시 전체 롤백 확인 |

### 5.3 수동 테스트 시나리오

**시나리오 1: 기본 삭제**
1. 임시제목에 "2025년 성공을 위한 방법" 등록
2. 단어 치환 -> 검색어: "2025년", 치환어: (비움)
3. 미리보기 -> "성공을 위한 방법" 확인 (앞 공백 없음)
4. 적용 -> DB 반영 확인

**시나리오 2: 단어 교체**
1. 검색어: "블로그", 치환어: "사이트"
2. 미리보기 -> 영향 받는 제목 확인
3. 적용 후 목록 새로고침 확인

**시나리오 3: 중복 발생 케이스**
1. "A 제목", "제목" 두 개 존재
2. "A " 삭제 시 -> "제목" 중복 -> 건너뛰기 + 경고

---

## 6. 리스크 및 고려사항

### 6.1 Feature 1 리스크

| 리스크 | 영향도 | 대응 |
|--------|--------|------|
| Tailwind 동적 클래스 미생성 | 중 | `safelist` 또는 전체 클래스 명시적 작성 확인 |
| 기존 로그 데이터에 `action_type` 없음 | 하 | JS 측에서 `action_type` 미존재 시 `"system"` 폴백 |
| 모바일에서 배지 과다로 줄 넘침 | 중 | 모바일에서 액션 배지를 아이콘만 표시 또는 축소 검토 |

### 6.2 Feature 2 리스크

| 리스크 | 영향도 | 대응 |
|--------|--------|------|
| 대량 제목 치환 시 성능 | 중 | 1000건 이상 시 배치 처리 또는 경고 표시 |
| 실수로 전체 제목 변경 | 높 | Preview 필수 + 확인 단계 2중 검증 |
| 치환 후 앞쪽 공백 잔존 | 높 | `strip()` 필수 적용 + 테스트 케이스 포함 |
| 정규식 특수문자 오류 | 중 | `re.escape()` 사용으로 안전 처리 |
| MainTitle의 `matched_blog_ids` 영향 | 하 | 제목 텍스트만 변경, 연관 필드 미변경 |

### 6.3 공통 고려사항

- 두 기능 모두 기존 API 하위 호환성을 유지해야 함
- Feature 1의 `action_type` 필드는 기존 클라이언트에 영향 없음 (추가 필드)
- Feature 2의 신규 엔드포인트이므로 하위 호환성 문제 없음
- Docker 재빌드 불필요 (Python/JS/HTML 변경만, 패키지 추가 없음)

---

> **작성**: Claude Code | **최종 수정**: 2026-04-23
