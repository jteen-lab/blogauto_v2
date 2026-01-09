# Phase 7 UI 수정 및 글로벌 요약탭 재작업

## 📋 수정 사항 목록

---

## 1. 카테고리 관리 페이지 수정

### 1-1. 타이틀/버튼 배경색 제거

**현재**: "카테고리 관리" 타이틀과 "주제 추가" 버튼에 흰색 배경 사각형 적용됨
**변경**: 배경색 제거 (다른 페이지와 UI 통일)

### 1-2. 텍스트 변경

**현재**: "3계층 카테고리 구조로 블로그 콘텐츠를 체계화하세요"
**변경**: "3분할 카테고리 구조로 블로그 콘텐츠를 체계화하세요"

**수정 파일**: `app/templates/categories/manage.html`

---

## 2. 페이지 제목 이모지 제거

다음 페이지들의 제목 앞 이모지 제거:

| 페이지 | 현재 | 변경 |
|--------|------|------|
| 모듈 관리 | 📦 모듈 관리 | 모듈 관리 |
| 플로우 관리 | 🔄 플로우 관리 | 플로우 관리 |
| 오토런 | ⚡ 오토런 | 오토런 |

**수정 파일**:
- `app/templates/modules/list.html`
- `app/templates/flows/list.html`
- `app/templates/autorun/index.html`

---

## 3. 오토런 버튼 간격 확대

### 현재 문제
- 전체|⏸▶⏹ 버튼 간격이 너무 좁음
- PC에서도 좁고, 모바일에서 터치 시 오터치 가능성 높음

### 변경
- 버튼 간 간격 확대
- 모바일에서 터치 영역 충분히 확보

**예시**:
```html
<!-- 변경 전 -->
<div class="flex gap-1">

<!-- 변경 후 -->
<div class="flex gap-2 md:gap-3">
```

**수정 파일**: `app/templates/autorun/index.html`

---

## 4. 글로벌 요약탭 재작업 (핵심)

### 현재 문제점

1. 요약탭이 상시 표시되지 않음 (클릭해야 보임)
2. 확장 시 페이지가 아래로 밀림 (오버레이 방식이 아님)
3. 확장 범위가 전체 화면이 아님

### 올바른 요구사항

#### 4-1. 상시 표시되는 요약탭 (1줄)

- **위치**: 네비게이션 바 바로 아래, 모든 페이지에서 항상 표시
- **높이**: 약 48px (컴팩트한 1줄)
- **표시 정보**: 
  - 🔄 활성 플로우 수
  - 📝 활성 블로그 수  
  - ✏️ 오늘 생성 수
  - 📤 오늘 발행 수
  - (차후 추가) 키워드/제목 수집 수

**레이아웃**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🍔 BlogAuto                              [사용자] [로그아웃] │  ← 네비게이션
├─────────────────────────────────────────────────────────────┤
│  🔄 12  │  📝 8  │  ✏️ 24  │  📤 18                    [▼]  │  ← 요약탭 (항상 표시)
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    각 페이지 콘텐츠                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4-2. 확장 시 전체 화면 오버레이

- **클릭/터치**: 요약탭 클릭 시 대시보드 패널이 **전체 화면을 덮음**
- **페이지 밀림 X**: 기존 페이지는 그대로, 위에 오버레이로 덮임
- **확장 범위**: 전체 화면 (100vh)

**확장 시 레이아웃**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🍔 BlogAuto                              [사용자] [로그아웃] │  ← 네비게이션 (유지)
├─────────────────────────────────────────────────────────────┤
│  🔄 12  │  📝 8  │  ✏️ 24  │  📤 18                    [▲]  │  ← 요약탭 (유지)
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │              대시보드 패널 (전체 화면 덮음)               │ │
│ │                                                         │ │
│ │  • 상세 통계                                            │ │
│ │  • 블로그별 현황                                        │ │
│ │  • 플로우별 현황                                        │ │
│ │  • 최근 활동 로그                                       │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│     (뒤 페이지 콘텐츠는 dimmed 상태로 가려짐)                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 구현 가이드

### base.html 수정

```html
<body>
    <!-- 네비게이션 -->
    {% include 'components/nav.html' %}
    
    <!-- 글로벌 요약탭 (항상 표시) -->
    <div class="bg-white border-b border-gray-200 sticky top-16 z-40"
         x-data="globalSummary()">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-12 cursor-pointer"
                 @click="togglePanel()">
                <!-- 지표들 -->
                <div class="flex items-center gap-4 md:gap-6 text-sm">
                    <div class="flex items-center gap-1.5" title="활성 플로우">
                        <span>🔄</span>
                        <span class="font-medium" x-text="summary.active_flows">0</span>
                    </div>
                    <div class="flex items-center gap-1.5" title="활성 블로그">
                        <span>📝</span>
                        <span class="font-medium" x-text="summary.active_blogs">0</span>
                    </div>
                    <div class="flex items-center gap-1.5" title="오늘 생성">
                        <span>✏️</span>
                        <span class="font-medium" x-text="summary.today_created">0</span>
                    </div>
                    <div class="flex items-center gap-1.5" title="오늘 발행">
                        <span>📤</span>
                        <span class="font-medium" x-text="summary.today_published">0</span>
                    </div>
                </div>
                
                <!-- 확장/축소 버튼 -->
                <button class="p-2 hover:bg-gray-100 rounded-lg">
                    <svg :class="expanded ? 'rotate-180' : ''" 
                         class="w-5 h-5 text-gray-500 transition-transform" 
                         fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                </button>
            </div>
        </div>
        
        <!-- 확장 패널 (전체 화면 오버레이) -->
        <div x-show="expanded"
             x-transition:enter="transition ease-out duration-300"
             x-transition:enter-start="opacity-0"
             x-transition:enter-end="opacity-100"
             x-transition:leave="transition ease-in duration-200"
             x-transition:leave-start="opacity-100"
             x-transition:leave-end="opacity-0"
             class="fixed inset-0 z-50"
             style="top: 112px;"
             @keydown.escape.window="expanded = false"
             x-cloak>
            
            <!-- 오버레이 배경 -->
            <div class="absolute inset-0 bg-black/50" @click="expanded = false"></div>
            
            <!-- 대시보드 패널 -->
            <div class="absolute inset-0 bg-white overflow-y-auto">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    
                    <!-- 상세 통계 카드 -->
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <!-- 활성 플로우 상세 -->
                        <div class="bg-gray-50 rounded-xl p-4">
                            <div class="text-sm text-gray-500 mb-1">활성 플로우</div>
                            <div class="text-2xl font-bold" x-text="stats.active_flows">0</div>
                            <div class="text-xs text-gray-400">전체 <span x-text="stats.total_flows">0</span>개</div>
                        </div>
                        
                        <!-- 활성 블로그 상세 -->
                        <div class="bg-gray-50 rounded-xl p-4">
                            <div class="text-sm text-gray-500 mb-1">활성 블로그</div>
                            <div class="text-2xl font-bold" x-text="stats.active_blogs">0</div>
                            <div class="text-xs text-gray-400">
                                WP <span x-text="stats.wordpress_count">0</span> / 
                                BL <span x-text="stats.blogger_count">0</span>
                            </div>
                        </div>
                        
                        <!-- 오늘 생성 상세 -->
                        <div class="bg-gray-50 rounded-xl p-4">
                            <div class="text-sm text-gray-500 mb-1">오늘 생성</div>
                            <div class="text-2xl font-bold" x-text="stats.today_created">0</div>
                            <div class="text-xs text-gray-400">어제 <span x-text="stats.yesterday_created">0</span>개</div>
                        </div>
                        
                        <!-- 오늘 발행 상세 -->
                        <div class="bg-gray-50 rounded-xl p-4">
                            <div class="text-sm text-gray-500 mb-1">오늘 발행</div>
                            <div class="text-2xl font-bold" x-text="stats.today_published">0</div>
                            <div class="text-xs text-gray-400">어제 <span x-text="stats.yesterday_published">0</span>개</div>
                        </div>
                    </div>
                    
                    <!-- 최근 활동 -->
                    <div class="bg-gray-50 rounded-xl p-4">
                        <h3 class="font-semibold mb-4">최근 활동</h3>
                        <div class="space-y-3">
                            <template x-for="activity in activities" :key="activity.id">
                                <div class="flex items-start gap-3 text-sm">
                                    <span x-text="activity.icon"></span>
                                    <div>
                                        <p x-text="activity.message"></p>
                                        <p class="text-xs text-gray-400" x-text="activity.time"></p>
                                    </div>
                                </div>
                            </template>
                            <div x-show="activities.length === 0" class="text-center text-gray-500 py-4">
                                최근 활동이 없습니다
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- 메인 콘텐츠 -->
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
```

### Alpine.js 컴포넌트

```javascript
function globalSummary() {
    return {
        expanded: false,
        summary: {
            active_flows: 0,
            active_blogs: 0,
            today_created: 0,
            today_published: 0
        },
        stats: {},
        activities: [],
        
        init() {
            this.loadSummary();
        },
        
        async loadSummary() {
            try {
                const res = await fetch('/api/v1/dashboard/summary');
                this.summary = await res.json();
            } catch (e) {
                console.error('요약 로드 실패:', e);
            }
        },
        
        async togglePanel() {
            this.expanded = !this.expanded;
            if (this.expanded) {
                await this.loadDetailedStats();
            }
        },
        
        async loadDetailedStats() {
            try {
                const [statsRes, activitiesRes] = await Promise.all([
                    fetch('/api/v1/dashboard/stats'),
                    fetch('/api/v1/dashboard/activities')
                ]);
                this.stats = await statsRes.json();
                const activitiesData = await activitiesRes.json();
                this.activities = activitiesData.activities || [];
            } catch (e) {
                console.error('상세 통계 로드 실패:', e);
            }
        }
    }
}
```

---

## 📁 수정 파일 목록

| 파일 | 수정 내용 |
|------|----------|
| `app/templates/categories/manage.html` | 배경색 제거, 텍스트 변경 |
| `app/templates/modules/list.html` | 제목 이모지 제거 |
| `app/templates/flows/list.html` | 제목 이모지 제거 |
| `app/templates/autorun/index.html` | 제목 이모지 제거, 버튼 간격 확대 |
| `app/templates/base.html` | 글로벌 요약탭 재작업 |

---

## 🧪 테스트 항목

| # | 테스트 항목 | 확인 |
|---|------------|------|
| 1 | 카테고리 관리 타이틀/버튼 배경색 제거됨 | ☐ |
| 2 | "3분할 카테고리 구조"로 텍스트 변경됨 | ☐ |
| 3 | 모듈/플로우/오토런 제목에서 이모지 제거됨 | ☐ |
| 4 | 오토런 버튼 간격 확대됨 | ☐ |
| 5 | 모든 페이지에서 요약탭 1줄 항상 표시 | ☐ |
| 6 | 요약탭 클릭 시 전체 화면 오버레이로 확장 | ☐ |
| 7 | 페이지가 밀리지 않고 덮임 | ☐ |
| 8 | ESC/오버레이 클릭으로 닫기 | ☐ |

---

위 내용대로 수정해주세요.
