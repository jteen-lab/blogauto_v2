# 테이블 스타일 전용 편집 UI 구현 계획서

> **버전**: v1.0.0 | **날짜**: 2026-04-23 | **상태**: 계획

---

## 1. 개요

### 1.1 목적
기존 블로그 스타일 탭의 범용 CSS 선택자 편집기와 **공존하는** 테이블 전용 스타일 편집 UI를 추가한다. 사용자가 CSS 속성을 개별적으로 입력하는 대신, 프리셋 선택/색상 피커/슬라이더 등 시각적 컨트롤로 테이블 스타일을 직관적으로 설정할 수 있게 한다.

### 1.2 핵심 목표
- 테이블 스타일링에 CSS 지식이 필요 없도록 시각적 UI 제공
- 기존 범용 편집기와 양방향 동기화 (같은 `styleConfig` 객체 공유)
- 행 교대 색상(Zebra Striping), 테이블 레이아웃 등 신규 기능 추가
- 백엔드 변경 없이 프론트엔드만으로 구현 (기존 `style_config` JSON 구조 활용)

### 1.3 범위
- 수정 파일: 5개 (HTML 1개 신규, JS 3개 수정, HTML 1개 수정)
- 신규 기능: 테이블 프리셋 5종, Zebra Striping, 테이블 레이아웃 설정
- 백엔드/DB 변경: 없음

---

## 2. 현재 시스템 분석

### 2.1 기존 스타일 편집기 구조

```
_tab_style.html (메인 레이아웃)
├── 좌측 (3col): 선택자 목록 패널
│   └── h1, h2, ..., table, th, td, blockquote
├── 중앙 (5col): 범용 스타일 편집 패널
│   └── 폰트/여백/테두리/배경 섹션
└── 우측 (4col): 실시간 미리보기 (iframe)
```

**JS 파일 구조:**
- `style-tab.js` — Alpine.js 메인 컴포넌트 (`styleTabApp()`)
- `style-tab-presets.js` — 프리셋 정의, 선택자 목록, 샘플 HTML
- `style-tab-css-utils.js` — CSS 생성, 미리보기 HTML 생성 유틸리티

**데이터 흐름:**
```
styleConfig (객체) → generateCssFromConfig() → CSS 문자열
                   → 미리보기 iframe 갱신
                   → 저장 시 API POST /api/v1/blogs/{id}/settings/style
```

### 2.2 현재 한계점
- `table`, `th`, `td` 선택자를 개별적으로 편집해야 함 (3번 반복 작업)
- 테두리 프리셋(가로선만, 외곽선만 등) 없음
- Zebra Striping 불가 (`tr:nth-child()` 선택자 미지원)
- 테이블 레이아웃 속성(`border-collapse`, `border-spacing`) 설정 불편

### 2.3 백엔드 호환성 확인
- `blog_settings_service.py`의 `generate_css()`: `style_config.items()` 순회하여 모든 선택자를 CSS로 변환 → **임의의 선택자 키 지원 (호환됨)**
- `blog_settings.py` 스키마: `Dict[str, Dict[str, str]]` 타입 → **임의의 키 허용 (호환됨)**
- `tr:nth-child(even)`, `tr:nth-child(odd)` 같은 키도 그대로 저장/생성 가능

---

## 3. 설계

### 3.1 통합 방식

테이블 전용 UI는 기존 3컬럼 레이아웃의 **중앙 패널을 조건부 전환**하는 방식으로 통합한다.

```
┌─────────────────────────────────────────────────────────┐
│  상단 도구바: [프리셋 ▼] [CSS 코드] [초기화] [저장]     │
├──────────┬────────────────────────┬─────────────────────┤
│ 선택자   │                        │                     │
│ 목록     │    중앙 편집 패널       │    미리보기          │
│          │                        │                     │
│ ┌──────┐ │  tableMode === true    │    ┌─────────────┐  │
│ │테이블│ │  → 테이블 전용 편집기   │    │  ┌───┬───┐  │  │
│ │ 설정 │ │                        │    │  │ H │ H │  │  │
│ ├──────┤ │  tableMode === false   │    │  ├───┼───┤  │  │
│ │ h1   │ │  → 범용 스타일 편집기   │    │  │ D │ D │  │  │
│ │ h2   │ │                        │    │  ├───┼───┤  │  │
│ │ ...  │ │                        │    │  │ D │ D │  │  │
│ │table │ │                        │    │  └───┴───┘  │  │
│ │[통합]│ │                        │    │             │  │
│ │ th   │ │                        │    └─────────────┘  │
│ │[통합]│ │                        │                     │
│ │ td   │ │                        │                     │
│ │[통합]│ │                        │                     │
│ │block │ │                        │                     │
│ │quote │ │                        │                     │
│ └──────┘ │                        │                     │
├──────────┴────────────────────────┴─────────────────────┤
│  CSS 코드 패널 (접이식)                                  │
└─────────────────────────────────────────────────────────┘
```

**전환 규칙:**
1. "테이블 설정" 버튼 클릭 → `tableMode = true`, 중앙 패널이 테이블 전용 편집기로 전환
2. 선택자 목록에서 아무 항목 클릭 → `tableMode = false`, 해당 선택자의 범용 편집기로 전환
3. `table`, `th`, `td` 선택자에는 `[통합]` 배지 표시 (테이블 UI에서 통합 관리됨을 표시)
4. `[통합]` 배지가 있는 선택자 클릭 시에도 범용 편집기로 전환 (고급 사용자용)

### 3.2 UI 컨트롤 상세

#### A. 테이블 프리셋 (5종)

```
┌─────────────────────────────────────────────┐
│  테이블 프리셋                               │
│  ┌─────┐ ┌─────┐ ┌──────┐ ┌──────┐ ┌────┐ │
│  │심플 │ │모던 │ │클래식│ │미니멀│ │다크│  │
│  └─────┘ └─────┘ └──────┘ └──────┘ └────┘  │
│  각 버튼 하단에 미니 프리뷰 테두리 스타일     │
└─────────────────────────────────────────────┘
```

HTML 구조:
```html
<div class="flex flex-wrap gap-2">
  <button @click="applyTablePreset('simple')"
          class="flex-1 min-w-[80px] px-3 py-2 text-xs border rounded-lg
                 hover:bg-gray-50 transition-colors text-center">
    <div class="font-medium mb-1">심플</div>
    <div class="w-full h-4 border border-gray-300 rounded-sm"></div>
  </button>
  <!-- ... 4개 더 -->
</div>
```

#### B. 전체 테두리

```
┌─────────────────────────────────────────────┐
│  테두리                                      │
│                                              │
│  빠른 선택:                                   │
│  ┌────┐ ┌────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │없음│ │전체│ │가로선│ │세로선│ │외곽선│   │
│  └────┘ └────┘ └──────┘ └──────┘ └──────┘   │
│                                              │
│  색상: [■ #e5e7eb ]  두께: [===●=== 2px]     │
│  스타일: [ solid  ▼]                          │
└─────────────────────────────────────────────┘
```

빠른 선택 버튼 5종:
- **없음**: `border-style: none` (table, th, td 모두)
- **전체**: `border-style: solid` + 지정 색상/두께
- **가로선만**: `border-top/bottom-style: solid`, 좌우 none
- **세로선만**: `border-left/right-style: solid`, 상하 none
- **외곽선만**: table에만 border, th/td는 border none

#### C. 헤더 스타일 (th)

```
┌─────────────────────────────────────────────┐
│  헤더 (th)                                   │
│                                              │
│  배경색: [■ #f3f4f6 ]   글자색: [■ #1f2937 ] │
│                                              │
│  프리셋 팔레트:                               │
│  [■][■][■][■][■][■][■][■]                    │
│                                              │
│  굵기: [Normal ▼] [Semi Bold ▼] [Bold ▼]     │
│                                              │
│  패딩:  컴팩트 ──●────── 기본 ────── 여유     │
│         (6px)          (10px)       (14px)    │
└─────────────────────────────────────────────┘
```

프리셋 팔레트 색상 (8종):
```
#f3f4f6 (회색), #dbeafe (파랑), #dcfce7 (초록), #fef3c7 (노랑),
#fce7f3 (핑크), #e0e7ff (인디고), #f3e8ff (보라), #1f2937 (다크)
```

#### D. 데이터 셀 스타일 (td)

```
┌─────────────────────────────────────────────┐
│  데이터 셀 (td)                              │
│                                              │
│  배경색: [■ transparent ]  글자색: [■ #333 ]  │
│                                              │
│  패딩:  컴팩트 ────●──── 기본 ────── 여유     │
│         (6px)          (10px)       (14px)    │
└─────────────────────────────────────────────┘
```

#### E. 행 교대 색상 (Zebra Striping)

```
┌─────────────────────────────────────────────┐
│  행 교대 색상                  [ ●━━ ON  ]   │
│                                              │
│  짝수 행: [■ #f9fafb ]                       │
│  홀수 행: [■ #ffffff  ]                       │
│                                              │
│  미리보기:                                    │
│  ┌──────────────────┐                        │
│  │ ████████████████ │ ← 짝수 행 색상          │
│  │                  │ ← 홀수 행 색상          │
│  │ ████████████████ │ ← 짝수 행 색상          │
│  └──────────────────┘                        │
└─────────────────────────────────────────────┘
```

**신규 기능 구현:**
- 토글 ON 시 `tr:nth-child(even)`, `tr:nth-child(odd)` 키를 `styleConfig`에 추가
- 토글 OFF 시 해당 키 삭제
- `HIDDEN_SELECTORS` 배열에 등록하여 좌측 선택자 목록에서 숨김

#### F. 테이블 레이아웃

```
┌─────────────────────────────────────────────┐
│  테이블 레이아웃                              │
│                                              │
│  너비: ( ) auto  (●) 100%  ( ) 직접입력 [  ] │
│                                              │
│  테두리 합침:  [●━━ collapse]                 │
│  (collapse: 테두리 겹침 / separate: 분리)     │
│                                              │
│  테두리 간격: [===●=== 2px]                   │
│  (separate 모드에서만 활성)                    │
└─────────────────────────────────────────────┘
```

### 3.3 프리셋 정의

5종 테이블 프리셋의 정확한 CSS 값:

```javascript
const TABLE_PRESETS = {
    simple: {
        label: '심플',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        th: {
            'background-color': '#f3f4f6',
            'color': '#1f2937',
            'font-weight': '600',
            'padding-top': '10',
            'padding-right': '12',
            'padding-bottom': '10',
            'padding-left': '12',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        td: {
            'color': '#374151',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        zebra: null
    },

    modern: {
        label: '모던',
        table: {
            'width': '100%',
            'border-collapse': 'separate',
            'border-radius': '8'
        },
        th: {
            'background-color': '#3b82f6',
            'color': '#ffffff',
            'font-weight': '600',
            'padding-top': '12',
            'padding-right': '16',
            'padding-bottom': '12',
            'padding-left': '16'
        },
        td: {
            'color': '#374151',
            'padding-top': '10',
            'padding-right': '16',
            'padding-bottom': '10',
            'padding-left': '16'
        },
        zebra: null
    },

    classic: {
        label: '클래식',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '2',
            'border-color': '#374151'
        },
        th: {
            'background-color': '#e5e7eb',
            'color': '#111827',
            'font-weight': 'bold',
            'padding-top': '10',
            'padding-right': '14',
            'padding-bottom': '10',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '2',
            'border-color': '#374151'
        },
        td: {
            'color': '#1f2937',
            'padding-top': '8',
            'padding-right': '14',
            'padding-bottom': '8',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#9ca3af'
        },
        zebra: null
    },

    minimal: {
        label: '미니멀',
        table: {
            'width': '100%',
            'border-collapse': 'collapse'
        },
        th: {
            'color': '#6b7280',
            'font-weight': '500',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-bottom-style': 'solid',
            'border-bottom-width': '2',
            'border-bottom-color': '#e5e7eb'
        },
        td: {
            'color': '#374151',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-bottom-style': 'solid',
            'border-bottom-width': '1',
            'border-bottom-color': '#f3f4f6'
        },
        zebra: null
    },

    dark: {
        label: '다크',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        th: {
            'background-color': '#1f2937',
            'color': '#ffffff',
            'font-weight': '600',
            'padding-top': '12',
            'padding-right': '14',
            'padding-bottom': '12',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        td: {
            'color': '#e5e7eb',
            'padding-top': '10',
            'padding-right': '14',
            'padding-bottom': '10',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        zebra: {
            even: '#111827',
            odd: '#1f2937'
        }
    }
};
```

### 3.4 Zebra Striping 구현

#### 숨겨진 선택자 방식

```javascript
// style-tab-presets.js에 추가
const HIDDEN_SELECTORS = ['tr:nth-child(even)', 'tr:nth-child(odd)'];
```

**동작 원리:**
1. Zebra 토글 ON → `styleConfig['tr:nth-child(even)']`, `styleConfig['tr:nth-child(odd)']` 생성
2. Zebra 토글 OFF → 해당 키 삭제
3. `STYLE_SELECTORS` 배열에는 포함하지 않음 → 좌측 목록에 표시 안 됨
4. `generateCssFromConfig()` 수정: `HIDDEN_SELECTORS`도 CSS에 포함
5. 미리보기 테이블: 4행 이상으로 수정하여 Zebra 효과 확인 가능

#### CSS 생성 확장

```javascript
// style-tab-css-utils.js의 generateCssFromConfig() 수정
function generateCssFromConfig(selectors, styleConfig, placeholderConfig) {
    const lines = [];

    // 기존: selectors 배열 순회
    for (const selector of selectors) { /* ... 기존 로직 ... */ }

    // 추가: HIDDEN_SELECTORS 순회
    const hiddenSelectors = typeof HIDDEN_SELECTORS !== 'undefined'
        ? HIDDEN_SELECTORS : [];
    for (const selector of hiddenSelectors) {
        const config = styleConfig[selector];
        if (!config || Object.keys(config).length === 0) continue;
        // selector 그대로 사용 (buildCssSelector 불필요)
        const properties = [];
        for (const [prop, value] of Object.entries(config)) {
            if (!value) continue;
            properties.push(`    ${prop}: ${value};`);
        }
        if (properties.length > 0) {
            lines.push(`${selector} {`);
            lines.push(...properties);
            lines.push('}');
            lines.push('');
        }
    }

    return lines.join('\n');
}
```

### 3.5 데이터 동기화

#### 양방향 동기화 메커니즘

```
테이블 UI 컨트롤 변경
    ↓
tableConfig 객체 업데이트 (UI 상태)
    ↓
styleConfig['table'] / ['th'] / ['td'] / ['tr:nth-child(*)'] 동기화
    ↓
debounceUpdatePreview() → CSS 재생성 → 미리보기 갱신

범용 편집기에서 table/th/td 편집
    ↓
styleConfig 직접 변경 (기존 로직)
    ↓
tableMode 전환 시 syncTableConfigFromStyleConfig() 호출
    ↓
tableConfig 역동기화 → 테이블 UI 컨트롤 반영
```

**`tableConfig` 객체 구조:**
```javascript
tableConfig: {
    // 테두리
    borderPreset: 'all',       // 'none'|'all'|'horizontal'|'vertical'|'outline'
    borderColor: '#e5e7eb',
    borderWidth: 1,
    borderStyle: 'solid',
    // 헤더
    thBgColor: '#f3f4f6',
    thTextColor: '#1f2937',
    thFontWeight: '600',
    thPadding: 10,             // 6|10|14
    // 데이터 셀
    tdBgColor: '',
    tdTextColor: '#374151',
    tdPadding: 8,
    // Zebra
    zebraEnabled: false,
    zebraEvenColor: '#f9fafb',
    zebraOddColor: '#ffffff',
    // 레이아웃
    tableWidth: '100%',        // 'auto'|'100%'|custom
    tableWidthCustom: '',
    borderCollapse: 'collapse', // 'collapse'|'separate'
    borderSpacing: '0'
}
```

**동기화 함수:**
```javascript
// tableConfig → styleConfig (테이블 UI 변경 시)
syncStyleConfigFromTable() {
    // table 속성 매핑
    this.styleConfig['table'] = {
        'width': this.tableConfig.tableWidth === 'custom'
            ? this.tableConfig.tableWidthCustom
            : this.tableConfig.tableWidth,
        'border-collapse': this.tableConfig.borderCollapse,
        ...this.buildBorderProps('table'),
        ...
    };
    // th, td 속성 매핑
    // zebra 속성 매핑
    this.debounceUpdatePreview();
}

// styleConfig → tableConfig (테이블 모드 진입 시)
syncTableConfigFromStyleConfig() {
    const tbl = this.styleConfig['table'] || {};
    const th = this.styleConfig['th'] || {};
    const td = this.styleConfig['td'] || {};
    const even = this.styleConfig['tr:nth-child(even)'] || {};

    this.tableConfig.thBgColor = th['background-color'] || '#f3f4f6';
    this.tableConfig.thTextColor = th['color'] || '#1f2937';
    this.tableConfig.borderCollapse = tbl['border-collapse'] || 'collapse';
    this.tableConfig.zebraEnabled = Object.keys(even).length > 0;
    // ... 나머지 역매핑
}
```

---

## 4. 구현 단계

### Phase 1: 프리셋 데이터 + 숨겨진 셀렉터 CSS

**파일:** `style-tab-presets.js`, `style-tab-css-utils.js`

- [ ] `TABLE_PRESETS` 객체 정의 (5종 프리셋, 정확한 CSS 값)
- [ ] `HIDDEN_SELECTORS` 배열 정의 (`tr:nth-child(even)`, `tr:nth-child(odd)`)
- [ ] `SAMPLE_CONTENT` 수정: 테이블 행을 4행 이상으로 변경 (Zebra 확인용)
- [ ] `generateCssFromConfig()` 수정: `HIDDEN_SELECTORS` 순회 로직 추가
- [ ] `generatePreviewHtml()` 수정: 기본 테이블 스타일에서 `th, td` 기본 border 제거 (사용자 설정과 충돌 방지)

**예상 변경량:** ~110줄

### Phase 2: JS 로직

**파일:** `style-tab.js`

- [ ] `tableMode` 상태 변수 추가 (기본값: `false`)
- [ ] `tableConfig` 객체 추가 (섹션 3.5 구조)
- [ ] `enterTableMode()` 함수: `tableMode = true`, `syncTableConfigFromStyleConfig()` 호출
- [ ] `exitTableMode()` 함수: 선택자 클릭 시 `tableMode = false`
- [ ] `syncStyleConfigFromTable()` 함수: tableConfig → styleConfig 동기화
- [ ] `syncTableConfigFromStyleConfig()` 함수: styleConfig → tableConfig 역동기화
- [ ] `applyTablePreset(presetName)` 함수: 테이블 프리셋 적용
- [ ] `updateTableStyle(section, property, value)` 함수: 개별 속성 변경 핸들러
- [ ] `buildBorderPropsForSelector(selector)` 함수: borderPreset에 따른 방향별 border 생성
- [ ] `toggleZebra()` 함수: Zebra on/off + styleConfig 키 생성/삭제
- [ ] 기존 선택자 클릭 핸들러 수정: `tableMode = false` 추가

**예상 변경량:** ~100줄

### Phase 3: 테이블 편집 패널 HTML

**파일:** `_tab_style_table.html` (신규)

- [ ] 섹션 A: 테이블 프리셋 버튼 5종 (각 프리셋별 미니 프리뷰 아이콘)
- [ ] 섹션 B: 테두리 — 빠른 선택 버튼 5종 + 색상 피커 + 두께 슬라이더 + 스타일 드롭다운
- [ ] 섹션 C: 헤더 스타일 — 배경색/글자색 피커 + 프리셋 팔레트 + 굵기 선택 + 패딩 슬라이더
- [ ] 섹션 D: 데이터 셀 — 배경색/글자색 피커 + 패딩 슬라이더
- [ ] 섹션 E: Zebra Striping — 토글 + 짝수/홀수 색상 피커 + 미니 프리뷰
- [ ] 섹션 F: 테이블 레이아웃 — 너비 라디오 + collapse 토글 + spacing 입력
- [ ] `max-h-[500px] overflow-y-auto` 스크롤 처리

**예상 변경량:** ~250줄

### Phase 4: 기존 스타일 탭 통합

**파일:** `_tab_style.html`

- [ ] 좌측 선택자 목록 상단에 "테이블 설정" 버튼 추가
- [ ] `table`, `th`, `td` 선택자에 `[통합]` 배지 표시
- [ ] 중앙 패널 조건부 렌더링: `x-show="tableMode"` / `x-show="!tableMode"`
- [ ] `_tab_style_table.html` include
- [ ] 선택자 클릭 핸들러에 `tableMode = false` 추가

**예상 변경량:** ~15줄

---

## 5. 파일 변경 목록

| 파일 경로 | 변경 유형 | 예상 라인 | 설명 |
|-----------|----------|-----------|------|
| `app/static/js/blogs/style-tab-presets.js` | 수정 | +80줄 | TABLE_PRESETS, HIDDEN_SELECTORS, SAMPLE_CONTENT 확장 |
| `app/static/js/blogs/style-tab-css-utils.js` | 수정 | +30줄 | HIDDEN_SELECTORS CSS 생성, 미리보기 테이블 기본 스타일 조정 |
| `app/static/js/blogs/style-tab.js` | 수정 | +100줄 | tableMode, tableConfig, 동기화 함수, 프리셋 적용 |
| `app/templates/blogs/settings/_tab_style_table.html` | **신규** | ~250줄 | 테이블 전용 편집 패널 HTML |
| `app/templates/blogs/settings/_tab_style.html` | 수정 | +15줄 | 버튼 추가, 조건부 패널 전환, [통합] 배지 |

**변경하지 않는 파일:**
| 파일 | 이유 |
|------|------|
| `app/models/blog.py` | `style_config` JSON이 이미 범용 구조 |
| `app/schemas/blog_settings.py` | `Dict[str, Dict[str, str]]` 타입이 이미 호환 |
| `app/routers/blog_settings.py` | API 변경 없음 |
| `app/services/blog_settings_service.py` | `generate_css()`가 이미 모든 선택자 처리 |
| DB 마이그레이션 | 필요 없음 |

---

## 6. 테스트 계획

### 6.1 프리셋 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| 각 프리셋(5종) 클릭 | 해당 CSS가 styleConfig에 정확히 반영, 미리보기 갱신 |
| 프리셋 적용 후 개별 속성 수정 | 수정된 속성만 변경, 나머지 프리셋 값 유지 |
| 프리셋 적용 후 다른 프리셋 적용 | 이전 프리셋 완전 교체 |

### 6.2 테두리 빠른 선택 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| "없음" 선택 | table/th/td에서 border-style: none |
| "전체" 선택 | 모든 셀에 동일한 border |
| "가로선만" 선택 | top/bottom만 border, left/right 없음 |
| "세로선만" 선택 | left/right만 border, top/bottom 없음 |
| "외곽선만" 선택 | table에만 border, 내부 셀은 border 없음 |
| 색상/두께/스타일 변경 | 실시간 미리보기 반영 |

### 6.3 헤더/데이터 셀 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| th 배경색 변경 | 미리보기 헤더 배경 변경 |
| th 프리셋 팔레트 클릭 | 해당 색상 즉시 적용 |
| td 패딩 슬라이더 조작 | 실시간 패딩 변경 반영 |
| 컬러 피커와 hex 입력 동기화 | 양쪽 모두 즉시 반영 |

### 6.4 Zebra Striping 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| 토글 ON | `tr:nth-child(even/odd)` 키 생성, 미리보기 반영 |
| 토글 OFF | 해당 키 삭제, 미리보기에서 제거 |
| 좌측 선택자 목록 확인 | `tr:nth-child()` 선택자가 표시되지 않음 |
| 짝수/홀수 색상 변경 | 미리보기 즉시 반영 |
| 저장 후 재로드 | Zebra 설정이 정확히 복원됨 |

### 6.5 양방향 동기화 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| 테이블 UI에서 수정 → 범용 편집기에서 확인 | styleConfig 값 일치 |
| 범용 편집기에서 th 수정 → 테이블 UI 진입 | 수정된 값 반영 |
| 테이블 UI에서 수정 → CSS 코드 패널 확인 | 생성된 CSS에 반영 |
| 테이블 UI에서 수정 → 저장 → 재로드 | 모든 값 정확히 복원 |

### 6.6 레이아웃 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| 너비 auto/100%/custom 전환 | table width 속성 변경 |
| collapse/separate 전환 | border-collapse 변경, separate 시 spacing 입력 활성 |
| border-spacing 입력 | separate 모드에서만 적용 |

### 6.7 기존 기능 회귀 테스트
| 시나리오 | 예상 결과 |
|---------|----------|
| 기존 프리셋(default/minimal/modern) 적용 | 기존과 동일하게 동작 |
| 비-테이블 선택자(h1, p 등) 편집 | 기존과 동일하게 동작 |
| 전체 초기화 | 테이블 설정 포함 모두 초기화 |
| CSS 코드 복사 | Zebra, 테이블 레이아웃 CSS 포함 |

---

## 7. 리스크 및 고려사항

### 7.1 Tailwind 동적 클래스
- **리스크**: Tailwind는 빌드 타임에 사용된 클래스만 포함. 동적으로 생성된 클래스는 누락될 수 있음.
- **대응**: 테이블 편집 패널에서 사용하는 모든 Tailwind 클래스는 정적으로 HTML에 존재하므로 문제 없음. `safelist`에 추가할 필요 없음. 컬러 피커 값은 inline style이 아닌 `styleConfig` 데이터로 처리하므로 Tailwind와 무관.

### 7.2 양방향 동기화 엣지 케이스
- **리스크**: 범용 편집기에서 테이블 속성을 부분적으로만 수정한 경우 `borderPreset` 역추론 실패 가능.
- **대응**: `syncTableConfigFromStyleConfig()`에서 정확히 매칭되는 borderPreset이 없으면 `'custom'`으로 설정. UI에 "사용자 정의" 상태로 표시.

### 7.3 미리보기 테이블 행 수
- **리스크**: 현재 샘플 테이블이 헤더 1행 + 데이터 1행뿐이라 Zebra 효과 확인 불가.
- **대응**: `SAMPLE_CONTENT`의 테이블을 헤더 1행 + 데이터 4행으로 확장.

```html
<table>
    <thead><tr><th>항목</th><th>값</th><th>비고</th></tr></thead>
    <tbody>
        <tr><td>데이터 A1</td><td>100</td><td>정상</td></tr>
        <tr><td>데이터 A2</td><td>200</td><td>주의</td></tr>
        <tr><td>데이터 A3</td><td>150</td><td>정상</td></tr>
        <tr><td>데이터 A4</td><td>300</td><td>확인</td></tr>
    </tbody>
</table>
```

### 7.4 기존 프리셋 호환성
- **리스크**: 기존 `STYLE_PRESETS.modern`에 이미 `table`, `th` 키가 있음. 테이블 프리셋과 범용 프리셋 적용 순서에 따른 충돌.
- **대응**: 범용 프리셋(`applyPreset`)은 기존 로직 유지. 테이블 프리셋(`applyTablePreset`)은 `table`, `th`, `td`, `tr:nth-child(*)` 키만 덮어씀 (다른 선택자 보존). 두 프리셋 시스템은 독립적으로 동작.

### 7.5 `generatePreviewHtml()` 기본 스타일 충돌
- **리스크**: 현재 `generatePreviewHtml()`에 하드코딩된 기본 테이블 스타일(`th, td { border: 1px solid #ddd; padding: 8px; }`)이 사용자 설정과 충돌.
- **대응**: 기본 스타일을 최소화하거나, 사용자 CSS가 기본 스타일보다 후순위에 배치되어 자연스럽게 오버라이드되도록 순서 조정. 테이블 모드 활성 시 기본 테이블 스타일 제거 검토.

### 7.6 성능
- **리스크**: 테이블 UI 컨트롤 변경마다 `syncStyleConfigFromTable()` + CSS 재생성 + 미리보기 갱신.
- **대응**: 기존 `debounceUpdatePreview()` (150ms) 활용. 슬라이더 등 연속 입력에도 150ms 디바운스로 충분.

---

## 부록: 전체 ASCII 레이아웃

### 테이블 편집 패널 전체 배치

```
┌─────────────────────────────────────────────────────────┐
│  스타일 편집: 테이블 설정                    [전체 초기화] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ── 프리셋 ──────────────────────────────────            │
│  [심플] [모던] [클래식] [미니멀] [다크]                    │
│                                                         │
│  ── 테두리 ──────────────────────────────────            │
│  빠른 선택: [없음] [전체] [가로선] [세로선] [외곽선]       │
│  색상: [■ #e5e7eb]  두께: [1] px  스타일: [solid ▼]      │
│                                                         │
│  ── 헤더 (th) ───────────────────────────────            │
│  배경: [■ #f3f4f6]  글자: [■ #1f2937]                    │
│  팔레트: [■][■][■][■][■][■][■][■]                        │
│  굵기: [Semi Bold ▼]                                    │
│  패딩: 컴팩트(6) ──●── 기본(10) ──── 여유(14)            │
│                                                         │
│  ── 데이터 셀 (td) ──────────────────────────            │
│  배경: [■ transparent]  글자: [■ #374151]                │
│  패딩: 컴팩트(6) ────●── 기본(10) ──── 여유(14)          │
│                                                         │
│  ── 행 교대 색상 ─────────────────── [●━ ON] ──          │
│  짝수 행: [■ #f9fafb]                                    │
│  홀수 행: [■ #ffffff ]                                    │
│                                                         │
│  ── 테이블 레이아웃 ─────────────────────────            │
│  너비: (○)auto  (●)100%  (○)직접입력 [    ]              │
│  테두리 합침: [●━ collapse]                               │
│  테두리 간격: [0] px (separate 모드에서만)                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 선택자 패널 (테이블 설정 버튼 + [통합] 배지)

```
┌──────────────────┐
│  선택자 목록       │
├──────────────────┤
│ ┌──────────────┐ │
│ │  테이블 설정   │ │  ← 파란색 배경 버튼
│ └──────────────┘ │
├──────────────────┤
│  h1              │
│  h2              │
│  h3              │
│  h4              │
│  h5              │
│  p               │
│  a (일반 링크)    │
│  a (버튼 링크)    │
│  li              │
│  ul              │
│  ol              │
│  table  [통합] ● │  ← 보라색 "통합" 배지 + 초록 점(스타일 있음)
│  th     [통합] ● │
│  td     [통합] ● │
│  blockquote      │
└──────────────────┘
```

### 테두리 빠른 선택 버튼 시각화

```
[없음]     [전체]     [가로선]   [세로선]   [외곽선]
 ┌───┐     ┌───┐     ┌───┐     ┌─┬─┐     ┌───┐
 │   │     ├───┤     ────      │ │ │     │   │
 │   │     ├───┤     ────      │ │ │     │   │
 └───┘     └───┘     └───┘     └─┴─┘     └───┘
```
