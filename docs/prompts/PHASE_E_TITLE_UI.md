# Phase E: 정식 제목 UI

> **Phase**: E  
> **목표**: 데이터 관리 페이지에 정식 제목 탭 추가  
> **의존성**: Phase D (제목 이동 모듈)

---

## 📋 작업 개요

데이터 관리 페이지에 "정식 제목" 탭을 추가하여 정식 제목을 관리할 수 있는 UI를 구현합니다.

---

## 📁 생성/수정할 파일
```
services/republish/app/
├── templates/
│   └── data_management/
│       ├── base.html              # 탭 구조 수정
│       └── titles_main.html       # 정식 제목 페이지 (신규)
├── routers/
│   └── data_management.py         # 라우터 수정
└── static/
    └── js/
        └── titles_main.js         # 정식 제목 JS (신규)
```

---

## 📝 작업 1: 탭 구조 수정

파일 위치: `app/templates/data_management/base.html` 또는 해당 탭 영역

### 탭 구조
```html
<!-- 데이터 관리 탭 -->
<div class="tabs">
    <a href="/data-management/temp-titles" 
       class="tab" 
       :class="{ 'active': currentTab === 'temp-titles' }">
        임시 제목
    </a>
    <a href="/data-management/titles" 
       class="tab"
       :class="{ 'active': currentTab === 'titles' }">
        정식 제목
    </a>
    <a href="/data-management/filters" 
       class="tab"
       :class="{ 'active': currentTab === 'filters' }">
        필터 설정
    </a>
</div>
```

---

## 📝 작업 2: titles_main.html 구현

파일 위치: `app/templates/data_management/titles_main.html`

### 템플릿 구조
```html
{% extends "base.html" %}
{% block title %}정식 제목 관리{% endblock %}

{% block content %}
<div x-data="titlesMainApp()" x-init="init()">
    
    <!-- 헤더 영역 -->
    <div class="flex justify-between items-center mb-4">
        <h1 class="text-2xl font-bold">정식 제목 관리</h1>
        
        <!-- 통계 -->
        <div class="flex gap-4 text-sm text-gray-600">
            <span>전체: <strong x-text="stats.total"></strong>개</span>
            <span>그룹: <strong x-text="stats.groups"></strong>개</span>
        </div>
    </div>
    
    <!-- 필터/검색 영역 -->
    <div class="bg-white rounded-lg shadow p-4 mb-4">
        <div class="flex flex-wrap gap-4">
            <!-- 카테고리 필터 -->
            <div>
                <label class="block text-sm font-medium mb-1">카테고리</label>
                <select x-model="filters.category_id" 
                        @change="loadTitles()"
                        class="border rounded px-3 py-2">
                    <option value="">전체</option>
                    <template x-for="cat in categories" :key="cat.id">
                        <option :value="cat.id" x-text="cat.name"></option>
                    </template>
                </select>
            </div>
            
            <!-- 보기 모드 -->
            <div>
                <label class="block text-sm font-medium mb-1">보기</label>
                <select x-model="filters.viewMode" 
                        @change="loadTitles()"
                        class="border rounded px-3 py-2">
                    <option value="all">전체 보기</option>
                    <option value="group">그룹별 보기</option>
                </select>
            </div>
            
            <!-- 검색 -->
            <div class="flex-1">
                <label class="block text-sm font-medium mb-1">검색</label>
                <input type="text" 
                       x-model="filters.search"
                       @keyup.enter="loadTitles()"
                       placeholder="제목 검색..."
                       class="border rounded px-3 py-2 w-full">
            </div>
            
            <!-- 검색 버튼 -->
            <div class="flex items-end">
                <button @click="loadTitles()" 
                        class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                    검색
                </button>
            </div>
        </div>
    </div>
    
    <!-- 액션 버튼 영역 -->
    <div class="flex justify-between items-center mb-4">
        <div class="flex gap-2">
            <!-- 선택 항목 액션 -->
            <button @click="moveSelectedToTemp()"
                    :disabled="selectedIds.length === 0"
                    class="px-3 py-1.5 bg-yellow-500 text-white rounded text-sm disabled:opacity-50">
                임시로 이동 (<span x-text="selectedIds.length"></span>)
            </button>
            <button @click="deleteSelected()"
                    :disabled="selectedIds.length === 0"
                    class="px-3 py-1.5 bg-red-500 text-white rounded text-sm disabled:opacity-50">
                삭제 (<span x-text="selectedIds.length"></span>)
            </button>
        </div>
        
        <div class="flex gap-2">
            <!-- 전체 선택 -->
            <button @click="selectAll()"
                    class="px-3 py-1.5 border rounded text-sm">
                전체 선택
            </button>
            <button @click="clearSelection()"
                    class="px-3 py-1.5 border rounded text-sm">
                선택 해제
            </button>
        </div>
    </div>
    
    <!-- 제목 목록 (전체 보기) -->
    <div x-show="filters.viewMode === 'all'" class="bg-white rounded-lg shadow">
        <table class="w-full">
            <thead class="bg-gray-50">
                <tr>
                    <th class="w-10 p-3">
                        <input type="checkbox" @change="toggleSelectAll($event)">
                    </th>
                    <th class="text-left p-3">제목</th>
                    <th class="w-32 p-3">카테고리</th>
                    <th class="w-24 p-3">그룹</th>
                    <th class="w-20 p-3">상태</th>
                    <th class="w-32 p-3">등록일</th>
                    <th class="w-24 p-3">액션</th>
                </tr>
            </thead>
            <tbody>
                <template x-for="title in titles" :key="title.id">
                    <tr class="border-t hover:bg-gray-50">
                        <td class="p-3 text-center">
                            <input type="checkbox" 
                                   :value="title.id"
                                   x-model="selectedIds">
                        </td>
                        <td class="p-3">
                            <div class="flex items-center gap-2">
                                <span x-show="title.is_representative" 
                                      class="text-yellow-500" title="대표 제목">★</span>
                                <span x-text="title.title"></span>
                            </div>
                        </td>
                        <td class="p-3 text-center text-sm" x-text="title.category_name || '-'"></td>
                        <td class="p-3 text-center">
                            <span x-show="title.group_count > 1" 
                                  class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs"
                                  x-text="title.group_count + '개'"></span>
                        </td>
                        <td class="p-3 text-center">
                            <span :class="{
                                'bg-green-100 text-green-800': title.status === 'active',
                                'bg-gray-100 text-gray-800': title.status === 'used'
                            }" class="px-2 py-0.5 rounded text-xs" x-text="title.status"></span>
                        </td>
                        <td class="p-3 text-center text-sm text-gray-500" 
                            x-text="formatDate(title.created_at)"></td>
                        <td class="p-3 text-center">
                            <button @click="editTitle(title)" 
                                    class="text-blue-500 hover:underline text-sm">수정</button>
                        </td>
                    </tr>
                </template>
                
                <!-- 빈 상태 -->
                <tr x-show="titles.length === 0">
                    <td colspan="7" class="p-8 text-center text-gray-500">
                        정식 제목이 없습니다.
                    </td>
                </tr>
            </tbody>
        </table>
        
        <!-- 페이지네이션 -->
        <div class="p-4 border-t flex justify-center">
            <nav class="flex gap-1">
                <button @click="goToPage(pagination.page - 1)"
                        :disabled="pagination.page <= 1"
                        class="px-3 py-1 border rounded disabled:opacity-50">
                    이전
                </button>
                <span class="px-3 py-1">
                    <span x-text="pagination.page"></span> / <span x-text="pagination.totalPages"></span>
                </span>
                <button @click="goToPage(pagination.page + 1)"
                        :disabled="pagination.page >= pagination.totalPages"
                        class="px-3 py-1 border rounded disabled:opacity-50">
                    다음
                </button>
            </nav>
        </div>
    </div>
    
    <!-- 그룹별 보기 -->
    <div x-show="filters.viewMode === 'group'" class="space-y-4">
        <template x-for="group in groups" :key="group.id">
            <div class="bg-white rounded-lg shadow">
                <!-- 그룹 헤더 (클릭하여 펼치기/접기) -->
                <div @click="toggleGroup(group.id)"
                     class="p-4 flex justify-between items-center cursor-pointer hover:bg-gray-50">
                    <div class="flex items-center gap-3">
                        <span x-text="expandedGroups.includes(group.id) ? '▼' : '▶'" 
                              class="text-gray-400"></span>
                        <span class="font-medium" x-text="group.representative_title"></span>
                        <span class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs"
                              x-text="group.title_count + '개'"></span>
                    </div>
                    <div class="flex items-center gap-4 text-sm text-gray-500">
                        <span x-text="group.location || '지역 없음'"></span>
                        <span x-text="group.category_name || '미분류'"></span>
                    </div>
                </div>
                
                <!-- 그룹 내 제목 목록 (펼침 상태일 때) -->
                <div x-show="expandedGroups.includes(group.id)" 
                     x-collapse
                     class="border-t">
                    <table class="w-full">
                        <tbody>
                            <template x-for="title in group.titles" :key="title.id">
                                <tr class="border-t hover:bg-gray-50">
                                    <td class="w-10 p-3 text-center">
                                        <input type="checkbox" 
                                               :value="title.id"
                                               x-model="selectedIds">
                                    </td>
                                    <td class="p-3">
                                        <div class="flex items-center gap-2">
                                            <span x-show="title.is_representative" 
                                                  class="text-yellow-500">★</span>
                                            <span x-text="title.title"></span>
                                            <span x-show="title.similarity_score"
                                                  class="text-xs text-gray-400"
                                                  x-text="'(' + title.similarity_score + '%)'"></span>
                                        </div>
                                    </td>
                                    <td class="w-32 p-3 text-center">
                                        <button x-show="!title.is_representative"
                                                @click="setAsRepresentative(group.id, title.id)"
                                                class="text-xs text-blue-500 hover:underline">
                                            대표로 설정
                                        </button>
                                    </td>
                                </tr>
                            </template>
                        </tbody>
                    </table>
                </div>
            </div>
        </template>
        
        <!-- 빈 상태 -->
        <div x-show="groups.length === 0" class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            그룹이 없습니다.
        </div>
    </div>
    
    <!-- 수정 모달 -->
    <div x-show="editModal.show" 
         class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
         @click.self="editModal.show = false">
        <div class="bg-white rounded-lg shadow-lg w-full max-w-lg p-6">
            <h3 class="text-lg font-bold mb-4">제목 수정</h3>
            
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium mb-1">제목</label>
                    <input type="text" 
                           x-model="editModal.title"
                           class="border rounded px-3 py-2 w-full">
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-1">카테고리</label>
                    <select x-model="editModal.category_id"
                            class="border rounded px-3 py-2 w-full">
                        <option value="">미분류</option>
                        <template x-for="cat in categories" :key="cat.id">
                            <option :value="cat.id" x-text="cat.name"></option>
                        </template>
                    </select>
                </div>
                
                <div>
                    <label class="block text-sm font-medium mb-1">상태</label>
                    <select x-model="editModal.status"
                            class="border rounded px-3 py-2 w-full">
                        <option value="active">활성</option>
                        <option value="used">사용됨</option>
                        <option value="disabled">비활성</option>
                    </select>
                </div>
            </div>
            
            <div class="flex justify-end gap-2 mt-6">
                <button @click="editModal.show = false"
                        class="px-4 py-2 border rounded">
                    취소
                </button>
                <button @click="saveTitle()"
                        class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                    저장
                </button>
            </div>
        </div>
    </div>
    
    <!-- 로딩 오버레이 -->
    <div x-show="loading" 
         class="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-6">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
            <p class="mt-2 text-gray-600">처리 중...</p>
        </div>
    </div>
    
</div>

<script src="/static/js/titles_main.js"></script>
{% endblock %}
```

---

## 📝 작업 3: titles_main.js 구현

파일 위치: `app/static/js/titles_main.js`
```javascript
/**
 * 정식 제목 관리 페이지 Alpine.js 앱
 */
function titlesMainApp() {
    return {
        // 상태
        loading: false,
        titles: [],
        groups: [],
        categories: [],
        selectedIds: [],
        expandedGroups: [],
        
        // 필터
        filters: {
            category_id: '',
            viewMode: 'all',
            search: ''
        },
        
        // 페이지네이션
        pagination: {
            page: 1,
            pageSize: 20,
            total: 0,
            totalPages: 0
        },
        
        // 통계
        stats: {
            total: 0,
            groups: 0
        },
        
        // 수정 모달
        editModal: {
            show: false,
            id: null,
            title: '',
            category_id: '',
            status: ''
        },
        
        // 초기화
        async init() {
            await this.loadCategories();
            await this.loadTitles();
            await this.loadStats();
        },
        
        // 카테고리 로드
        async loadCategories() {
            try {
                const response = await fetch('/api/v1/categories');
                const data = await response.json();
                this.categories = data.items || data;
            } catch (error) {
                console.error('카테고리 로드 실패:', error);
            }
        },
        
        // 제목 로드
        async loadTitles() {
            this.loading = true;
            try {
                const params = new URLSearchParams({
                    page: this.pagination.page,
                    page_size: this.pagination.pageSize,
                    group_view: this.filters.viewMode === 'group'
                });
                
                if (this.filters.category_id) {
                    params.append('category_id', this.filters.category_id);
                }
                if (this.filters.search) {
                    params.append('search', this.filters.search);
                }
                
                const response = await fetch(`/api/v1/titles?${params}`);
                const data = await response.json();
                
                if (this.filters.viewMode === 'group') {
                    this.groups = data.items || [];
                    this.titles = [];
                } else {
                    this.titles = data.items || [];
                    this.groups = [];
                }
                
                this.pagination.total = data.total || 0;
                this.pagination.totalPages = data.total_pages || 1;
                
            } catch (error) {
                console.error('제목 로드 실패:', error);
                this.showToast('제목을 불러오는데 실패했습니다.', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 통계 로드
        async loadStats() {
            try {
                const response = await fetch('/api/v1/titles/transfer/stats');
                const data = await response.json();
                this.stats = {
                    total: data.main_titles || 0,
                    groups: data.groups || 0
                };
            } catch (error) {
                console.error('통계 로드 실패:', error);
            }
        },
        
        // 페이지 이동
        goToPage(page) {
            if (page < 1 || page > this.pagination.totalPages) return;
            this.pagination.page = page;
            this.loadTitles();
        },
        
        // 선택 관련
        toggleSelectAll(event) {
            if (event.target.checked) {
                this.selectedIds = this.titles.map(t => t.id);
            } else {
                this.selectedIds = [];
            }
        },
        
        selectAll() {
            this.selectedIds = this.titles.map(t => t.id);
        },
        
        clearSelection() {
            this.selectedIds = [];
        },
        
        // 그룹 펼치기/접기
        toggleGroup(groupId) {
            const index = this.expandedGroups.indexOf(groupId);
            if (index > -1) {
                this.expandedGroups.splice(index, 1);
            } else {
                this.expandedGroups.push(groupId);
                this.loadGroupTitles(groupId);
            }
        },
        
        // 그룹 내 제목 로드
        async loadGroupTitles(groupId) {
            try {
                const response = await fetch(`/api/v1/titles/groups/${groupId}`);
                const data = await response.json();
                
                const group = this.groups.find(g => g.id === groupId);
                if (group) {
                    group.titles = data.titles || [];
                }
            } catch (error) {
                console.error('그룹 제목 로드 실패:', error);
            }
        },
        
        // 임시로 이동
        async moveSelectedToTemp() {
            if (this.selectedIds.length === 0) return;
            
            if (!confirm(`선택한 ${this.selectedIds.length}개의 제목을 임시 제목으로 이동하시겠습니까?`)) {
                return;
            }
            
            this.loading = true;
            try {
                const response = await fetch('/api/v1/titles/transfer/to-temp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title_ids: this.selectedIds })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.showToast(`${result.moved}개의 제목이 임시로 이동되었습니다.`, 'success');
                    this.selectedIds = [];
                    await this.loadTitles();
                    await this.loadStats();
                } else {
                    this.showToast('이동에 실패했습니다.', 'error');
                }
            } catch (error) {
                console.error('이동 실패:', error);
                this.showToast('이동 중 오류가 발생했습니다.', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 삭제
        async deleteSelected() {
            if (this.selectedIds.length === 0) return;
            
            if (!confirm(`선택한 ${this.selectedIds.length}개의 제목을 삭제하시겠습니까?`)) {
                return;
            }
            
            this.loading = true;
            try {
                const response = await fetch('/api/v1/titles/bulk-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.selectedIds)
                });
                
                if (response.ok) {
                    this.showToast('삭제되었습니다.', 'success');
                    this.selectedIds = [];
                    await this.loadTitles();
                    await this.loadStats();
                }
            } catch (error) {
                console.error('삭제 실패:', error);
                this.showToast('삭제 중 오류가 발생했습니다.', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 대표 제목 설정
        async setAsRepresentative(groupId, titleId) {
            this.loading = true;
            try {
                const response = await fetch(`/api/v1/titles/groups/${groupId}/representative`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_representative_id: titleId })
                });
                
                if (response.ok) {
                    this.showToast('대표 제목이 변경되었습니다.', 'success');
                    await this.loadGroupTitles(groupId);
                }
            } catch (error) {
                console.error('대표 변경 실패:', error);
                this.showToast('대표 변경 중 오류가 발생했습니다.', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 수정 모달 열기
        editTitle(title) {
            this.editModal = {
                show: true,
                id: title.id,
                title: title.title,
                category_id: title.category_id || '',
                status: title.status
            };
        },
        
        // 제목 저장
        async saveTitle() {
            this.loading = true;
            try {
                const response = await fetch(`/api/v1/titles/${this.editModal.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: this.editModal.title,
                        category_id: this.editModal.category_id || null,
                        status: this.editModal.status
                    })
                });
                
                if (response.ok) {
                    this.showToast('저장되었습니다.', 'success');
                    this.editModal.show = false;
                    await this.loadTitles();
                }
            } catch (error) {
                console.error('저장 실패:', error);
                this.showToast('저장 중 오류가 발생했습니다.', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 유틸리티
        formatDate(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleDateString('ko-KR');
        },
        
        showToast(message, type = 'info') {
            // 토스트 알림 구현 (기존 시스템 활용 또는 간단한 alert)
            alert(message);
        }
    };
}
```

---

## 📝 작업 4: 라우터 수정

파일 위치: `app/routers/data_management.py` (수정)
```python
# 기존 라우터에 추가

@router.get("/titles", response_class=HTMLResponse)
async def titles_main_page(request: Request):
    """정식 제목 관리 페이지"""
    return templates.TemplateResponse(
        "data_management/titles_main.html",
        {"request": request, "current_tab": "titles"}
    )
```

---

## ✅ 완료 조건

1. [ ] 탭 구조에 "정식 제목" 탭 추가
2. [ ] `titles_main.html` 구현 (< 400줄)
3. [ ] `titles_main.js` 구현 (< 300줄)
4. [ ] 라우터에 페이지 추가
5. [ ] 전체 보기 / 그룹별 보기 전환 기능
6. [ ] 제목 선택 → 임시로 이동/삭제 기능
7. [ ] 그룹 대표 제목 변경 기능
8. [ ] 제목 수정 모달 기능

---

## 🧪 테스트 케이스
```
1. 정식 제목 페이지 접속
   - URL: /data-management/titles
   - 탭 활성화 확인

2. 전체 보기
   - 제목 목록 표시
   - 페이지네이션 동작
   - 카테고리 필터 동작

3. 그룹별 보기
   - 그룹 접기/펼치기
   - 그룹 내 제목 표시
   - 대표 제목 표시 (★)

4. 제목 선택 → 임시로 이동
   - 체크박스 선택
   - 이동 버튼 클릭
   - 확인 후 이동 완료

5. 대표 제목 변경
   - 그룹 펼치기
   - "대표로 설정" 클릭
   - 대표 변경 확인

6. 제목 수정
   - 수정 버튼 클릭
   - 모달에서 수정
   - 저장 후 반영 확인
```

---

## 📚 참조

- 기존 UI: `app/templates/data_management/` 구조 참조
- 기존 JS 패턴: `app/static/js/` 참조
- Phase C: `app/api/titles.py`
- Phase D: `app/api/title_transfer.py`

---

**다음 Phase**: Phase F (테스트 및 튜닝)
