# Phase 7 추가 수정

## 📋 수정 사항

---

## 1. API 500 에러 수정

### 에러 발생 API
- `GET /api/v1/dashboard/summary` → 500 Error
- `GET /api/v1/dashboard/stats` → 500 Error
- `GET /api/v1/dashboard/activities` → 500 Error

### 원인 확인
`app/routers/dashboard.py` 파일에서 에러 원인 확인 필요

**수정 파일**: `app/routers/dashboard.py`

---

## 2. 버튼 스타일 통일

### 현재 카테고리 관리 버튼 (outline 스타일)
이 스타일을 다른 페이지에도 동일하게 적용

### 적용 대상
| 페이지 | PC 버튼 | 모바일 버튼 |
|--------|---------|-------------|
| 블로그 관리 | 블로그 추가 | 플로팅 + |
| 모듈 관리 | 모듈 추가 | 플로팅 + |
| 플로우 관리 | 플로우 추가 | 플로팅 + |
| 오토런 | (해당 없음) | (해당 없음) |

### 스타일 요구사항
- outline 스타일 (배경색 없음, 테두리만)
- **볼드체** 적용 (사각형, +, 텍스트 모두)

**수정 파일**:
- `app/templates/blogs/list.html`
- `app/templates/modules/list.html`
- `app/templates/flows/list.html`

---

## 3. 설명 메시지 삭제

### 제거 대상
모든 페이지의 제목 아래 설명 메시지 삭제

| 페이지 | 제거할 설명 메시지 |
|--------|-------------------|
| 카테고리 관리 | "3분할 카테고리 구조로 블로그 콘텐츠를 체계화하세요" |
| 블로그 관리 | (있다면 제거) |
| 모듈 관리 | (있다면 제거) |
| 플로우 관리 | (있다면 제거) |
| 오토런 | (있다면 제거) |

**수정 파일**:
- `app/templates/categories/manage.html`
- `app/templates/blogs/list.html`
- `app/templates/modules/list.html`
- `app/templates/flows/list.html`
- `app/templates/autorun/index.html`

---

## 4. 글로벌 요약탭 재작업 (핵심)

### 현재 문제점
1. 고정 영역이 너무 작음
2. 클릭 시 중앙 팝업 형태로 확장됨 (잘못됨)

### 올바른 요구사항

#### 4-1. 요약탭 크기 (축소 상태)

- **높이**: 기존 카드형태가 한 줄로 들어갈 수 있는 크기 (약 60~72px)
- **내용**: 4개 지표를 카드 스타일로 표시

**축소 상태 레이아웃**:
```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│ │🔄 활성   │ │📝 활성   │ │✏️ 오늘   │ │📤 오늘   │           [▼]  │
│ │플로우 12 │ │블로그 8  │ │생성 24   │ │발행 18   │                 │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘                 │
└──────────────────────────────────────────────────────────────────────┘
```

#### 4-2. 확장 방식 (하단 시트의 반대)

- **방향**: 상단에서 아래로 확장 (하단 시트가 아래에서 위로 확장되는 것의 반대)
- **확장 범위**: 화면 가장 아래까지 확장
- **기존 페이지**: 밀리지 않고 덮임 (오버레이)

**확장 상태 레이아웃**:
```
┌──────────────────────────────────────────────────────────────────────┐
│ 🍔 BlogAuto                                      [사용자] [로그아웃] │
├──────────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│ │🔄 활성   │ │📝 활성   │ │✏️ 오늘   │ │📤 오늘   │           [▲]  │
│ │플로우 12 │ │블로그 8  │ │생성 24   │ │발행 18   │                 │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │                     대시보드 상세 내용                          │ │
│  │                                                                │ │
│  │  • 상세 통계                                                   │ │
│  │  • 블로그별 현황                                               │ │
│  │  • 플로우별 현황                                               │ │
│  │  • 최근 활동 로그                                              │ │
│  │                                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  (기존 페이지 콘텐츠는 이 패널 뒤에 가려짐 - 밀리지 않음)            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4-3. 애니메이션

- **확장**: 상단에서 아래로 슬라이드 다운
- **축소**: 아래에서 상단으로 슬라이드 업

---

## 📝 구현 가이드

### base.html 요약탭 영역

```html
<!-- 글로벌 요약탭 (항상 표시) -->
<div class="bg-gray-50 border-b border-gray-200 sticky top-16 z-40"
     x-data="globalSummary()">
    
    <!-- 요약 카드 영역 (항상 표시) -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
        <div class="flex items-center justify-between">
            <!-- 4개 지표 카드 -->
            <div class="flex items-center gap-3 md:gap-4 overflow-x-auto">
                <!-- 활성 플로우 카드 -->
                <div class="flex items-center gap-2 bg-white px-3 py-2 rounded-lg border border-gray-200 min-w-fit">
                    <span class="text-lg">🔄</span>
                    <div>
                        <div class="text-xs text-gray-500">활성 플로우</div>
                        <div class="font-bold" x-text="summary.active_flows">0</div>
                    </div>
                </div>
                
                <!-- 활성 블로그 카드 -->
                <div class="flex items-center gap-2 bg-white px-3 py-2 rounded-lg border border-gray-200 min-w-fit">
                    <span class="text-lg">📝</span>
                    <div>
                        <div class="text-xs text-gray-500">활성 블로그</div>
                        <div class="font-bold" x-text="summary.active_blogs">0</div>
                    </div>
                </div>
                
                <!-- 오늘 생성 카드 -->
                <div class="flex items-center gap-2 bg-white px-3 py-2 rounded-lg border border-gray-200 min-w-fit">
                    <span class="text-lg">✏️</span>
                    <div>
                        <div class="text-xs text-gray-500">오늘 생성</div>
                        <div class="font-bold" x-text="summary.today_created">0</div>
                    </div>
                </div>
                
                <!-- 오늘 발행 카드 -->
                <div class="flex items-center gap-2 bg-white px-3 py-2 rounded-lg border border-gray-200 min-w-fit">
                    <span class="text-lg">📤</span>
                    <div>
                        <div class="text-xs text-gray-500">오늘 발행</div>
                        <div class="font-bold" x-text="summary.today_published">0</div>
                    </div>
                </div>
            </div>
            
            <!-- 확장/축소 버튼 -->
            <button @click="togglePanel()" 
                    class="p-2 hover:bg-gray-200 rounded-lg transition-colors flex-shrink-0">
                <svg :class="expanded ? 'rotate-180' : ''" 
                     class="w-5 h-5 text-gray-500 transition-transform" 
                     fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                </svg>
            </button>
        </div>
    </div>
    
    <!-- 확장 패널 (상단에서 아래로 확장) -->
    <div x-show="expanded"
         x-transition:enter="transition ease-out duration-300"
         x-transition:enter-start="opacity-0 -translate-y-full"
         x-transition:enter-end="opacity-100 translate-y-0"
         x-transition:leave="transition ease-in duration-200"
         x-transition:leave-start="opacity-100 translate-y-0"
         x-transition:leave-end="opacity-0 -translate-y-full"
         class="fixed left-0 right-0 bg-white border-b border-gray-200 shadow-lg overflow-y-auto z-50"
         style="top: 128px; bottom: 0;"
         @click.outside="expanded = false"
         @keydown.escape.window="expanded = false"
         x-cloak>
        
        <!-- 대시보드 상세 내용 -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            
            <!-- 상세 통계 카드 그리드 -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div class="bg-gray-50 rounded-xl p-4">
                    <div class="text-sm text-gray-500 mb-1">활성 플로우</div>
                    <div class="text-2xl font-bold" x-text="stats.active_flows || 0">0</div>
                    <div class="text-xs text-gray-400">전체 <span x-text="stats.total_flows || 0">0</span>개</div>
                </div>
                <div class="bg-gray-50 rounded-xl p-4">
                    <div class="text-sm text-gray-500 mb-1">활성 블로그</div>
                    <div class="text-2xl font-bold" x-text="stats.active_blogs || 0">0</div>
                    <div class="text-xs text-gray-400">
                        WP <span x-text="stats.wordpress_count || 0">0</span> / 
                        BL <span x-text="stats.blogger_count || 0">0</span>
                    </div>
                </div>
                <div class="bg-gray-50 rounded-xl p-4">
                    <div class="text-sm text-gray-500 mb-1">오늘 생성</div>
                    <div class="text-2xl font-bold" x-text="stats.today_created || 0">0</div>
                    <div class="text-xs text-gray-400">어제 <span x-text="stats.yesterday_created || 0">0</span>개</div>
                </div>
                <div class="bg-gray-50 rounded-xl p-4">
                    <div class="text-sm text-gray-500 mb-1">오늘 발행</div>
                    <div class="text-2xl font-bold" x-text="stats.today_published || 0">0</div>
                    <div class="text-xs text-gray-400">어제 <span x-text="stats.yesterday_published || 0">0</span>개</div>
                </div>
            </div>
            
            <!-- 최근 활동 -->
            <div class="bg-gray-50 rounded-xl p-4">
                <h3 class="font-semibold mb-4">최근 활동</h3>
                <div class="space-y-3 max-h-64 overflow-y-auto">
                    <template x-for="activity in activities" :key="activity.id">
                        <div class="flex items-start gap-3 text-sm">
                            <span x-text="activity.icon">🟢</span>
                            <div>
                                <p x-text="activity.message"></p>
                                <p class="text-xs text-gray-400" x-text="activity.time"></p>
                            </div>
                        </div>
                    </template>
                    <div x-show="!activities || activities.length === 0" class="text-center text-gray-500 py-4">
                        최근 활동이 없습니다
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- 오버레이 (확장 시 뒤 페이지 어둡게) -->
    <div x-show="expanded"
         x-transition:enter="transition ease-out duration-300"
         x-transition:enter-start="opacity-0"
         x-transition:enter-end="opacity-100"
         x-transition:leave="transition ease-in duration-200"
         x-transition:leave-start="opacity-100"
         x-transition:leave-end="opacity-0"
         class="fixed inset-0 bg-black/30 z-40"
         style="top: 128px;"
         @click="expanded = false"
         x-cloak>
    </div>
</div>
```

---

## 📁 수정 파일 목록

| 파일 | 수정 내용 |
|------|----------|
| `app/routers/dashboard.py` | API 500 에러 수정 |
| `app/templates/base.html` | 글로벌 요약탭 UI 재작업 |
| `app/templates/blogs/list.html` | 버튼 스타일 변경, 설명 메시지 제거 |
| `app/templates/modules/list.html` | 버튼 스타일 변경, 설명 메시지 제거 |
| `app/templates/flows/list.html` | 버튼 스타일 변경, 설명 메시지 제거 |
| `app/templates/categories/manage.html` | 설명 메시지 제거 |
| `app/templates/autorun/index.html` | 설명 메시지 제거 |

---

## 🧪 테스트 항목

| # | 테스트 항목 | 확인 |
|---|------------|------|
| 1 | API 에러 없이 정상 동작 | ☐ |
| 2 | 모든 페이지 버튼 outline+볼드 스타일 통일 | ☐ |
| 3 | 모든 페이지 설명 메시지 제거됨 | ☐ |
| 4 | 요약탭이 카드 형태로 한 줄에 표시 | ☐ |
| 5 | 확장 시 상단에서 아래로 슬라이드 | ☐ |
| 6 | 확장 시 화면 끝까지 확장 | ☐ |
| 7 | 기존 페이지가 밀리지 않고 덮임 | ☐ |

---

위 내용대로 수정해주세요. API 에러부터 먼저 수정해주세요.
