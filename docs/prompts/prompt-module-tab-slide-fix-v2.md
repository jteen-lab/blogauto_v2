# 멀티 에이전트 프롬프트: 모듈 카드 탭 전환 시 슬라이드 초기화 문제 수정

## 📋 작업 개요

**작업명:** 모듈 카드 탭 전환 시 슬라이드 미작동 버그 수정  
**우선순위:** 긴급  
**환경:** 스마트폰 (탭 기반 UI)  

---

## 🐛 문제 상황

### 현상
- **PC/태블릿:** 모든 모듈 섹션이 한 화면에 표시 → 슬라이드 정상 작동 ✅
- **스마트폰:** 탭으로 섹션 전환 → 슬라이드 미작동 ❌

### 화면 구성 차이

**PC/태블릿 (4개 섹션 동시 표시):**
```
┌─────────┬─────────┬─────────┬─────────┐
│ 재발행  │ AI생성  │ 제목수집 │ 발행    │
│ 모듈들  │ 모듈들  │ 모듈들  │ 모듈들  │
│ (슬라이드 작동 ✅)                    │
└─────────┴─────────┴─────────┴─────────┘
```

**스마트폰 (탭 전환 방식):**
```
┌─────────────────────────────────────┐
│  [재발행] [AI생성] [제목수집] [발행] │  ← 탭 버튼
├─────────────────────────────────────┤
│                                     │
│        현재 선택된 섹션만 표시       │
│        (슬라이드 미작동 ❌)          │
│                                     │
└─────────────────────────────────────┘
```

### 원인 분석

1. **페이지 로드 시:** 첫 번째 탭만 `display: block`, 나머지는 `display: none`
2. **슬라이드 초기화:** `display: none` 상태에서는 요소의 **너비가 0으로 계산**됨
3. **초기화 로직:** "컨텐츠 너비 < 컨테이너 너비" → "슬라이드 불필요"로 판단
4. **탭 전환 후:** 초기화 함수가 **재호출되지 않음** → 슬라이드 여전히 미작동

---

## 🔍 분석 요청

### @explorer-agent 작업

**모듈 관리 페이지의 탭 구조 분석:**

#### 1. 탭 UI 구조 확인
```
파일 확인:
- app/templates/modules/list.html
- app/static/js/modules/list.js
```

확인 사항:
- 탭 전환 방식 (Alpine.js? JavaScript?)
- 탭 컨텐츠 숨김 방식 (`display: none`? `hidden`? `visibility`?)
- 탭 전환 이벤트 핸들러

#### 2. 슬라이드 초기화 로직 확인
```
파일 확인:
- app/static/js/modules/list.js
- app/static/css/flow-card-slide.css
```

확인 사항:
- 슬라이드 초기화 함수 (`initSlide`, `initModuleSlides` 등)
- 초기화 호출 시점 (DOMContentLoaded? Alpine.init?)
- 너비 계산 로직

#### 3. 플로우 카드와 비교
플로우 관리 페이지에서 유사한 탭 구조가 있는지 확인

---

## 🔧 해결 방안

### 방안 1: 탭 전환 시 슬라이드 재초기화 (권장)

탭이 활성화될 때마다 해당 탭 내의 슬라이드를 초기화합니다.

**JavaScript 수정:**
```javascript
// 탭 전환 이벤트 핸들러에 추가
function onTabChange(tabId) {
    // 기존 탭 전환 로직
    showTab(tabId);
    
    // 슬라이드 재초기화 (약간의 딜레이 후)
    setTimeout(() => {
        initSlidesInTab(tabId);
    }, 50);  // display: block 적용 후 실행
}

function initSlidesInTab(tabId) {
    const tabContent = document.querySelector(`#${tabId}`);
    if (!tabContent) return;
    
    tabContent.querySelectorAll('.module-info-track').forEach(track => {
        initSlideTrack(track);
    });
}

function initSlideTrack(track) {
    const container = track.closest('.info-value-slide');
    if (!container) return;
    
    // 너비 재계산
    const containerWidth = container.clientWidth;
    const trackWidth = track.scrollWidth;
    
    if (trackWidth > containerWidth * 1.2) {
        // 슬라이드 필요
        container.classList.remove('no-slide');
        container.classList.add('info-fade-mask');
        track.style.animation = '';  // CSS 애니메이션 재적용
        track.style.webkitAnimation = '';
    }
}
```

### 방안 2: IntersectionObserver 사용

요소가 화면에 보일 때 자동으로 슬라이드 초기화합니다.

**JavaScript 수정:**
```javascript
// IntersectionObserver로 가시성 감지
const slideObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            initSlideTrack(entry.target);
            slideObserver.unobserve(entry.target);  // 한 번만 초기화
        }
    });
}, { threshold: 0.1 });

// 모든 슬라이드 트랙 관찰
document.querySelectorAll('.module-info-track').forEach(track => {
    slideObserver.observe(track);
});
```

### 방안 3: Alpine.js x-show 대신 x-cloak + CSS 사용

`display: none` 대신 `visibility: hidden`을 사용하면 너비가 유지됩니다.

**CSS 수정:**
```css
/* 탭 컨텐츠 숨김 방식 변경 */
.tab-content {
    position: absolute;
    visibility: hidden;
    opacity: 0;
    width: 100%;
}

.tab-content.active {
    position: relative;
    visibility: visible;
    opacity: 1;
}
```

---

## 🔄 에이전트별 작업

### @explorer-agent

**목표:** 모듈 관리 페이지 탭 구조 분석

**작업:**
1. `app/templates/modules/list.html`에서 탭 HTML 구조 확인
2. `app/static/js/modules/list.js`에서 탭 전환 로직 확인
3. 슬라이드 초기화 함수 위치 및 호출 시점 확인
4. Alpine.js 사용 여부 및 x-show/x-if 사용 확인

**산출물:**
```
탭 전환 방식: [Alpine.js x-show / JavaScript display 전환 / 기타]
숨김 방식: [display: none / visibility: hidden / 기타]
초기화 시점: [DOMContentLoaded / Alpine.init / 기타]
```

---

### @frontend-agent

**목표:** 탭 전환 시 슬라이드 재초기화 구현

**작업:**

#### 1. 탭 전환 이벤트에 슬라이드 재초기화 추가

**파일:** `app/static/js/modules/list.js`

```javascript
// 탭 전환 함수 수정 (기존 함수에 추가)
function switchTab(tabId) {
    // 기존 탭 전환 로직...
    
    // 슬라이드 재초기화 추가
    setTimeout(() => {
        reinitSlidesInTab(tabId);
    }, 100);
}

// 특정 탭 내 슬라이드 재초기화
function reinitSlidesInTab(tabId) {
    const tabContent = document.querySelector(`[data-tab="${tabId}"]`);
    if (!tabContent) return;
    
    tabContent.querySelectorAll('.module-info-track').forEach(track => {
        const container = track.closest('.info-value-slide');
        if (!container) return;
        
        // 복제 요소 다시 표시
        container.querySelectorAll('[aria-hidden="true"]').forEach(el => {
            el.style.display = '';
        });
        const separator = container.querySelector('.info-separator');
        if (separator) separator.style.display = '';
        
        // 너비 재계산
        const containerWidth = container.clientWidth;
        const trackWidth = track.scrollWidth;
        
        if (trackWidth > containerWidth * 1.2) {
            // 슬라이드 필요
            container.classList.remove('no-slide');
            container.classList.add('info-fade-mask');
            
            // 애니메이션 재시작
            track.style.animation = 'none';
            track.style.webkitAnimation = 'none';
            track.offsetHeight;  // reflow 트리거
            track.style.animation = '';
            track.style.webkitAnimation = '';
        } else {
            // 슬라이드 불필요
            container.classList.add('no-slide');
            container.classList.remove('info-fade-mask');
            container.querySelectorAll('[aria-hidden="true"]').forEach(el => {
                el.style.display = 'none';
            });
            if (separator) separator.style.display = 'none';
            track.style.animation = 'none';
            track.style.webkitAnimation = 'none';
        }
    });
}
```

#### 2. Alpine.js 사용 시 (x-show 감지)

**파일:** `app/templates/modules/list.html`

```html
<!-- Alpine.js x-show에 x-effect 추가 -->
<div x-show="activeTab === 'republish'" 
     x-effect="if (activeTab === 'republish') $nextTick(() => reinitSlides($el))">
    <!-- 모듈 카드들 -->
</div>
```

#### 3. 페이지 로드 시에도 활성 탭 초기화

```javascript
// DOMContentLoaded에서 활성 탭 슬라이드 초기화
document.addEventListener('DOMContentLoaded', () => {
    // 초기 로드 시 약간의 딜레이 후 초기화
    setTimeout(() => {
        const activeTab = document.querySelector('.tab-content.active, [x-show]:not([style*="display: none"])');
        if (activeTab) {
            reinitSlidesInTab(activeTab.id || activeTab.dataset.tab);
        }
    }, 200);
});
```

---

### @reviewer-agent

**검증 항목:**

#### 스마트폰 테스트
- [ ] 페이지 첫 로드 시 첫 번째 탭 슬라이드 작동
- [ ] 다른 탭으로 전환 시 슬라이드 작동
- [ ] 원래 탭으로 돌아와도 슬라이드 작동
- [ ] 여러 번 탭 전환해도 정상 작동

#### 기존 기능 유지
- [ ] PC에서 모든 섹션 슬라이드 정상 작동
- [ ] 태블릿에서 정상 작동
- [ ] 플로우 카드 슬라이드 영향 없음
- [ ] 호버/터치 일시정지 정상 작동

#### 성능 확인
- [ ] 탭 전환 시 눈에 띄는 지연 없음
- [ ] 메모리 누수 없음 (반복 전환 시)

---

## 📁 수정 대상 파일

```
app/static/js/modules/list.js         # 탭 전환 시 슬라이드 재초기화
app/templates/modules/list.html       # Alpine.js 수정 (필요 시)
```

---

## 🚀 실행 명령

```bash
/multi-agent 모듈 카드가 스마트폰에서 탭 전환 시 슬라이드가 작동하지 않는 버그를 수정해주세요.

문제 상황:
- PC/태블릿: 모든 섹션 동시 표시 → 슬라이드 정상 ✅
- 스마트폰: 탭 전환 방식 → 슬라이드 미작동 ❌

원인:
- 숨겨진 탭(display: none)에서 슬라이드 초기화 시 너비가 0으로 계산됨
- 탭 전환 후 슬라이드 초기화 함수가 재호출되지 않음

해결:
- 탭 전환 이벤트에 슬라이드 재초기화 함수 호출 추가

수정 프롬프트: docs/prompts/prompt-module-tab-slide-fix.md
```

---

## ✅ 완료 기준

- [ ] 스마트폰에서 탭 전환 시 모듈 슬라이드 정상 작동
- [ ] 페이지 첫 로드 시 첫 번째 탭 슬라이드 정상 작동
- [ ] PC/태블릿 기존 기능 유지
- [ ] 탭 전환 시 눈에 띄는 지연 없음
