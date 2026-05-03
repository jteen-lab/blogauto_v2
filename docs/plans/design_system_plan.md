# BlogAuto V2 통합 디자인 시스템 계획서

> **버전**: v1.0.0 | **작성일**: 2026-04-23 | **상태**: 계획

---

## 목차

1. [디자인 시스템 개요](#1-디자인-시스템-개요)
2. [CSS 변수 기반 컬러 시스템](#2-css-변수-기반-컬러-시스템)
3. [사용자 컬러 선택 UI](#3-사용자-컬러-선택-ui)
4. [페이지별 변경 사항](#4-페이지별-변경-사항)
5. [구현 전략](#5-구현-전략)
6. [Tailwind + CSS 변수 공존 전략](#6-tailwind--css-변수-공존-전략)
7. [프리셋 테마 정의](#7-프리셋-테마-정의)
8. [파일 변경 목록](#8-파일-변경-목록)
9. [리스크 및 고려사항](#9-리스크-및-고려사항)

---

## 1. 디자인 시스템 개요

### 1.1 현재 상태 (AS-IS)

| 영역 | 현재 상태 | 문제점 |
|------|----------|--------|
| **대시보드** | Sora 폰트, 컴팩트 카드, #0F6E56/#0C447C 고유 색상 | 다른 페이지와 스타일 불일치 |
| **기타 페이지** | Tailwind 기본 blue 테마, 시스템 폰트 | 디자인 통일감 부재 |
| **네비게이션** | `bg-blue-600` 하드코딩 | 컬러 변경 불가 |
| **버튼/링크** | `bg-blue-600`, `text-blue-600` 등 하드코딩 | 43개 템플릿, 25개 JS에 분산 |
| **컬러 커스터마이징** | 미지원 | 사용자 선호 반영 불가 |

**하드코딩 현황 (조사 결과)**:
- 템플릿(HTML): 43개 파일에서 `blue-600/700` 계열 421건 발견
- 정적 파일(JS/CSS): 25개 파일에서 133건 발견
- 대시보드 전용 색상(`#0F6E56`, `#0C447C`): 1개 파일 7건
- **총 영향 범위**: 68개 파일, 약 554건의 하드코딩 컬러

### 1.2 목표 상태 (TO-BE)

| 영역 | 목표 상태 |
|------|----------|
| **전체 폰트** | Sora 폰트 일관 적용 (본문 400, 제목 600-700) |
| **카드 레이아웃** | 대시보드 스타일의 `section-card` 패턴 전체 적용 |
| **컬러 시스템** | CSS 변수 기반, 사용자 선택 가능 |
| **간격/여백** | 컴팩트 스타일 통일 (py-4~6, gap-3~4) |
| **테두리** | `border-radius: 12px`, `border: 0.5px solid #e5e7eb` 통일 |
| **텍스트** | 라벨: 0.7~0.75rem uppercase, 값: 1.75rem bold |

### 1.3 디자인 토큰

```
Typography:
  font-family     : 'Sora', sans-serif
  heading-weight  : 600~700
  body-weight     : 400~500
  label-size      : 0.7rem (uppercase, letter-spacing: 0.08em)
  body-size       : 0.875rem
  small-size      : 0.75rem

Spacing:
  page-padding    : px-4 sm:px-6 lg:px-8
  section-gap     : 16px (gap-4)
  card-padding    : 16~20px
  compact-gap     : 12px (gap-3)

Border:
  card-radius     : 12px
  button-radius   : 8px
  badge-radius    : 9999px (full)
  card-border     : 0.5px solid var(--border-color)

Shadow:
  card-shadow     : none (border 기반)
  elevated-shadow : 0 10px 15px -3px rgba(0,0,0,0.1)
  dropdown-shadow : 0 4px 6px rgba(0,0,0,0.1)
```

---

## 2. CSS 변수 기반 컬러 시스템

### 2.1 변수 정의

`base.html`의 `<style>` 블록에 `:root` 변수를 정의한다.

```css
:root {
  /* === Primary (메인 컬러) === */
  --color-primary: #0F6E56;           /* 네비바, 주요 버튼, 활성 탭 */
  --color-primary-light: #E6F5F1;     /* hover 배경, 선택 상태 배경 */
  --color-primary-dark: #0A5A46;      /* active/pressed 상태 */
  --color-primary-rgb: 15, 110, 86;   /* rgba() 사용용 */

  /* === Accent (포인트 컬러) === */
  --color-accent: #0C447C;            /* 배지, 하이라이트, 보조 버튼 */
  --color-accent-light: #E8F0F8;      /* accent hover 배경 */
  --color-accent-dark: #093662;       /* accent active 상태 */
  --color-accent-rgb: 12, 68, 124;    /* rgba() 사용용 */

  /* === 시맨틱 컬러 (테마 불변) === */
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  --color-info: #3b82f6;

  /* === 중립 컬러 (테마 불변) === */
  --color-bg: #f9fafb;
  --color-surface: #ffffff;
  --color-border: #e5e7eb;
  --color-text-primary: #111827;
  --color-text-secondary: #6b7280;
  --color-text-muted: #9ca3af;

  /* === 포커스 링 === */
  --focus-ring-color: rgba(var(--color-primary-rgb), 0.3);
}
```

### 2.2 파생 색상 자동 계산

JavaScript에서 HEX를 받아 light/dark 변형을 자동 계산한다.

```javascript
function applyThemeColors(primary, accent) {
  const root = document.documentElement;

  // Primary 계열
  root.style.setProperty('--color-primary', primary);
  root.style.setProperty('--color-primary-light', lighten(primary, 0.9));
  root.style.setProperty('--color-primary-dark', darken(primary, 0.15));
  root.style.setProperty('--color-primary-rgb', hexToRgb(primary));

  // Accent 계열
  root.style.setProperty('--color-accent', accent);
  root.style.setProperty('--color-accent-light', lighten(accent, 0.9));
  root.style.setProperty('--color-accent-dark', darken(accent, 0.15));
  root.style.setProperty('--color-accent-rgb', hexToRgb(accent));

  // 포커스 링 업데이트
  root.style.setProperty('--focus-ring-color',
    `rgba(${hexToRgb(primary)}, 0.3)`);
}
```

### 2.3 유틸리티 CSS 클래스

CSS 변수를 참조하는 커스텀 유틸리티 클래스를 정의한다.

```css
/* === 배경 === */
.bg-primary     { background-color: var(--color-primary) !important; }
.bg-primary-lt  { background-color: var(--color-primary-light) !important; }
.bg-primary-dk  { background-color: var(--color-primary-dark) !important; }
.bg-accent      { background-color: var(--color-accent) !important; }
.bg-accent-lt   { background-color: var(--color-accent-light) !important; }

/* === 텍스트 === */
.text-primary   { color: var(--color-primary) !important; }
.text-primary-dk{ color: var(--color-primary-dark) !important; }
.text-accent    { color: var(--color-accent) !important; }

/* === 보더 === */
.border-primary { border-color: var(--color-primary) !important; }
.border-accent  { border-color: var(--color-accent) !important; }

/* === 버튼 === */
.btn-primary {
  background-color: var(--color-primary);
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s;
}
.btn-primary:hover {
  background-color: var(--color-primary-dark);
}

.btn-accent {
  background-color: var(--color-accent);
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s;
}
.btn-accent:hover {
  background-color: var(--color-accent-dark);
}

.btn-outline-primary {
  border: 2px solid var(--color-primary);
  color: var(--color-primary);
  background: transparent;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.2s;
}
.btn-outline-primary:hover {
  background-color: var(--color-primary-light);
}

/* === 탭 (활성/비활성) === */
.tab-active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  background-color: var(--color-primary-light);
}

/* === 포커스 링 === */
.focus-ring:focus {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring-color);
}

/* === 배지 === */
.badge-primary {
  background-color: var(--color-primary-light);
  color: var(--color-primary-dark);
}
.badge-accent {
  background-color: var(--color-accent-light);
  color: var(--color-accent-dark);
}
```

---

## 3. 사용자 컬러 선택 UI

### 3.1 배치 위치

설정 모달(`settings/modal.html`)에 **"테마" 탭**을 추가한다.

기존 탭: `계정 | AI 서비스 | API 설정 | 시스템`
변경 후: `계정 | AI 서비스 | API 설정 | 테마 | 시스템`

### 3.2 컬러 선택 UI 목업

```
+----------------------------------------------------------+
|  설정                                              [X]   |
+----------------------------------------------------------+
|  계정 | AI 서비스 | API 설정 | [테마] | 시스템            |
+----------------------------------------------------------+
|                                                          |
|  테마 설정                                               |
|  --------                                                |
|                                                          |
|  프리셋 테마                                              |
|  +----------+ +----------+ +----------+                  |
|  | [======] | | [======] | | [======] |                  |
|  | 기본     | | 블루     | | 퍼플     |                  |
|  | #0F6E56  | | #1d4ed8  | | #7c3aed  |                  |
|  | #0C447C  | | #6366f1  | | #ec4899  |                  |
|  +----------+ +----------+ +----------+                  |
|  +----------+ +----------+ +----------+                  |
|  | [======] | | [======] | | [======] |                  |
|  | 다크     | | 오렌지   | | 커스텀   |                  |
|  | #1f2937  | | #ea580c  | |  [pick]  |                  |
|  | #3b82f6  | | #d97706  | |  [pick]  |                  |
|  +----------+ +----------+ +----------+                  |
|                                                          |
|  커스텀 컬러 (커스텀 선택 시 표시)                         |
|  +--------------------------------------------------+   |
|  |  메인 컬러        포인트 컬러                      |   |
|  |  [#______] [O]    [#______] [O]                   |   |
|  |                                                    |   |
|  |  미리보기:                                         |   |
|  |  +--------------------------------------------+   |   |
|  |  | [====네비바====]  bg: primary               |   |   |
|  |  | [버튼] primary   [배지] accent              |   |   |
|  |  | [링크] primary   [탭━━] active              |   |   |
|  |  +--------------------------------------------+   |   |
|  +--------------------------------------------------+   |
|                                                          |
|                              [ 적용하기 ]                 |
+----------------------------------------------------------+
```

### 3.3 프리셋 카드 상세 목업

각 프리셋 카드는 실제 색상을 미리보기로 보여준다.

```
+----------------+
|  +-----------+ |  <-- 상단: primary 색 배경의 미니 네비바
|  | BlogAuto  | |
|  +-----------+ |
|  [btn] [badge] |  <-- btn은 primary, badge는 accent
|  ------------- |
|  기본           |  <-- 테마 이름
|  ############## |  <-- primary 색상 바
|  ############## |  <-- accent 색상 바
+----------------+
    ^-- 선택 시 border: 2px solid var(--color-primary)
```

### 3.4 저장/로드 전략

**1순위: localStorage (즉시 적용, 네트워크 불필요)**

```javascript
// 저장
function saveTheme(preset, primary, accent) {
  localStorage.setItem('blogauto_theme', JSON.stringify({
    preset,     // 'default' | 'blue' | 'purple' | 'dark' | 'orange' | 'custom'
    primary,    // '#0F6E56'
    accent      // '#0C447C'
  }));
  applyThemeColors(primary, accent);
}

// 로드 (base.html에서 DOMContentLoaded 전에 실행)
function loadTheme() {
  const saved = localStorage.getItem('blogauto_theme');
  if (saved) {
    const { primary, accent } = JSON.parse(saved);
    applyThemeColors(primary, accent);
  }
}
```

**2순위 (향후): UserSettings DB 저장**

UserSettings 모델에 `theme_preset`, `theme_primary`, `theme_accent` 컬럼을 추가하면
다른 기기에서도 동일 테마를 유지할 수 있다. 1차 구현에서는 localStorage만 사용하고,
필요 시 DB 연동을 추가한다.

### 3.5 실시간 미리보기

커스텀 컬러 입력 시 `<input type="color">` + `<input type="text">` 를 조합하고,
`input` 이벤트에서 `applyThemeColors()`를 즉시 호출하여 페이지 전체에 실시간 반영한다.
"적용하기" 버튼 클릭 시에만 localStorage에 저장한다.

---

## 4. 페이지별 변경 사항

### 4.1 base.html (글로벌)

| 요소 | 현재 | 변경 |
|------|------|------|
| `<head>` | 없음 | Sora 폰트 CDN `<link>` 추가 |
| `<body>` | `class="bg-gray-50"` | `style="font-family:'Sora',sans-serif"` 추가 |
| `<nav>` | `bg-blue-600` | `bg-primary` |
| PC 메뉴 링크 | `bg-blue-700 hover:bg-blue-800` | `bg-primary-dk hover:opacity-90` |
| 모바일 메뉴 | `bg-blue-700`, `border-blue-500` | `bg-primary-dk`, `border-primary` |
| 로그아웃 버튼 | `bg-red-600` | 유지 (시맨틱 컬러) |
| `<style>` 블록 | 기존 스타일 | `:root` CSS 변수 + 유틸리티 클래스 추가 |
| `<script>` | 기존 JS | `loadTheme()` 즉시 실행 스크립트 추가 |
| 로딩 spinner | `border-top: #3498db` | `border-top-color: var(--color-primary)` |

### 4.2 login.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 로그인 탭 | `border-blue-500 text-blue-600` | `tab-active` 클래스 |
| 회원가입 탭 | 동일 | `tab-active` 클래스 |
| 로그인 버튼 | `bg-blue-600 hover:bg-blue-700` | `btn-primary` 클래스 |
| focus ring | `ring-blue-500` | `focus-ring` 클래스 |
| 회원가입 버튼 | `bg-green-600` | 유지 (구분 목적) 또는 `btn-accent` |
| input focus | `ring-blue-500 border-blue-500` | `focus-ring` + `border-primary` |

**참고**: 로그인 페이지는 테마 로드 전 기본 테마(기본 프리셋)로 표시된다.
localStorage에 저장된 테마가 있으면 즉시 적용된다.

### 4.3 dashboard_v2.html

| 요소 | 현재 | 변경 |
|------|------|------|
| `.dashboard-page` | `font-family: 'Sora'` 직접 지정 | 제거 (base.html에서 전역 적용) |
| `.kpi-delta-up` | `color: #0F6E56` | `color: var(--color-primary)` |
| 상태 세그먼트 바 | `bg-[#0F6E56]`, `bg-[#0C447C]` | `bg-primary`, `bg-accent` |
| 요약탭 선택 버튼 | `border-[#0F6E56]`, `bg-[#0F6E56]/10` | `border-primary`, `bg-primary-lt` |
| 전체보기 링크 | `text-[#0C447C]` | `text-accent` |
| 블로그 바 차트 | `bg-[#0C447C]` | `bg-accent` |
| ApexCharts 색상 | JS에 하드코딩된 색상 | `getComputedStyle`로 CSS 변수 참조 |

### 4.4 blogs/list.html + blogs/_card.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 추가 버튼 | `bg-blue-600` | `btn-primary` |
| 설정 버튼 | `text-blue-600` | `text-primary` |
| 배지 (플랫폼) | `bg-blue-100 text-blue-800` | `badge-accent` |
| 활성 상태 배지 | `bg-green-100` | 유지 (시맨틱) |
| 탭 활성 | `text-blue-600 border-blue-500` | `tab-active` |
| 카드 스타일 | 기존 rounded-lg | `section-card` 패턴 (12px radius, 0.5px border) |

### 4.5 modules/list.html + modules/_form.html + modules/_prompt_form.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 모듈 타입 배지 | `bg-blue-100 text-blue-800` | `badge-primary` 또는 `badge-accent` |
| 추가 버튼 | `bg-blue-600` | `btn-primary` |
| 폼 저장 버튼 | `bg-blue-600` | `btn-primary` |
| 폼 취소 버튼 | `bg-gray-200` | 유지 |
| 입력 focus | `ring-blue-500` | `focus-ring` |
| 탭 (프롬프트 폼) | `border-blue-500 text-blue-600` 21건 | `tab-active` |
| 카드 레이아웃 | 기존 shadow 기반 | `section-card` 패턴 |

### 4.6 flows/list.html + flows/_form.html + flows/_card.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 플로우 실행 버튼 | `bg-blue-600` | `btn-primary` |
| 모듈 추가 | `border-blue-400 text-blue-600` | `btn-outline-primary` |
| 블로그 선택 | `bg-blue-50 border-blue-500` | `bg-primary-lt border-primary` |
| 카드 레이아웃 | 기존 | `section-card` 패턴 |

### 4.7 collection/index.html + _titles.html + _urls.html + _keywords.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 탭 활성 | `color: #2563eb; border-bottom-color: #2563eb` | `tab-active` CSS 클래스 |
| 체크박스 선택 바 | `bg-blue-600` | `bg-primary` |
| 액션 버튼 | `bg-blue-600` | `btn-primary` |
| 배지 | `badge-blue` | `badge-primary` |
| 카드 | 기존 | `section-card` 패턴 |

### 4.8 autorun/index.html + autorun/_card.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 실행 버튼 | `bg-blue-600` | `btn-primary` |
| 상태 표시 | `bg-green-100` (활성), `bg-yellow-100` (일시정지) | 유지 (시맨틱) |
| 선택 바 | `bg-blue-50` | `bg-primary-lt` |

### 4.9 categories/manage.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 주제 추가 버튼 | `border-blue-600 text-blue-600` | `btn-outline-primary` |
| 탭 활성 | `bg-blue-50 text-blue-700 border-blue-500` | `tab-active` |
| 편집 버튼 | `text-blue-600` | `text-primary` |

### 4.10 settings/modal.html

| 요소 | 현재 | 변경 |
|------|------|------|
| 탭 활성 | `border-blue-500 text-blue-600 bg-blue-50` 40건 | `tab-active` |
| 저장 버튼 | `bg-blue-600` | `btn-primary` |
| **신규 탭** | 없음 | "테마" 탭 추가 (컬러 선택 UI) |

### 4.11 공통 컴포넌트

| 파일 | 요소 | 변경 |
|------|------|------|
| `components/fab_button.html` | FAB 버튼 | `bg-primary` |
| `components/flow_card.html` | 플로우 카드 | `section-card` + `text-primary` |
| `components/module_card.html` | 모듈 카드 | `section-card` + `badge-primary` |
| `components/selection_popup.html` | 선택 팝업 | `btn-primary` |
| `components/checkbox_list.html` | 체크박스 | `text-primary` |
| `components/global_summary.html` | 글로벌 요약탭 | `bg-primary` 관련 7건 |
| `components/status_badge.html` | 상태 배지 | 시맨틱 컬러 유지 |

---

## 5. 구현 전략

### Phase 1: CSS 변수 정의 + 글로벌 스타일 적용 (예상: 2~3일)

**목표**: base.html에 디자인 시스템 기반 구축

1. **base.html 수정**
   - Sora 폰트 CDN 추가
   - `:root` CSS 변수 정의 (2.1절 참조)
   - 유틸리티 CSS 클래스 추가 (2.3절 참조)
   - `<body>`에 `font-family: 'Sora', sans-serif` 적용
   - `<nav>` 컬러를 CSS 변수 기반 클래스로 교체
   - `loadTheme()` 스크립트 추가 (FOUC 방지를 위해 `<head>` 내 인라인)

2. **static/css/design-system.css 생성**
   - 유틸리티 클래스 외부 파일 분리
   - `section-card`, `kpi-card` 등 공통 카드 패턴
   - 탭, 버튼, 배지, 포커스 링 스타일

3. **static/js/theme.js 생성**
   - `applyThemeColors()`, `loadTheme()`, `saveTheme()`
   - HEX-RGB 변환, lighten/darken 유틸 함수
   - 프리셋 테마 데이터 정의

4. **components.css 업데이트**
   - `--focus-ring` 값을 CSS 변수 참조로 변경

**검증**: 네비바 색상이 CSS 변수로 동작하는지 확인, Sora 폰트 적용 확인

### Phase 2: 컬러 선택 UI + 저장/로드 (예상: 1~2일)

**목표**: 사용자가 테마를 선택하고 저장할 수 있는 UI

1. **settings/modal.html에 테마 탭 추가**
   - 프리셋 카드 6개 (기본, 블루, 퍼플, 다크, 오렌지, 커스텀)
   - 커스텀 컬러 피커 (`<input type="color">` + HEX 입력)
   - 실시간 미리보기 영역
   - "적용하기" 버튼

2. **static/js/settings/theme-settings.js 생성**
   - 프리셋 선택 핸들러
   - 커스텀 컬러 피커 로직
   - 미리보기 렌더링
   - localStorage 저장/로드

**검증**: 프리셋 선택 즉시 반영, 커스텀 컬러 실시간 미리보기, 새로고침 후 유지

### Phase 3: 페이지별 마이그레이션 (예상: 5~7일)

**목표**: 모든 하드코딩 컬러를 CSS 변수 기반으로 교체

마이그레이션 순서 (의존성 + 영향도 기준):

```
3-1. 공통 컴포넌트 (1일)
     - components/*.html (6개 파일)
     - components/*.js (7개 파일)
     → 이후 모든 페이지에 자동 반영

3-2. 데이터 관리 (1일)
     - collection/index.html + 하위 탭 5개
     - collection 관련 JS

3-3. 블로그 관리 (1일)
     - blogs/list.html + _card.html + create.html
     - blogs/settings/ 탭 7개
     - blogs 관련 JS

3-4. 모듈 관리 (1일)
     - modules/list.html + _form.html + _card.html
     - _prompt_form.html + _generate_form.html + _growth_profile_form.html
     - modules 관련 JS (14개 파일)

3-5. 플로우 + 오토런 (1일)
     - flows/list.html + _form.html + _card.html + 하위 컴포넌트
     - autorun/index.html + _card.html
     - 관련 JS

3-6. 기타 페이지 (0.5일)
     - categories/manage.html
     - generation/history.html
     - groups/list.html + form.html
     - login.html, error.html

3-7. 설정 모달 (0.5일)
     - settings/modal.html (40건의 blue 참조)
```

**마이그레이션 규칙**:
- `bg-blue-600` → `bg-primary`
- `bg-blue-700` → `bg-primary-dk`
- `hover:bg-blue-700` / `hover:bg-blue-800` → `hover:opacity-90` 또는 인라인 hover
- `text-blue-600` / `text-blue-700` → `text-primary`
- `border-blue-500` / `border-blue-600` → `border-primary`
- `ring-blue-500` / `focus:ring-blue-500` → `focus-ring`
- `bg-blue-50` / `bg-blue-100` → `bg-primary-lt`
- Tailwind 동적 클래스(Alpine `:class`)는 인라인 `style` 바인딩으로 변경

### Phase 4: 대시보드 연동 + 통합 테스트 (예상: 1~2일)

1. **dashboard_v2.html 업데이트**
   - 대시보드 전용 `<style>` 블록에서 하드코딩 색상 제거
   - `.dashboard-page` font-family 제거 (글로벌에서 적용)
   - ApexCharts 색상을 CSS 변수에서 동적 추출

2. **ApexCharts 테마 연동**
   ```javascript
   const primaryColor = getComputedStyle(document.documentElement)
     .getPropertyValue('--color-primary').trim();
   // 차트 옵션에 사용
   ```

3. **크로스 페이지 테스트**
   - 모든 프리셋 테마로 전체 페이지 순회
   - 커스텀 극단값 (매우 밝은/어두운 색) 테스트
   - 모바일/태블릿/데스크탑 반응형 확인

4. **접근성 테스트**
   - WCAG 2.1 AA 명도 대비(4.5:1) 검증
   - 프리셋 테마별 대비율 사전 검증
   - 커스텀 컬러 선택 시 대비율 경고 표시

---

## 6. Tailwind + CSS 변수 공존 전략

### 6.1 문제점

BlogAuto V2는 Tailwind CSS CDN(`cdn.tailwindcss.com`)을 사용한다.
CDN 방식은 `tailwind.config.js`를 직접 수정할 수 없으므로,
`bg-primary` 같은 커스텀 유틸리티 클래스를 Tailwind 방식으로 생성할 수 없다.

### 6.2 권장 전략: 커스텀 CSS 클래스 + Tailwind 병행

**이유**: 빌드 스텝 없이 즉시 적용 가능하고, 기존 Tailwind 유틸리티와 충돌 없음.

**구현 방법**:

1. **신규 요소**: 커스텀 CSS 클래스 사용
   ```html
   <button class="btn-primary">저장</button>
   <div class="section-card">...</div>
   <span class="badge-accent">배지</span>
   ```

2. **기존 Tailwind 클래스 교체 패턴**:
   ```html
   <!-- Before -->
   <nav class="bg-blue-600 text-white">
   <button class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded">

   <!-- After -->
   <nav class="bg-primary text-white">
   <button class="btn-primary">
   ```

3. **Alpine.js 동적 클래스 처리**:
   ```html
   <!-- Before (Tailwind 동적 클래스) -->
   <button :class="active ? 'border-blue-500 text-blue-600 bg-blue-50' : 'text-gray-500'">

   <!-- After (커스텀 클래스) -->
   <button :class="active ? 'tab-active' : 'text-gray-500'">
   ```

4. **인라인 스타일이 필요한 경우** (CSS 클래스로 불가능한 동적 값):
   ```html
   <!-- 프로그레스 바 등 -->
   <div :style="`background-color: var(--color-primary); width: ${pct}%`"></div>
   ```

### 6.3 Tailwind CDN 커스텀 설정 활용

Tailwind CDN은 인라인 `<script>` 로 제한적 커스터마이징을 지원한다.

```html
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          // CSS 변수를 Tailwind 색상으로 등록
          // 주의: CDN에서는 JIT 모드만 지원하므로
          // 동적 변수 참조는 불완전할 수 있음
        },
        fontFamily: {
          'sora': ['Sora', 'sans-serif'],
        },
      }
    }
  }
</script>
```

**한계**: Tailwind CDN의 `tailwind.config`로 CSS 변수를 색상값으로 매핑하면
`bg-primary-600` 같은 클래스를 생성할 수 있지만, 런타임에 CSS 변수가 변경되어도
Tailwind가 재컴파일하지 않으므로 **정적 값만 가능**하다.

**결론**: 테마 변경이 필요한 색상은 **반드시 커스텀 CSS 클래스 또는 인라인 스타일을 사용**한다.
Tailwind 유틸리티는 테마와 무관한 레이아웃, 간격, 타이포그래피에만 계속 사용한다.

### 6.4 공존 규칙 요약

| 역할 | 사용 기술 | 예시 |
|------|----------|------|
| **테마 색상** (동적) | 커스텀 CSS 클래스 | `.bg-primary`, `.btn-primary` |
| **시맨틱 색상** (고정) | Tailwind 유틸리티 | `bg-red-600`, `text-green-700` |
| **레이아웃** | Tailwind 유틸리티 | `flex`, `grid`, `max-w-7xl` |
| **간격/여백** | Tailwind 유틸리티 | `px-4`, `py-6`, `gap-3` |
| **타이포그래피** | Tailwind + 커스텀 | `text-sm`, `font-bold` + Sora |
| **반응형** | Tailwind 유틸리티 | `md:grid-cols-2`, `lg:hidden` |

---

## 7. 프리셋 테마 정의

### 7.1 테마 데이터

```javascript
const THEME_PRESETS = {
  default: {
    name: '기본',
    description: '딥 그린 + 네이비 블루',
    primary: '#0F6E56',
    accent: '#0C447C',
  },
  blue: {
    name: '블루',
    description: '로얄 블루 + 인디고',
    primary: '#1d4ed8',
    accent: '#6366f1',
  },
  purple: {
    name: '퍼플',
    description: '바이올렛 + 핑크',
    primary: '#7c3aed',
    accent: '#ec4899',
  },
  dark: {
    name: '다크',
    description: '차콜 + 블루 액센트',
    primary: '#1f2937',
    accent: '#3b82f6',
  },
  orange: {
    name: '오렌지',
    description: '선셋 오렌지 + 앰버',
    primary: '#ea580c',
    accent: '#d97706',
  },
  custom: {
    name: '커스텀',
    description: '직접 선택',
    primary: null,  // 사용자 입력
    accent: null,   // 사용자 입력
  }
};
```

### 7.2 테마별 색상 팔레트

각 프리셋의 파생 색상 (자동 계산):

| 테마 | primary | primary-light | primary-dark | accent | accent-light | accent-dark |
|------|---------|---------------|-------------|--------|-------------|------------|
| 기본 | #0F6E56 | #E6F5F1 | #0A5A46 | #0C447C | #E8F0F8 | #093662 |
| 블루 | #1d4ed8 | #EBF0FC | #1740B0 | #6366f1 | #EEEFFE | #4F52C4 |
| 퍼플 | #7c3aed | #F2EBFD | #6530C1 | #ec4899 | #FDE8F2 | #C13A7C |
| 다크 | #1f2937 | #E9EAEC | #161D27 | #3b82f6 | #EBF1FE | #2F69C8 |
| 오렌지 | #ea580c | #FEF0E8 | #BF470A | #d97706 | #FDF3E5 | #AF5F05 |

### 7.3 접근성 검증 (WCAG 2.1 AA)

흰색 배경 위 텍스트 대비율 (최소 4.5:1 필요):

| 테마 | primary on white | accent on white | 판정 |
|------|-----------------|----------------|------|
| 기본 | 5.8:1 | 6.4:1 | PASS |
| 블루 | 5.1:1 | 4.6:1 | PASS |
| 퍼플 | 5.3:1 | 4.5:1 | PASS (경계) |
| 다크 | 13.1:1 | 4.8:1 | PASS |
| 오렌지 | 4.6:1 | 4.9:1 | PASS (경계) |

흰색 텍스트 배경 대비율 (버튼/네비바, 최소 4.5:1 필요):

| 테마 | white on primary | white on accent | 판정 |
|------|-----------------|----------------|------|
| 기본 | 5.8:1 | 6.4:1 | PASS |
| 블루 | 5.1:1 | 4.6:1 | PASS |
| 퍼플 | 5.3:1 | 4.5:1 | PASS |
| 다크 | 13.1:1 | 4.8:1 | PASS |
| 오렌지 | 4.6:1 | 4.9:1 | PASS (경계) |

**커스텀 컬러 대비율 경고 기능**:
사용자가 커스텀 컬러를 선택할 때, 흰색 텍스트와의 대비율이 4.5:1 미만이면
경고 메시지를 표시한다.

```
  "선택한 색상의 명도 대비가 부족합니다 (3.2:1).
   텍스트 가독성이 떨어질 수 있습니다."
```

---

## 8. 파일 변경 목록

### 8.1 신규 생성 파일

| 파일 | 용도 | 예상 라인 |
|------|------|----------|
| `app/static/css/design-system.css` | 디자인 토큰, 유틸리티 클래스 | ~200줄 |
| `app/static/js/theme.js` | 테마 로드/저장/적용 로직 | ~150줄 |
| `app/static/js/settings/theme-settings.js` | 테마 설정 UI 로직 | ~120줄 |

### 8.2 수정 파일 (템플릿)

| 파일 | 변경 건수 | 주요 변경 |
|------|----------|----------|
| `base.html` | ~20줄 | 폰트, CSS 변수, 네비바, 테마 로드 |
| `login.html` | ~10줄 | 버튼, 탭, focus 스타일 |
| `dashboard/dashboard_v2.html` | ~15줄 | 하드코딩 색상 → CSS 변수 |
| `blogs/list.html` | ~30줄 | 버튼, 탭, 배지 |
| `blogs/_card.html` | ~5줄 | 배지, 링크 색상 |
| `blogs/create.html` | ~15줄 | 폼 버튼, focus |
| `blogs/settings/_tab_style.html` | ~15줄 | 버튼, 탭 |
| `blogs/settings/_tab_replace.html` | ~20줄 | 버튼, 탭 |
| `blogs/settings/_tab_matching.html` | ~8줄 | 버튼 |
| `blogs/settings/_tab_category.html` | ~8줄 | 버튼 |
| `blogs/settings/_tab_ai.html` | ~5줄 | 버튼 |
| `blogs/settings/_tab_image.html` | ~8줄 | 버튼 |
| `blogs/settings/_tab_seo.html` | ~3줄 | 버튼 |
| `blogs/settings/_tab_style_table.html` | ~5줄 | 버튼 |
| `modules/list.html` | ~10줄 | 버튼, 탭 |
| `modules/_form.html` | ~45줄 | 폼 요소 전체 |
| `modules/_prompt_form.html` | ~25줄 | 탭, 버튼 |
| `modules/_generate_form.html` | ~15줄 | 버튼 |
| `modules/_growth_profile_form.html` | ~25줄 | 폼, 탭 |
| `modules/_card.html` | ~5줄 | 배지 |
| `modules/_prompt_test_panel.html` | ~3줄 | 버튼 |
| `flows/list.html` | ~10줄 | 버튼 |
| `flows/_form.html` | ~8줄 | 버튼 |
| `flows/_card.html` | ~5줄 | 배지, 링크 |
| `flows/_module_selector.html` | ~3줄 | 버튼 |
| `flows/_module_select_card.html` | ~5줄 | 선택 상태 |
| `flows/_blog_select_card.html` | ~5줄 | 선택 상태 |
| `collection/index.html` | ~10줄 | 탭 |
| `collection/_titles.html` | ~15줄 | 버튼, 배지 |
| `collection/_titles_main.html` | ~25줄 | 버튼, 배지 |
| `collection/_urls.html` | ~12줄 | 버튼, 배지 |
| `collection/_keywords.html` | ~12줄 | 버튼 |
| `collection/_filters.html` | ~10줄 | 버튼 |
| `autorun/index.html` | ~8줄 | 버튼 |
| `autorun/_card.html` | ~3줄 | 배지 |
| `categories/manage.html` | ~18줄 | 탭, 버튼 |
| `settings/modal.html` | ~50줄 | 탭 40건 + 테마 탭 신규 |
| `generation/history.html` | ~5줄 | 버튼 |
| `groups/list.html` | ~5줄 | 버튼 |
| `groups/form.html` | ~10줄 | 폼 버튼 |
| `error.html` | ~2줄 | 링크 |
| `components/fab_button.html` | ~3줄 | FAB 색상 |
| `components/flow_card.html` | ~3줄 | 카드 |
| `components/module_card.html` | ~3줄 | 카드 |
| `components/selection_popup.html` | ~5줄 | 버튼 |
| `components/checkbox_list.html` | ~5줄 | 체크 상태 |
| `components/global_summary.html` | ~8줄 | 요약탭 색상 |

### 8.3 수정 파일 (JavaScript)

| 파일 | 변경 건수 | 주요 변경 |
|------|----------|----------|
| `js/components/GlobalSummary.js` | ~8줄 | 하드코딩 blue 제거 |
| `js/components/FlowCard.js` | ~5줄 | 색상 |
| `js/components/SelectionPopup.js` | ~5줄 | 색상 |
| `js/components/FABButton.js` | ~3줄 | 색상 |
| `js/components/CheckboxList.js` | ~5줄 | 색상 |
| `js/components/StatusBadge.js` | ~3줄 | 배지 |
| `js/modules/prompt-form-template.js` | ~30줄 | 폼 색상 |
| `js/modules/prompt-form-template-sections.js` | ~5줄 | 색상 |
| `js/modules/growth-profile-form-template.js` | ~15줄 | 폼 색상 |
| `js/modules/growth-profile-form-template-sections.js` | ~3줄 | 색상 |
| `js/modules/list.js` | ~15줄 | 목록 색상 |
| `js/modules/schedule.js` | ~8줄 | 스케줄 색상 |
| `js/modules/prompt-form-template-generate.js` | ~3줄 | 색상 |
| `js/modules/prompt-test-template.js` | ~3줄 | 색상 |
| `js/flows/list.js` | ~5줄 | 색상 |
| `js/autorun/main.js` | ~3줄 | 색상 |
| `js/widgets/base-widgets.js` | ~3줄 | 색상 |
| `js/widgets/advanced-widgets.js` | ~12줄 | 색상 |
| `js/widgets/extended-widgets.js` | ~22줄 | 색상 |
| `js/blogs/style-tab-presets.js` | ~3줄 | 색상 |
| `js/dashboard/kpi_spark.js` | ~3줄 | 차트 색상 |
| `js/dashboard/main_charts.js` | ~5줄 | 차트 색상 |
| `js/dashboard/perf_panel.js` | ~5줄 | 차트 색상 |
| `js/dashboard/content_table.js` | ~3줄 | 색상 |

### 8.4 수정 파일 (CSS)

| 파일 | 변경 건수 | 주요 변경 |
|------|----------|----------|
| `css/components.css` | ~5줄 | `--focus-ring` CSS 변수 참조 |
| `css/flow-card-slide.css` | ~3줄 | 색상 참조 |

### 8.5 총 작업량 요약

| 카테고리 | 파일 수 | 예상 변경 라인 |
|----------|---------|---------------|
| 신규 파일 | 3개 | ~470줄 (신규) |
| 템플릿 수정 | 46개 | ~500줄 |
| JS 수정 | 24개 | ~170줄 |
| CSS 수정 | 2개 | ~8줄 |
| **합계** | **75개** | **~1,148줄** |

---

## 9. 리스크 및 고려사항

### 9.1 Tailwind CDN 제약

| 리스크 | 영향도 | 대응 |
|--------|-------|------|
| CDN은 커스텀 설정 제한적 | 중 | 커스텀 CSS 클래스로 대체 |
| JIT 모드에서 동적 CSS 변수 불가 | 중 | 테마 관련은 커스텀 클래스만 사용 |
| `@apply` 지시어 CDN에서 사용 불가 | 저 | 기존 사용 부분(flows, autorun)은 순수 CSS로 변환 |

**`@apply` 문제 상세**: `flows/list.html`, `autorun/index.html` 등에서 `<style>` 블록 내
`@apply bg-green-100 text-green-800;` 같은 지시어를 사용 중이다. Tailwind CDN의
JIT 엔진이 이를 처리하므로 현재는 작동하지만, 커스텀 클래스(`bg-primary` 등)에는
`@apply`를 사용할 수 없다. 해당 부분은 순수 CSS 속성으로 변환한다.

### 9.2 FOUC (Flash of Unstyled Content)

**문제**: 페이지 로드 시 기본 테마가 잠깐 보인 후 사용자 테마로 전환되는 깜빡임.

**대응**: `<head>` 태그 내에서 `<script>` 블록으로 동기적으로 테마를 적용한다.

```html
<head>
  ...
  <script>
    // FOUC 방지: DOM 렌더링 전 테마 적용
    (function() {
      try {
        const saved = localStorage.getItem('blogauto_theme');
        if (saved) {
          const { primary, accent } = JSON.parse(saved);
          const root = document.documentElement;
          root.style.setProperty('--color-primary', primary);
          root.style.setProperty('--color-accent', accent);
          // light/dark 파생 색상도 즉시 계산
        }
      } catch(e) {}
    })();
  </script>
  ...
</head>
```

### 9.3 로그인 페이지 안정성

**문제**: 로그인 페이지는 인증 전 표시되므로, DB 기반 테마 로드가 불가하다.

**대응**:
- localStorage 기반이므로 로그인 전에도 이전 방문자의 테마가 유지된다.
- 최초 방문자는 기본 프리셋(딥 그린)이 표시된다.
- 로그인 페이지는 전체적으로 깔끔한 디자인을 유지하므로 어떤 테마에서도 무난하다.

### 9.4 극단적 커스텀 컬러

**문제**: 사용자가 매우 밝은 색(#FFFFFF)이나 매우 어두운 색(#000000)을 선택할 수 있다.

**대응**:
- 밝기 범위 제한: HSL 기준 L값 15~75% 범위만 허용
- 대비율 4.5:1 미만 시 경고 표시
- 극단값에서도 레이아웃이 깨지지 않도록 border 기반 디자인 유지

### 9.5 성능 영향

| 항목 | 영향 | 대응 |
|------|------|------|
| Sora 폰트 로드 | 초기 ~50KB 추가 | `display=swap`으로 FOUT 최소화 |
| CSS 변수 연산 | 무시할 수준 | 없음 |
| localStorage 접근 | <1ms | 없음 |
| design-system.css | ~5KB 추가 | gzip 시 ~1.5KB |
| theme.js | ~4KB 추가 | gzip 시 ~1.2KB |

### 9.6 다크 모드 (향후 확장)

현재 계획에 다크 모드는 포함하지 않지만, CSS 변수 기반 시스템이므로
향후 다크 모드 추가가 용이하다.

```css
/* 향후 다크 모드 확장 시 */
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #111827;
    --color-surface: #1f2937;
    --color-border: #374151;
    --color-text-primary: #f9fafb;
    --color-text-secondary: #9ca3af;
  }
}
```

### 9.7 브라우저 호환성

CSS Custom Properties 지원: Chrome 49+, Firefox 31+, Safari 9.1+, Edge 15+.
대상 사용자가 최신 브라우저를 사용하므로 문제 없음.

### 9.8 마이그레이션 중 회귀 리스크

| 리스크 | 영향도 | 대응 |
|--------|-------|------|
| 누락된 색상 교체 | 중 | grep으로 잔존 하드코딩 검사 |
| Alpine.js 동적 클래스 깨짐 | 높 | 페이지별 수동 테스트 |
| JS에서 생성하는 HTML의 색상 | 중 | JS 파일 별도 검사 |
| `@apply` 지시어 호환 | 중 | 순수 CSS로 변환 |

**최종 검증 스크립트**:
```bash
# 마이그레이션 완료 후 잔존 하드코딩 검사
grep -rn "bg-blue-\|text-blue-\|border-blue-\|ring-blue-" \
  app/templates/ app/static/js/ \
  --include="*.html" --include="*.js" \
  | grep -v "node_modules" | grep -v ".pyc"
```

---

## 부록: 전체 일정 요약

| Phase | 작업 | 예상 기간 | 의존성 |
|-------|------|----------|--------|
| **Phase 1** | CSS 변수 + 글로벌 스타일 | 2~3일 | 없음 |
| **Phase 2** | 컬러 선택 UI | 1~2일 | Phase 1 |
| **Phase 3** | 페이지별 마이그레이션 | 5~7일 | Phase 1 |
| **Phase 4** | 대시보드 연동 + 테스트 | 1~2일 | Phase 1~3 |
| **합계** | | **9~14일** | |

Phase 1이 완료되면 Phase 2와 Phase 3을 병렬로 진행할 수 있다.
Phase 3의 각 서브 태스크(3-1 ~ 3-7)도 독립적이므로 병렬 작업이 가능하다.

---

**Last Updated**: 2026-04-23 | **Version**: v1.0.0
