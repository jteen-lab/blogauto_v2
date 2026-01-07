# 멀티 에이전트 프롬프트: 모듈 카드 모바일 슬라이드 버그 수정

## 📋 작업 개요

**작업명:** 모듈 카드 모바일 슬라이드 미작동 버그 수정  
**우선순위:** 긴급  
**환경:** 스마트폰 (Android Chrome 테스트 확인)  

---

## 🐛 문제 상황

### 현상
- **플로우 카드:** 모바일에서 슬라이드 정상 작동 ✅
- **모듈 카드:** 모바일에서 슬라이드 미작동 ❌
- PC/태블릿에서는 둘 다 정상 작동

### 환경
- Android 스마트폰
- "애니메이션 줄이기" 설정 비활성화 상태
- 플로우 슬라이드는 정상 작동하므로 모듈 카드 CSS/JS만 문제

---

## 🔍 분석 요청

### @explorer-agent 작업

**두 카드의 슬라이드 구현 비교 분석:**

#### 1. 플로우 카드 분석 (정상 작동)
```
파일 확인:
- app/templates/flows/_card.html
- app/static/css/flow-card-slide.css
- app/static/js/flows/list.js
```

확인 사항:
- 슬라이드에 사용된 CSS 클래스명
- animation 속성 정의
- JavaScript 초기화 방식

#### 2. 모듈 카드 분석 (미작동)
```
파일 확인:
- app/templates/modules/_card.html
- app/static/css/flow-card-slide.css (공통 사용?)
- app/static/js/modules/list.js
```

확인 사항:
- 슬라이드에 사용된 CSS 클래스명
- animation 속성 정의
- JavaScript 초기화 방식

#### 3. 차이점 도출
- CSS 클래스명 차이
- animation 속성 차이
- -webkit- 접두사 유무
- JavaScript 초기화 로직 차이

---

## 🔧 예상 원인 및 해결 방향

### 가능성 1: CSS 클래스명 불일치

**플로우 카드:**
```css
.module-slide-track {
    animation: slideInfo 30s linear infinite;
}
```

**모듈 카드 (다른 클래스명 사용?):**
```css
.module-info-track {
    animation: slideInfo 30s linear infinite;
}
```

→ 클래스명 통일 또는 누락된 스타일 추가

### 가능성 2: -webkit-animation 누락

**수정 필요:**
```css
.module-info-track {
    animation: slideInfo var(--info-duration, 30s) linear infinite;
    -webkit-animation: slideInfo var(--info-duration, 30s) linear infinite;
}

@keyframes slideInfo {
    0% { transform: translateX(0); }
    100% { transform: translateX(-50%); }
}

@-webkit-keyframes slideInfo {
    0% { -webkit-transform: translateX(0); }
    100% { -webkit-transform: translateX(-50%); }
}
```

### 가능성 3: JavaScript 초기화 문제

모듈 카드의 슬라이드 초기화 함수가 모바일에서 호출되지 않을 수 있음.

```javascript
// 플로우 카드 초기화 방식 확인 후 모듈에도 동일 적용
document.addEventListener('DOMContentLoaded', () => {
    initModuleSlides();
});
```

### 가능성 4: 템플릿 구조 차이

플로우 카드와 모듈 카드의 HTML 구조가 달라서 CSS 선택자가 맞지 않을 수 있음.

---

## 🔄 에이전트별 작업

### @explorer-agent

**목표:** 플로우 vs 모듈 슬라이드 구현 차이점 분석

**작업:**
1. `app/templates/flows/_card.html`에서 슬라이드 관련 HTML 구조 확인
2. `app/templates/modules/_card.html`에서 슬라이드 관련 HTML 구조 확인
3. 사용된 CSS 클래스명 비교
4. `app/static/css/flow-card-slide.css`에서 두 카드의 스타일 정의 확인
5. JavaScript 초기화 로직 비교

**산출물:**
```
┌─────────────┬─────────────────────────┬─────────────────────────┐
│ 항목        │ 플로우 카드              │ 모듈 카드               │
├─────────────┼─────────────────────────┼─────────────────────────┤
│ CSS 클래스  │ [클래스명]              │ [클래스명]              │
│ animation   │ [정의 여부]             │ [정의 여부]             │
│ -webkit-    │ [유무]                  │ [유무]                  │
│ JS 초기화   │ [방식]                  │ [방식]                  │
└─────────────┴─────────────────────────┴─────────────────────────┘
```

---

### @frontend-agent

**목표:** 모듈 카드 모바일 슬라이드 수정

**작업:**

#### 1. CSS 수정 (app/static/css/flow-card-slide.css)

플로우 카드와 동일한 스타일 적용:
```css
/* 모듈 카드 슬라이드 - 모바일 호환 */
.module-info-track {
    display: inline-flex;
    white-space: nowrap;
    animation: slideInfo var(--info-duration, 30s) linear infinite;
    -webkit-animation: slideInfo var(--info-duration, 30s) linear infinite;
}

/* -webkit- keyframes 추가 (없는 경우) */
@-webkit-keyframes slideInfo {
    0% { 
        -webkit-transform: translateX(0);
        transform: translateX(0); 
    }
    100% { 
        -webkit-transform: translateX(-50%);
        transform: translateX(-50%); 
    }
}
```

#### 2. 템플릿 확인/수정 (app/templates/modules/_card.html)

플로우 카드와 동일한 HTML 구조 확인:
- 슬라이드 컨테이너 클래스
- 트랙 클래스
- data 속성

#### 3. JavaScript 확인/수정 (app/static/js/modules/list.js)

초기화 로직이 플로우와 동일한지 확인:
```javascript
// 슬라이드 초기화 함수가 호출되는지 확인
function initModuleSlides() {
    document.querySelectorAll('.module-info-track').forEach(track => {
        // 초기화 로직
    });
}
```

---

### @reviewer-agent

**검증 항목:**

#### 모바일 테스트
- [ ] Android Chrome에서 모듈 슬라이드 작동
- [ ] iOS Safari에서 모듈 슬라이드 작동 (가능하면)

#### 기존 기능 유지
- [ ] PC에서 모듈 슬라이드 정상 작동
- [ ] PC에서 플로우 슬라이드 정상 작동
- [ ] 태블릿에서 정상 작동
- [ ] 호버/터치 일시정지 작동

#### 코드 품질
- [ ] -webkit- 접두사 추가됨
- [ ] 플로우/모듈 스타일 일관성

---

## 📁 수정 대상 파일

```
app/static/css/flow-card-slide.css    # CSS 수정 (주요)
app/templates/modules/_card.html      # 템플릿 확인/수정
app/static/js/modules/list.js         # JS 확인/수정
```

---

## 🚀 실행 명령

```bash
/multi-agent 모듈 카드가 모바일에서 슬라이드 되지 않는 버그를 수정해주세요.

문제 상황:
- 플로우 카드: 모바일 슬라이드 정상 ✅
- 모듈 카드: 모바일 슬라이드 미작동 ❌
- PC/태블릿에서는 둘 다 정상

작업:
1. @explorer-agent: 플로우 카드 vs 모듈 카드 슬라이드 구현 차이점 분석
2. @frontend-agent: 분석 결과 기반으로 모듈 카드 수정 (-webkit- 접두사, 클래스명 등)
3. @reviewer-agent: 수정 검증

수정 프롬프트: docs/prompts/prompt-module-mobile-slide-fix.md
```

---

## ✅ 완료 기준

- [ ] Android 스마트폰에서 모듈 카드 슬라이드 정상 작동
- [ ] 플로우 카드 슬라이드 기존 기능 유지
- [ ] PC/태블릿 정상 작동 유지
- [ ] -webkit- 접두사 적용
