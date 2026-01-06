# 멀티 에이전트 프롬프트: 모듈 카드 슬라이드 UI 적용

## 📋 작업 개요

**작업명:** 모듈 카드에 플로우 카드와 동일한 슬라이드 UI 적용  
**우선순위:** 높음  
**연관 작업:** 플로우 카드 슬라이드 UI 구현  

### 목표
모듈 관리 페이지의 카드에서도 플로우 카드와 동일하게 **각 정보 항목별 행 단위 슬라이드** 방식을 적용하여 일관된 UI/UX 제공.

### 참고
- 플로우 카드 슬라이드: 이미 구현 완료
- 동일한 CSS/JS 재사용

---

## 🎯 요구사항

### 1. 모듈 카드 현재 구조 (예상)

```
┌─────────────────────────────────────────┐
│ 🔁 재발행 모듈 A          [활성] [편집] │
├─────────────────────────────────────────┤
│ 적용구간: 1~무제한 (누적 포스트)        │
│ 재발행 간격: 25분마다 (최대 21회/일)    │
│ 스케줄: 월,수,금(09~22)                 │
│         화,목(12~22)                    │
│         토(10~12), 일(14~16)            │
│ 플랫폼: WordPress                        │
├─────────────────────────────────────────┤
│ 더보기 (2개 더) ▼                       │
└─────────────────────────────────────────┘
```

현재는 정보가 정적으로 나열되어 있음.

### 2. 수정 후 구조

```
┌─────────────────────────────────────────────────────────────┐
│ 🔁 재발행 모듈 A                              [활성] [편집] │
├─────────────────────────────────────────────────────────────┤
│ [적용구간  ] │ 1~무제한 (누적 포스트) | ◆ | 1~무제한...    → │
│ [재발행간격] │ 25분마다 (최대 21회/일) | ◆ | 25분...       → │
│ [스케줄    ] │ 월수금(09~22) | 화목(12~22) | 토... | ◆ |   → │
│ ←── 33% ──→ │←──────────────── 67% ─────────────────────→  │
├─────────────────────────────────────────────────────────────┤
│                     더보기 (2개 더) ▼                       │
└─────────────────────────────────────────────────────────────┘
```

**적용 사항:**
- 각 정보 항목이 **한 행(Row)**을 차지
- 항목명(라벨)은 **왼쪽 고정** (33%)
- 항목값은 **오른쪽 슬라이드** (67%)
- 플로우 카드와 **동일한 슬라이드 방식** 적용

---

## 📐 기술 명세

### 모듈 타입별 표시 정보

#### 재발행 모듈
| 항목명 | 표시 값 예시 |
|--------|-------------|
| 적용구간 | 1~무제한 (누적 포스트), 최근 100개 등 |
| 재발행 간격 | 25분마다 (최대 21회/일) |
| 스케줄 | 월,수,금(09~22) \| 화,목(12~22) \| 토(10~12) \| 일(14~16) |
| 플랫폼 | WordPress, Blogger |

#### AI 글생성 모듈
| 항목명 | 표시 값 예시 |
|--------|-------------|
| AI 모델 | GPT-4o, Claude 3.5 |
| 글자수 | 1500자, 2000자 |
| 톤/스타일 | 친근한 대화체, 정보 전달 |
| 이미지 생성 | 자동 생성, 수동 |

#### 제목 수집 모듈
| 항목명 | 표시 값 예시 |
|--------|-------------|
| 소스 | 네이버 블로그, 구글 |
| 수집량 | 100개/일 |
| 키워드 | 5개 등록 |
| 필터 | 중복 제거, 길이 필터 |

#### 프롬프트 모듈
| 항목명 | 표시 값 예시 |
|--------|-------------|
| 템플릿 | SEO 최적화 A |
| 변수 | 제목, 키워드, 본문 |
| 길이 설정 | 상세 (2000토큰) |

#### 발행 모듈
| 항목명 | 표시 값 예시 |
|--------|-------------|
| 플랫폼 | WordPress, Blogger |
| 발행 방식 | 즉시 발행, 예약 발행 |
| 카테고리 | 자동 분류, 수동 지정 |

---

### 슬라이드 적용 규칙

#### 플로우 카드와 동일한 규칙 적용

1. **비율:** 라벨 33% : 값 67%
2. **슬라이드 조건:** 값이 슬라이드 영역보다 길 때만 슬라이드
3. **짧은 값:** 정적 표시 (복제 없음)
4. **구분자:** 슬라이드 끝에 ◆ 표시
5. **속도:** 플로우 카드와 동일 (baseSpeed: 18초, perItem: 4.5초)
6. **호버:** 해당 행만 일시정지
7. **터치:** 탭으로 일시정지/재생

#### 더보기 버튼 규칙

- **기본 노출:** 최대 3행
- **3행 초과 시:** 더보기 버튼 표시
- **더보기 버튼 스타일:** 플로우 카드와 동일

---

## 🔄 에이전트별 작업

### @explorer-agent (Gemini CLI)

**목표:** 모듈 카드 현재 구조 분석

**작업 내용:**
1. `app/templates/modules/` 디렉토리 구조 확인
2. 모듈 카드 템플릿 파일 분석 (`list.html`, `_card.html` 등)
3. 모듈 타입별 데이터 구조 확인
4. 현재 정보 표시 방식 파악

**산출물:**
- 현재 모듈 카드 템플릿 구조
- 모듈 타입별 표시 정보 목록
- 수정이 필요한 파일 목록

---

### @backend-agent

**목표:** 모듈 상세 정보 데이터 구조 확인 및 필요시 수정

**작업 내용:**
1. 모듈 목록 API에서 각 모듈의 상세 정보가 포함되는지 확인
2. 필요시 `display_info` 형태로 데이터 가공
   ```python
   # 예시: 모듈 타입별 표시 정보 매핑
   def get_display_info(module):
       if module.type == 'republish':
           return [
               {'label': '적용구간', 'value': module.range_display},
               {'label': '재발행 간격', 'value': module.interval_display},
               {'label': '스케줄', 'value': module.schedule_display},
               {'label': '플랫폼', 'value': module.platform},
           ]
       # ... 다른 모듈 타입들
   ```

**수정 대상 파일 (예상):**
- `app/api/modules.py`
- `app/schemas/module.py`

---

### @frontend-agent

**목표:** 모듈 카드에 슬라이드 UI 적용

**작업 내용:**

#### 1. 기존 CSS/JS 재사용
플로우 카드에서 사용하는 슬라이드 CSS/JS를 모듈 카드에도 적용:
- `app/static/css/flow-card-slide.css` → 공통 사용
- `app/static/js/flow-card-slide.js` → 공통 사용

#### 2. 모듈 카드 템플릿 수정

**파일:** `app/templates/modules/list.html` 또는 관련 partial

**수정 전 (예상):**
```html
<div class="module-card">
    <div class="module-header">
        <span class="module-icon">🔁</span>
        <span class="module-name">재발행 모듈 A</span>
    </div>
    <div class="module-info">
        <p>적용구간: 1~무제한</p>
        <p>재발행 간격: 25분마다</p>
        <p>스케줄: 월,수,금(09~22)</p>
        <!-- ... -->
    </div>
</div>
```

**수정 후:**
```html
<div class="module-card" x-data="{ 
    expanded: false,
    maxVisible: 3,
    get displayInfo() {
        return this.module.display_info || [];
    },
    get hiddenCount() {
        return Math.max(0, this.displayInfo.length - this.maxVisible);
    }
}">
    <!-- 카드 헤더 -->
    <div class="module-header">
        <div class="flex items-center gap-2">
            <span class="module-icon" :style="{ background: module.color }">
                <span x-text="module.icon"></span>
            </span>
            <span class="module-name" x-text="module.name"></span>
        </div>
        <div class="flex items-center gap-2">
            <span class="status-badge" :class="module.is_active ? 'active' : 'inactive'">
                <span x-text="module.is_active ? '활성' : '비활성'"></span>
            </span>
            <button class="edit-btn">편집</button>
        </div>
    </div>
    
    <!-- 정보 행 목록 (슬라이드 적용) -->
    <div class="module-info-list">
        <template x-for="(info, index) in displayInfo" :key="index">
            <div class="info-row" x-show="expanded || index < maxVisible" x-transition>
                <!-- 라벨 (고정, 33%) -->
                <div class="info-label-fixed">
                    <span x-text="info.label"></span>
                </div>
                
                <!-- 값 (슬라이드, 67%) -->
                <div class="info-value-slide info-fade-mask" 
                     :style="{ '--info-duration': calculateDuration(info) + 's' }"
                     x-init="initSlide($el)">
                    <div class="info-value-track">
                        <!-- 원본 값 -->
                        <span class="info-value-item" x-text="info.value"></span>
                        <!-- 구분자 -->
                        <span class="info-separator">◆</span>
                        <!-- 복제 값 (슬라이드 필요시만) -->
                        <span class="info-value-item" x-text="info.value" aria-hidden="true"></span>
                    </div>
                    <span class="pause-hint">⏸</span>
                </div>
            </div>
        </template>
    </div>
    
    <!-- 더보기/접기 버튼 -->
    <button 
        x-show="hiddenCount > 0" 
        @click="expanded = !expanded"
        class="expand-btn"
    >
        <template x-if="!expanded">
            <span>더보기 (<span x-text="hiddenCount"></span>개 더) ▼</span>
        </template>
        <template x-if="expanded">
            <span>접기 ▲</span>
        </template>
    </button>
</div>
```

#### 3. 추가 CSS (모듈 카드 전용)

**파일:** `app/static/css/flow-card-slide.css` (기존 파일에 추가)

```css
/* ========================================
   모듈 카드 슬라이드 스타일
   ======================================== */

/* 정보 행 */
.info-row {
    display: flex;
    align-items: center;
    border-bottom: 1px solid #f0f0f0;
    background: white;
}

.info-row:last-child {
    border-bottom: none;
}

.info-row:hover {
    background: #fafafa;
}

/* 라벨 (고정, 33%) */
.info-label-fixed {
    flex-shrink: 0;
    width: 33%;
    max-width: 100px;
    padding: 8px 10px;
    border-right: 1px solid #e5e7eb;
    background: #f9fafb;
    font-size: 11px;
    font-weight: 500;
    color: #6b7280;
}

/* 값 (슬라이드, 67%) */
.info-value-slide {
    flex: 2;
    overflow: hidden;
    position: relative;
}

.info-value-track {
    display: inline-flex;
    white-space: nowrap;
    animation: slideInfo var(--info-duration, 30s) linear infinite;
    padding: 8px 0;
}

.info-value-item {
    display: inline-flex;
    align-items: center;
    padding: 0 12px;
    font-size: 12px;
    color: #374151;
}

/* 호버 시 일시정지 */
.info-row:hover .info-value-track {
    animation-play-state: paused;
}
```

#### 4. JavaScript 수정

**파일:** `app/static/js/flow-card-slide.js` (기존 파일에 추가)

```javascript
// 슬라이드 초기화 (조건부 슬라이드)
function initSlide(container) {
    const track = container.querySelector('.info-value-track');
    const duplicates = container.querySelectorAll('[aria-hidden="true"]');
    const separator = container.querySelector('.info-separator');
    
    // 슬라이드 필요 여부 판단
    requestAnimationFrame(() => {
        if (track.scrollWidth <= container.clientWidth * 1.2) {
            // 슬라이드 불필요: 복제 요소 숨김, 애니메이션 중지
            duplicates.forEach(el => el.style.display = 'none');
            if (separator) separator.style.display = 'none';
            track.style.animation = 'none';
        }
    });
}

// 속도 계산 (플로우 카드와 동일)
function calculateDuration(info) {
    // 값의 길이에 따라 속도 조절
    const length = (info.value || '').length;
    const baseSpeed = 18;
    const perChar = 0.3;  // 글자당 0.3초 추가
    return Math.max(baseSpeed, baseSpeed + (length * perChar));
}

// 모바일 터치 지원 (모듈 카드용)
document.querySelectorAll('.info-row').forEach(row => {
    let paused = false;
    row.addEventListener('touchstart', function() {
        paused = !paused;
        const track = this.querySelector('.info-value-track');
        if (track) {
            track.style.animationPlayState = paused ? 'paused' : 'running';
        }
    });
});
```

---

### @reviewer-agent

**목표:** 코드 리뷰 및 품질 검증

**검증 항목:**

#### 기능 검증
- [ ] 각 정보 항목이 행 단위로 표시됨
- [ ] 라벨:값 비율이 33%:67%
- [ ] 긴 값은 슬라이드 적용
- [ ] 짧은 값은 정적 표시 (복제 미노출)
- [ ] 슬라이드 끝에 구분자(◆) 표시
- [ ] 호버 시 해당 행만 일시정지
- [ ] 터치 시 일시정지/재생 토글

#### 더보기 버튼
- [ ] 기본 3행 노출
- [ ] 3행 초과 시 더보기 버튼 표시
- [ ] 더보기 버튼 스타일이 플로우 카드와 동일

#### 일관성 검증
- [ ] 플로우 카드와 동일한 슬라이드 속도
- [ ] 플로우 카드와 동일한 페이드 마스크
- [ ] 플로우 카드와 동일한 호버 효과

#### 반응형/접근성
- [ ] PC/모바일 정상 작동
- [ ] `prefers-reduced-motion` 지원
- [ ] `aria-hidden` 적용

---

## 📁 예상 파일 변경 목록

### 수정
```
app/templates/modules/list.html       # 모듈 카드 템플릿
app/static/css/flow-card-slide.css    # 공통 슬라이드 CSS (모듈용 추가)
app/static/js/flow-card-slide.js      # 공통 슬라이드 JS (모듈용 추가)
app/api/modules.py                    # display_info 데이터 추가 (필요시)
```

---

## 🚀 실행 명령

```bash
/multi-agent 모듈 카드에 플로우 카드와 동일한 슬라이드 UI를 적용해주세요:

1. 각 정보 항목을 행 단위로 표시
2. 라벨(33%) : 값(67%) 비율 적용
3. 값이 길면 슬라이드, 짧으면 정적 표시
4. 슬라이드 끝에 구분자(◆) 표시
5. 기존 플로우 카드 CSS/JS 재사용
6. 더보기 버튼 로직도 동일하게 적용 (기본 3행)

수정 프롬프트: /mnt/user-data/outputs/prompt-module-card-slide.md
```

---

## ✅ 완료 기준

- [ ] 모듈 카드에 행 단위 슬라이드 적용
- [ ] 라벨:값 비율 33%:67%
- [ ] 긴 값 슬라이드 / 짧은 값 정적 표시
- [ ] 슬라이드 끝 구분자 표시
- [ ] 호버/터치 일시정지 작동
- [ ] 더보기 버튼 로직 (기본 3행)
- [ ] 플로우 카드와 일관된 UI/UX
- [ ] PC/모바일 정상 작동
