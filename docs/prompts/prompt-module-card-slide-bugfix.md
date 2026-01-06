# 멀티 에이전트 프롬프트: 모듈 카드 슬라이드 UI 버그 수정

## 📋 작업 개요

**작업명:** 모듈 카드 슬라이드 UI 버그 및 스타일 수정  
**우선순위:** 긴급  
**이전 작업:** 모듈 카드 슬라이드 UI 적용  

---

## 🐛 발견된 문제점

### 1. 페이지 이동 후 더보기 버튼 및 정보 사라짐

**현상:**
- 모듈 관리 페이지에서 슬라이드 UI가 정상 적용됨
- 다른 페이지로 이동했다가 다시 모듈 관리 페이지로 돌아오면:
  - 더보기 버튼 사라짐
  - 정보가 모두 출력되지 않음

**원인 추정:**
- Alpine.js 컴포넌트 초기화 문제
- SPA 방식 네비게이션 시 x-data 재초기화 실패
- 또는 JavaScript 이벤트 리스너 재등록 실패

**해결 방향:**
```javascript
// Alpine.js 재초기화 확인
document.addEventListener('alpine:init', () => {
    // 컴포넌트 등록
});

// 또는 turbo/htmx 사용 시 이벤트 처리
document.addEventListener('turbo:load', () => {
    // 페이지 로드 시 재초기화
});
```

---

### 2. 글자 스타일 불일치 (플로우 카드 vs 모듈 카드)

**현상:**
- 모듈 카드의 정보 글자체가 전체적으로 **연함**
- 플로우 카드와 글자 진하기, 색상이 다름

**수정 요청:**
- 플로우 카드와 **동일한 글자 스타일** 적용
- 글자 색상, font-weight 통일

**플로우 카드 스타일 (참고):**
```css
/* 플로우 카드 정보 스타일 */
.info-label {
    color: #9ca3af;      /* 라벨: 연한 회색 */
    font-size: 11px;
}

.info-value {
    color: #374151;      /* 값: 진한 회색 */
    font-weight: 500;    /* 중간 굵기 */
    font-size: 11px;
}

/* 강조 값 */
.info-value.highlight {
    color: #ea580c;      /* 주황색 */
    font-weight: 600;
}
```

**모듈 카드에 동일 적용:**
```css
/* 모듈 카드 정보 스타일 - 플로우와 통일 */
.info-row .info-label-fixed {
    color: #6b7280;      /* 라벨 */
    font-weight: 500;
    font-size: 11px;
}

.info-row .info-value-item {
    color: #374151;      /* 값: 진한 회색 */
    font-weight: 500;    /* 중간 굵기 */
    font-size: 12px;
}
```

---

### 3. 슬라이드 안 되는 정보의 여백 부족

**현상:**
- 정보가 짧아서 슬라이드가 적용되지 않는 경우
- 값이 **제목 영역 경계에 너무 붙어있음**
- 여백이 전혀 없음

**현재 상태:**
```
┌────────────────────────────────────────┐
│ [적용구간]│1~무제한                    │
│           ↑                            │
│           경계에 바로 붙어있음 (여백 없음)
└────────────────────────────────────────┘
```

**수정 요청:**
```
┌────────────────────────────────────────┐
│ [적용구간] │  1~무제한                 │
│            ↑ ↑                         │
│            │ 왼쪽 여백 (padding-left)  │
│            경계선                       │
└────────────────────────────────────────┘
```

**CSS 수정:**
```css
.info-value-slide {
    padding-left: 12px;  /* 왼쪽 여백 추가 */
}

/* 또는 트랙 내부에 여백 */
.info-value-track {
    padding-left: 12px;
}

.info-value-item:first-child {
    padding-left: 12px;  /* 첫 번째 항목 왼쪽 여백 */
}
```

---

### 4. 페이드 마스크로 인한 시인성 저하

**현상:**
- 슬라이드 영역 양쪽에 그라데이션(페이드 마스크) 적용됨
- 슬라이드 안 되는 짧은 정보의 경우에도 **왼쪽 그라데이션이 적용**됨
- 글자가 흐리게 보여 **시인성 떨어짐**

**현재 상태:**
```
│ [적용구간] │ ░░1~무제한░░              │
│              ↑                         │
│              그라데이션으로 글자 흐림   │
```

**수정 요청:**
- 슬라이드가 **적용되는 경우에만** 페이드 마스크 적용
- 슬라이드가 **적용되지 않는 경우** 페이드 마스크 제거

**해결 방법:**

#### 방법 A: 조건부 클래스 적용
```html
<!-- 슬라이드 필요 여부에 따라 클래스 토글 -->
<div class="info-value-slide" 
     :class="{ 'info-fade-mask': needsSlide }">
```

#### 방법 B: JavaScript로 동적 제거
```javascript
function initSlide(container) {
    const track = container.querySelector('.info-value-track');
    
    requestAnimationFrame(() => {
        if (track.scrollWidth <= container.clientWidth * 1.2) {
            // 슬라이드 불필요: 페이드 마스크 제거
            container.classList.remove('info-fade-mask');
            // 복제 요소 숨김
            // 애니메이션 중지
            track.style.animation = 'none';
        }
    });
}
```

#### 방법 C: 페이드 마스크 시작점 조정
```css
/* 왼쪽 페이드 시작점을 더 안쪽으로 */
.info-fade-mask {
    mask-image: linear-gradient(
        to right,
        transparent 0%,
        black 3%,       /* 기존 5% → 3%로 축소 */
        black 95%,
        transparent 100%
    );
}

/* 슬라이드 안 되는 경우 페이드 없음 */
.info-value-slide.no-slide {
    mask-image: none;
    -webkit-mask-image: none;
}
```

---

## 🔄 에이전트별 작업

### @frontend-agent

#### 1. Alpine.js 초기화 문제 해결

**파일:** `app/templates/modules/list.html` 또는 관련 JS

**확인 사항:**
- Alpine.js 컴포넌트가 페이지 이동 후에도 정상 초기화되는지
- turbo/htmx 사용 시 적절한 이벤트 핸들링
- x-data 내 데이터가 올바르게 바인딩되는지

**수정 예시:**
```javascript
// 페이지 로드/재로드 시 초기화 보장
document.addEventListener('DOMContentLoaded', initModuleCards);
document.addEventListener('turbo:load', initModuleCards);  // Turbo 사용 시
document.addEventListener('htmx:afterSwap', initModuleCards);  // HTMX 사용 시

function initModuleCards() {
    // 슬라이드 초기화
    document.querySelectorAll('.info-value-slide').forEach(container => {
        initSlide(container);
    });
}
```

#### 2. 글자 스타일 통일

**파일:** `app/static/css/flow-card-slide.css`

```css
/* 모듈 카드 정보 스타일 - 플로우 카드와 통일 */
.info-row .info-label-fixed {
    color: #6b7280;
    font-weight: 500;
    font-size: 11px;
}

.info-row .info-value-item {
    color: #374151;       /* 진한 회색 */
    font-weight: 500;     /* 중간 굵기 */
    font-size: 12px;
}

/* 강조가 필요한 값 */
.info-value-item.text-orange-600 {
    color: #ea580c;
    font-weight: 600;
}

.info-value-item.text-blue-600 {
    color: #2563eb;
    font-weight: 600;
}

.info-value-item.text-green-600 {
    color: #16a34a;
    font-weight: 600;
}
```

#### 3. 슬라이드 안 되는 정보 여백 추가

**파일:** `app/static/css/flow-card-slide.css`

```css
/* 값 영역 기본 여백 */
.info-value-slide {
    padding-left: 12px;
}

/* 트랙 내부 첫 항목 여백 */
.info-value-item:first-child {
    padding-left: 0;  /* 컨테이너에서 이미 여백 적용 */
}

/* 슬라이드 안 되는 경우 추가 여백 */
.info-value-slide.no-slide .info-value-item {
    padding-left: 12px;
}
```

#### 4. 조건부 페이드 마스크 적용

**파일:** `app/static/js/flow-card-slide.js`

```javascript
function initSlide(container) {
    const track = container.querySelector('.info-value-track');
    const duplicates = container.querySelectorAll('[aria-hidden="true"]');
    const separator = container.querySelector('.info-separator');
    
    requestAnimationFrame(() => {
        const needsSlide = track.scrollWidth > container.clientWidth * 1.2;
        
        if (!needsSlide) {
            // 슬라이드 불필요
            container.classList.add('no-slide');
            container.classList.remove('info-fade-mask');  // 페이드 마스크 제거
            
            // 복제 요소 숨김
            duplicates.forEach(el => el.style.display = 'none');
            if (separator) separator.style.display = 'none';
            
            // 애니메이션 중지
            track.style.animation = 'none';
        } else {
            // 슬라이드 필요
            container.classList.remove('no-slide');
            container.classList.add('info-fade-mask');  // 페이드 마스크 적용
        }
    });
}
```

**CSS 추가:**
```css
/* 슬라이드 안 되는 경우: 페이드 마스크 없음 */
.info-value-slide.no-slide {
    mask-image: none;
    -webkit-mask-image: none;
}
```

---

### @reviewer-agent

#### 검증 항목

**버그 수정 확인:**
- [ ] 다른 페이지 이동 후 돌아와도 더보기 버튼 정상 표시
- [ ] 다른 페이지 이동 후 돌아와도 정보 정상 출력
- [ ] Alpine.js 컴포넌트 재초기화 정상

**스타일 통일 확인:**
- [ ] 모듈 카드 글자 색상이 플로우 카드와 동일
- [ ] 모듈 카드 글자 굵기가 플로우 카드와 동일
- [ ] 강조 색상 (주황, 파랑, 초록) 동일하게 적용

**여백 및 시인성 확인:**
- [ ] 슬라이드 안 되는 정보에 왼쪽 여백 적용됨
- [ ] 슬라이드 안 되는 정보에 페이드 마스크 적용 안 됨
- [ ] 글자가 흐리게 보이지 않음
- [ ] 시인성 개선됨

**기존 기능 유지:**
- [ ] 슬라이드 되는 정보는 정상 슬라이드
- [ ] 슬라이드 되는 정보에 페이드 마스크 정상 적용
- [ ] 호버/터치 일시정지 정상 작동
- [ ] 더보기/접기 정상 작동

---

## 📁 수정 대상 파일

```
app/templates/modules/list.html       # Alpine.js 초기화 수정
app/static/css/flow-card-slide.css    # 스타일 통일, 여백, 페이드 마스크
app/static/js/flow-card-slide.js      # 초기화 로직, 조건부 페이드 마스크
```

---

## 🚀 실행 명령

```bash
/multi-agent 모듈 카드 슬라이드 UI의 다음 버그 및 스타일 문제를 수정해주세요:

1. [버그] 페이지 이동 후 돌아오면 더보기 버튼과 정보가 사라지는 문제 (Alpine.js 초기화)
2. [스타일] 글자 진하기/색상을 플로우 카드와 동일하게 통일
3. [여백] 슬라이드 안 되는 정보의 왼쪽 여백 추가
4. [시인성] 슬라이드 안 되는 정보에 페이드 마스크 제거 (글자 흐림 방지)

수정 프롬프트: docs/prompts/prompt-module-card-slide-bugfix.md
```

---

## ✅ 완료 기준

- [ ] 페이지 이동 후에도 더보기 버튼 및 정보 정상 표시
- [ ] 모듈 카드 글자 스타일이 플로우 카드와 동일
- [ ] 슬라이드 안 되는 정보에 적절한 왼쪽 여백 적용
- [ ] 슬라이드 안 되는 정보에 페이드 마스크 미적용 (시인성 확보)
- [ ] 기존 슬라이드 기능 정상 유지
