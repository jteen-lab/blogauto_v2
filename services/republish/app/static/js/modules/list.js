/**
 * 모듈 목록 페이지 JavaScript
 * Alpine.js 기반 상태 관리 및 API 통신
 */

function moduleListApp() {
    return {
        // 상태 데이터
        loading: false,
        modules: [],
        moduleTypes: [],

        // 캐시 시스템
        intervalTextCache: {},
        scheduleSummaryCache: {},

        // 정렬 상태
        sortBy: 'name',
        sortOrder: 'asc',

        // 초기화
        async init() {
            // 저장된 정렬 설정 로드
            this.loadSortPreference();

            this.loading = true;
            try {
                await Promise.all([
                    this.loadModuleTypes(),
                    this.loadModules()
                ]);
            } catch (error) {
                this.showError('데이터를 불러오는 중 오류가 발생했습니다');
                console.error('초기화 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 정렬 방향 토글
        toggleSortOrder() {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            this.saveSortPreference();
        },

        // 정렬 설정 저장 (localStorage)
        saveSortPreference() {
            try {
                localStorage.setItem('moduleSortBy', this.sortBy);
                localStorage.setItem('moduleSortOrder', this.sortOrder);
            } catch (e) {
                console.warn('정렬 설정 저장 실패:', e);
            }
        },

        // 정렬 설정 로드 (localStorage)
        loadSortPreference() {
            try {
                const savedSortBy = localStorage.getItem('moduleSortBy');
                const savedSortOrder = localStorage.getItem('moduleSortOrder');
                if (savedSortBy) {
                    this.sortBy = savedSortBy;
                }
                if (savedSortOrder) {
                    this.sortOrder = savedSortOrder;
                }
            } catch (e) {
                console.warn('정렬 설정 로드 실패:', e);
            }
        },

        // 정렬된 모듈 목록 반환
        getSortedModules(moduleList) {
            if (!moduleList || moduleList.length === 0) {
                return [];
            }

            const sorted = [...moduleList].sort((a, b) => {
                let valueA, valueB;

                switch (this.sortBy) {
                    case 'name':
                        valueA = (a.name || '').toLowerCase();
                        valueB = (b.name || '').toLowerCase();
                        return valueA.localeCompare(valueB, 'ko');

                    case 'created_at':
                        valueA = new Date(a.created_at || 0).getTime();
                        valueB = new Date(b.created_at || 0).getTime();
                        return valueA - valueB;

                    case 'updated_at':
                        valueA = new Date(a.updated_at || a.created_at || 0).getTime();
                        valueB = new Date(b.updated_at || b.created_at || 0).getTime();
                        return valueA - valueB;

                    case 'module_type':
                        const typeOrder = { 'prompt': 1, 'generate': 2, 'publish': 3, 'republish': 4, 'collect': 5, 'data': 6 };
                        valueA = typeOrder[a.module_type?.code] || 99;
                        valueB = typeOrder[b.module_type?.code] || 99;
                        return valueA - valueB;

                    default:
                        return 0;
                }
            });

            // 내림차순이면 역순
            if (this.sortOrder === 'desc') {
                sorted.reverse();
            }

            return sorted;
        },

        // 모듈 타입 목록 로드
        async loadModuleTypes() {
            const response = await fetch('/api/v1/module-types', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('모듈 타입 목록 조회 실패');
            }

            this.moduleTypes = await response.json();
        },

        // 모듈 목록 로드
        async loadModules() {
            const response = await fetch('/api/v1/modules', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('모듈 목록 조회 실패');
            }

            const data = await response.json();
            this.modules = data.modules || [];

            // 캐시 초기화
            this.intervalTextCache = {};
            this.scheduleSummaryCache = {};

            // 로딩 완료 후 동적 레이아웃 적용
            setTimeout(() => {
                this.applyDynamicLayout();
            }, 100);
        },

        // 타입별 모듈 목록 반환 (정렬 적용)
        getModulesByType(typeCode) {
            const filtered = this.modules.filter(module => module.module_type.code === typeCode);
            return this.getSortedModules(filtered);
        },

        // 타입별 모듈 개수 계산
        getModuleCountByType(typeCode) {
            return this.modules.filter(module => module.module_type.code === typeCode).length;
        },

        // 동적 섹션 레이아웃 적용
        applyDynamicLayout() {
            const moduleTypes = ['prompt', 'generate', 'publish', 'republish', 'collect', 'data'];
            const visibleSections = moduleTypes.filter(type => this.getModulesByType(type).length > 0);
            const sectionCount = visibleSections.length;

            console.log(`[applyDynamicLayout] 표시할 섹션 수: ${sectionCount}`);

            // 데스크탑 섹션 컨테이너 찾기
            const desktopSections = document.querySelector('.desktop-sections');
            if (!desktopSections) return;

            // 기존 클래스 제거
            desktopSections.classList.remove('sections-1', 'sections-2', 'sections-3', 'sections-4', 'sections-5', 'sections-6');

            // 섹션 수에 따른 클래스 추가
            desktopSections.classList.add(`sections-${sectionCount}`);

            // 각 섹션의 모듈 그리드에도 클래스 적용
            visibleSections.forEach(type => {
                const moduleGrid = document.querySelector(`[x-show*="getModulesByType('${type}')"] .module-grid`);
                if (moduleGrid) {
                    moduleGrid.classList.remove('grid-1', 'grid-2', 'grid-3', 'grid-4', 'grid-5', 'grid-6');
                    moduleGrid.classList.add(`grid-${sectionCount}`);
                }
            });

            // 레이아웃 적용 완료 후 표시
            setTimeout(() => {
                desktopSections.classList.add('layout-ready');
            }, 50);
        },

        // 모듈 아이콘 반환
        getModuleIcon(typeCode) {
            const icons = {
                republish: '🔄',
                publish: '📤',
                generate: '✨',
                prompt: '📝',
                collect: '🔍',
                data: '📊'
            };
            return icons[typeCode] || '📦';
        },

        // 모듈 타입 이름 반환
        getModuleTypeName(typeCode) {
            const type = this.moduleTypes.find(t => t.code === typeCode);
            if (type) return type.name;

            // 폴백 이름
            const fallbackNames = {
                'prompt': '프롬프트',
                'generate': '생성',
                'publish': '발행',
                'republish': '재발행',
                'collect': '수집',
                'data': '데이터'
            };
            return fallbackNames[typeCode] || typeCode;
        },


        // 전체 폼 템플릿
        getFullFormTemplate() {
            return `
                <div class="max-w-6xl mx-auto">
                    <form @submit.prevent="submitForm()">
                        <!-- 기본 정보 -->
                        <div class="space-y-6">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                모듈 이름 <span class="text-red-500">*</span>
                            </label>
                            <input type="text"
                                   x-model="formData.name"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                   placeholder="예: 재발행 모듈 A"
                                   required>
                            <p class="mt-1 text-xs text-gray-500">모듈을 구분할 수 있는 이름을 입력하세요</p>
                        </div>

                        <!-- 설명 -->
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">설명 (선택)</label>
                            <textarea x-model="formData.description"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                      rows="3"
                                      placeholder="모듈에 대한 설명을 입력하세요...">
                            </textarea>
                        </div>

                        <!-- 타입별 설정 -->
                        <div x-show="formData.type_code === 'republish'">
                            <!-- 재발행 조건 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    🎯 재발행 조건
                                </h3>

                                <!-- 재발행 가능 최소 포스트 수 -->
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        재발행 가능 최소 포스트 수
                                    </label>
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <input type="number"
                                               x-model.number="formData.min_post_count"
                                               min="1"
                                               max="1000"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                        <span class="text-gray-500 text-sm">개 이상일 때 재발행 시작</span>
                                    </div>
                                    <p class="mt-1 text-xs text-gray-500">블로그에 최소 이만큼의 포스트가 누적되어야 재발행이 활성화됩니다</p>
                                </div>

                                <!-- 재발행 적용 구간 -->
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        재발행 적용 구간 (누적 포스트 수 기준)
                                    </label>
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="text-gray-500 text-sm">시작</span>
                                        <input type="number"
                                               x-model.number="formData.post_range_start"
                                               min="1"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                        <span class="text-gray-500">~</span>
                                        <span class="text-gray-500 text-sm">종료</span>
                                        <input type="number"
                                               x-model.number="formData.post_range_end"
                                               min="1"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                               placeholder="무제한">
                                        <span class="text-gray-400 text-xs">(비워두면 무제한)</span>
                                    </div>
                                    <p class="mt-1 text-xs text-gray-500">블로그에 누적된 포스트 수가 해당 범위일 때만 프로파일이 적용됩니다. 예: 누적 포스트가 1~100인 블로그에만 적용, 초과 시 미적용</p>
                                </div>
                            </div>

                            <!-- 재발행 간격 설정 -->
                            <div>
                                <label class="block text-sm font-semibold text-gray-900 mb-3">
                                    재발행 간격 설정 (하루 기준)
                                </label>

                                <!-- 간격 설정 모드 선택 -->
                                <div class="flex gap-4 mb-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.interval_mode"
                                               value="manual"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">시간으로 설정</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.interval_mode"
                                               value="auto"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">횟수로 설정</span>
                                    </label>
                                </div>

                                <!-- Manual 모드: 간격(분) 입력 -->
                                <div x-show="formData.interval_mode === 'manual'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="text-gray-700 text-sm">재발행 간격:</span>
                                        <input type="number"
                                               x-model.number="formData.manual_interval_minutes"
                                               min="15"
                                               max="1440"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                               @input="calculateFromInterval()">
                                        <span class="text-gray-500 text-sm">분</span>
                                        <span class="text-gray-400">/</span>
                                        <span class="text-gray-500 text-sm">하루 최대:</span>
                                        <span class="font-semibold text-blue-600" x-text="calculatedDailyCount + '회'"></span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 기준으로 계산됩니다 (오늘 활성 시간: <span x-text="todayActiveHours"></span>시간)</p>
                                </div>

                                <!-- Auto 모드: 하루 목표 횟수 입력 -->
                                <div x-show="formData.interval_mode === 'auto'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2 flex-wrap">
                                        <span class="text-gray-700 text-sm">하루 목표:</span>
                                        <input type="number"
                                               x-model.number="formData.auto_daily_count"
                                               min="1"
                                               max="100"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                               @input="calculateFromDailyCount()">
                                        <span class="text-gray-500 text-sm">회</span>
                                        <span class="text-gray-400">/</span>
                                        <span class="text-gray-500 text-sm">최소 간격:</span>
                                        <span class="font-semibold text-blue-600" x-text="calculatedInterval + '분'"></span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 기준으로 간격이 자동 계산됩니다 (오늘 활성 시간: <span x-text="todayActiveHours"></span>시간)</p>
                                </div>

                                <div class="mt-2 flex items-center gap-2 text-xs text-blue-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                    </svg>
                                    <span>최소 15분 이상 간격이 유지되도록 설정됩니다</span>
                                </div>
                            </div>

                            <!-- 스케줄 매트릭스 -->
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">스케줄 설정</label>
                                <div class="bg-gray-50 rounded-lg p-4">
                                    <!-- 빠른 설정 버튼과 통계 -->
                                    <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
                                        <div class="flex flex-wrap gap-2">
                                            <button type="button"
                                                    @click="selectAllHours()"
                                                    class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                                                전체 선택
                                            </button>
                                            <button type="button"
                                                    @click="clearAllHours()"
                                                    class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                                                전체 해제
                                            </button>
                                            <button type="button"
                                                    @click="selectWorkingHours()"
                                                    class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                                                평일 9-21시
                                            </button>
                                        </div>

                                        <!-- 활성 시간 요약 (간단) -->
                                        <div class="flex items-center gap-4 text-sm">
                                            <span class="text-blue-800 font-medium">
                                                활성: <span x-text="activeHoursCount"></span>시간/주
                                            </span>
                                            <span class="text-blue-600" x-show="todayActiveHours > 0">
                                                오늘: <span x-text="todayActiveHours"></span>시간
                                            </span>
                                            <span class="text-blue-600" x-show="expectedDailyPosts > 0">
                                                예상 일일 발행: 약 <span x-text="expectedDailyPosts"></span>회
                                            </span>
                                        </div>
                                    </div>

                                    <p class="text-xs text-gray-500 mb-3">
                                        파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 전체 선택/해제
                                    </p>

                                    <!-- 스케줄 테이블 -->
                                    <div class="overflow-x-auto">
                                        <table class="w-full text-xs border-collapse">
                                            <thead>
                                                <tr>
                                                    <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                                    <template x-for="(day, dayIdx) in days" :key="dayIdx">
                                                        <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                                            @click="toggleDay(dayIdx)"
                                                            x-text="day">
                                                        </th>
                                                    </template>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <template x-for="hour in 24" :key="hour">
                                                    <tr>
                                                        <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                                            x-text="String(hour-1).padStart(2, '0') + '시'">
                                                        </td>
                                                        <template x-for="(day, dayIdx) in days" :key="dayIdx + '-' + hour">
                                                            <td class="border border-gray-300 p-0">
                                                                <button type="button"
                                                                        class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                                                        :class="schedule[dayIdx][hour-1] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'"
                                                                        @click="toggleHour(dayIdx, hour-1)">
                                                                </button>
                                                            </td>
                                                        </template>
                                                    </tr>
                                                </template>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 수집 모듈 설정 -->
                        <div x-show="formData.type_code === 'collect'">
                            <!-- API 상태 안내 -->
                            <div class="mb-6 p-4 rounded-lg" :class="hasRequiredAPI() ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'">
                                <div class="flex items-start gap-3">
                                    <span x-show="hasRequiredAPI()" class="text-green-600 text-xl">✅</span>
                                    <span x-show="!hasRequiredAPI()" class="text-red-600 text-xl">⚠️</span>
                                    <div>
                                        <p class="font-medium" :class="hasRequiredAPI() ? 'text-green-800' : 'text-red-800'">
                                            <span x-show="hasRequiredAPI()">API 설정 완료</span>
                                            <span x-show="!hasRequiredAPI()">필수 API 미설정</span>
                                        </p>
                                        <p class="text-sm mt-1" :class="hasRequiredAPI() ? 'text-green-700' : 'text-red-700'">
                                            <span x-show="hasRequiredAPI()">네이버 광고 API가 설정되어 연관검색어 확장이 가능합니다.</span>
                                            <span x-show="!hasRequiredAPI()">수집 모듈 저장을 위해 <strong>네이버 광고 API</strong>가 필요합니다. 설정 메뉴에서 API 키를 등록해주세요.</span>
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <!-- 수집 대상 설정 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    📊 수집 대상 설정
                                </h3>
                                <p class="text-xs text-gray-500 -mt-2">수집할 데이터 소스를 선택하세요</p>

                                <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                    <!-- 네이버 뉴스 -->
                                    <div class="flex items-center p-3 border rounded-lg transition-colors cursor-pointer"
                                         :class="apiStatus.naver_news
                                                 ? (formData.source_naver_news ? 'border-purple-500 bg-purple-50' : 'border-gray-200 hover:bg-gray-50')
                                                 : 'border-gray-200 bg-gray-100 opacity-60 cursor-not-allowed'"
                                         @click="if(apiStatus.naver_news) formData.source_naver_news = !formData.source_naver_news">
                                        <input type="checkbox"
                                               :checked="formData.source_naver_news"
                                               :disabled="!apiStatus.naver_news"
                                               class="rounded text-purple-600 focus:ring-purple-500 pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">네이버 뉴스</span>
                                            <span x-show="!apiStatus.naver_news" class="block text-xs text-red-500">API 미등록</span>
                                            <span x-show="apiStatus.naver_news" class="block text-xs text-blue-600">제목 수집</span>
                                        </div>
                                    </div>

                                    <!-- 구글 뉴스 RSS -->
                                    <div class="flex items-center p-3 border rounded-lg transition-colors cursor-pointer"
                                         :class="formData.source_google_news ? 'border-purple-500 bg-purple-50' : 'border-gray-200 hover:bg-gray-50'"
                                         @click="formData.source_google_news = !formData.source_google_news">
                                        <input type="checkbox"
                                               :checked="formData.source_google_news"
                                               class="rounded text-purple-600 focus:ring-purple-500 pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">구글 뉴스</span>
                                            <span class="block text-xs text-blue-600">제목 수집</span>
                                        </div>
                                    </div>

                                    <!-- 네이버 웹문서 -->
                                    <div class="flex items-center p-3 border rounded-lg transition-colors cursor-pointer"
                                         :class="apiStatus.naver_webdoc
                                                 ? (formData.source_naver_webdoc ? 'border-purple-500 bg-purple-50' : 'border-gray-200 hover:bg-gray-50')
                                                 : 'border-gray-200 bg-gray-100 opacity-60 cursor-not-allowed'"
                                         @click="if(apiStatus.naver_webdoc) formData.source_naver_webdoc = !formData.source_naver_webdoc">
                                        <input type="checkbox"
                                               :checked="formData.source_naver_webdoc"
                                               :disabled="!apiStatus.naver_webdoc"
                                               class="rounded text-purple-600 focus:ring-purple-500 pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">네이버 웹문서</span>
                                            <span x-show="!apiStatus.naver_webdoc" class="block text-xs text-red-500">API 미등록</span>
                                            <span x-show="apiStatus.naver_webdoc" class="block text-xs text-blue-600">제목 수집</span>
                                        </div>
                                    </div>
                                </div>

                                <p class="text-xs text-gray-500">
                                    <svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                    </svg>
                                    네이버 뉴스 API는 설정 → API 설정 → <strong>네이버 검색 API</strong>에서 등록하세요
                                </p>
                            </div>

                            <!-- 수집 유형 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    📋 수집 유형
                                </h3>
                                <div class="flex gap-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" x-model="formData.collect_type" value="keyword" class="text-purple-600 focus:ring-purple-500">
                                        <span class="ml-2 text-sm">키워드만</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" x-model="formData.collect_type" value="title" class="text-purple-600 focus:ring-purple-500">
                                        <span class="ml-2 text-sm">제목만</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" x-model="formData.collect_type" value="both" class="text-purple-600 focus:ring-purple-500">
                                        <span class="ml-2 text-sm">키워드+제목 모두</span>
                                    </label>
                                </div>
                            </div>

                            <!-- 추가 옵션 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    ⚙️ 추가 옵션
                                </h3>
                                <div class="space-y-3">
                                    <label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                           :class="formData.enable_related_search ? 'border-purple-500 bg-purple-50' : 'border-gray-200'">
                                        <input type="checkbox" x-model="formData.enable_related_search" class="rounded text-purple-600 focus:ring-purple-500">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium">연관검색 확장</span>
                                            <p class="text-xs text-gray-500">수집된 키워드의 연관검색어도 함께 수집합니다</p>
                                        </div>
                                    </label>
                                    <label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                           :class="formData.enable_title_extraction ? 'border-purple-500 bg-purple-50' : 'border-gray-200'">
                                        <input type="checkbox" x-model="formData.enable_title_extraction" class="rounded text-purple-600 focus:ring-purple-500">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium">제목 자동 추출</span>
                                            <p class="text-xs text-gray-500">네이버 뉴스/웹문서에서 제목을 자동 수집합니다</p>
                                        </div>
                                    </label>
                                </div>
                            </div>

                            <!-- 키워드 추출 옵션 (제목 → 키워드) - 키워드만 선택 시 비활성화 -->
                            <!-- x-effect로 키워드만 선택 시 자동 비활성화 -->
                            <div x-effect="if (formData.collect_type === 'keyword') formData.enable_keyword_extraction = false"></div>
                            <div class="space-y-4 mb-6" x-show="formData.collect_type !== 'keyword'" x-transition>
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    🔑 키워드 추출 (제목 → 키워드)
                                </h3>

                                <div class="space-y-4">
                                    <!-- 키워드 추출 활성화 -->
                                    <label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                                           :class="formData.enable_keyword_extraction ? 'border-green-500 bg-green-50' : 'border-gray-200'">
                                        <input type="checkbox" x-model="formData.enable_keyword_extraction" class="rounded text-green-600 focus:ring-green-500">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium">제목에서 키워드 자동 추출</span>
                                            <p class="text-xs text-gray-500">수집된 제목을 분석하여 핵심 키워드를 추출하고 저장합니다</p>
                                        </div>
                                    </label>

                                    <!-- 키워드 추출 상세 옵션 (활성화시에만 표시) -->
                                    <div x-show="formData.enable_keyword_extraction" x-transition class="p-4 bg-green-50 rounded-lg space-y-4">
                                        <!-- 추출 방법 선택 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">추출 방법</label>
                                            <select x-model="formData.keyword_extraction_method"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent">
                                                <option value="all">통합 (모든 방법)</option>
                                                <option value="konlpy">형태소 분석 (명사 추출)</option>
                                                <option value="tfidf">TF-IDF 핵심 키워드</option>
                                                <option value="ngram">N-gram 빈도 분석</option>
                                            </select>
                                            <p class="mt-1 text-xs text-gray-500">
                                                <span x-show="formData.keyword_extraction_method === 'all'">KoNLPy + TF-IDF + N-gram 통합 분석</span>
                                                <span x-show="formData.keyword_extraction_method === 'konlpy'">한국어 형태소 분석으로 명사 추출</span>
                                                <span x-show="formData.keyword_extraction_method === 'tfidf'">문서 빈도 역수 가중치 기반 핵심어 추출</span>
                                                <span x-show="formData.keyword_extraction_method === 'ngram'">연속 단어 조합 빈도 분석</span>
                                            </p>
                                        </div>

                                        <!-- 분석할 제목 수 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">분석할 제목 수</label>
                                            <div class="flex items-center gap-2">
                                                <input type="number"
                                                       x-model.number="formData.keyword_extraction_title_limit"
                                                       min="10"
                                                       max="500"
                                                       class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent">
                                                <span class="text-gray-500 text-sm">개의 제목에서</span>
                                            </div>
                                        </div>

                                        <!-- 추출할 키워드 수 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">추출할 키워드 수</label>
                                            <div class="flex items-center gap-2">
                                                <input type="number"
                                                       x-model.number="formData.keyword_extraction_limit"
                                                       min="10"
                                                       max="200"
                                                       class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent">
                                                <span class="text-gray-500 text-sm">개 키워드 추출</span>
                                            </div>
                                        </div>

                                        <div class="p-3 bg-green-100 rounded-lg">
                                            <p class="text-xs text-green-800">
                                                📝 수집 완료 후 임시 제목에서 키워드를 자동으로 추출하여 키워드 탭에 저장합니다.<br>
                                                불용어 필터링이 자동 적용되며, 추출된 키워드는 source_type="extracted"로 구분됩니다.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- 수집 수량 설정 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    📊 수집 수량 설정
                                </h3>
                                <p class="text-xs text-gray-500 -mt-2">수집 유형을 선택하고 수량을 설정합니다 (중복 선택 가능)</p>

                                <!-- 일반 수집 -->
                                <div class="border border-gray-200 rounded-lg overflow-hidden">
                                    <div class="flex items-center p-3 bg-gray-50 border-b border-gray-200 cursor-pointer"
                                         @click="formData.enable_normal_collect = !formData.enable_normal_collect">
                                        <input type="checkbox"
                                               x-model="formData.enable_normal_collect"
                                               class="rounded text-purple-600 focus:ring-purple-500 pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium">📋 일반 수집</span>
                                            <p class="text-xs text-gray-500">키워드/제목별 수집 수량 제한</p>
                                        </div>
                                    </div>
                                    <div x-show="formData.enable_normal_collect" x-transition class="p-4 bg-white">
                                        <div class="grid grid-cols-2 gap-4">
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">🔑 키워드 수집</label>
                                                <div class="flex items-center gap-2">
                                                    <input type="number" x-model.number="formData.keyword_collect_limit" min="10" max="1000"
                                                           class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                    <span class="text-sm text-gray-500">개</span>
                                                </div>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">📝 제목 수집</label>
                                                <div class="flex items-center gap-2">
                                                    <input type="number" x-model.number="formData.title_collect_limit" min="10" max="1000"
                                                           class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                    <span class="text-sm text-gray-500">개</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- 대량 수집 -->
                                <div class="border border-gray-200 rounded-lg overflow-hidden">
                                    <div class="flex items-center p-3 bg-gray-50 border-b border-gray-200 cursor-pointer"
                                         @click="formData.enable_bulk_collect = !formData.enable_bulk_collect">
                                        <input type="checkbox"
                                               x-model="formData.enable_bulk_collect"
                                               class="rounded text-orange-600 focus:ring-orange-500 pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium">🚀 대량 수집</span>
                                            <p class="text-xs text-gray-500">블로그/사이트의 전체 포스트 제목 수집 (수량 제한 없음)</p>
                                        </div>
                                    </div>
                                    <div x-show="formData.enable_bulk_collect" x-transition class="p-4 bg-white">
                                        <div class="p-3 bg-orange-50 rounded-lg mb-3">
                                            <p class="text-xs text-orange-800">
                                                ⚠️ 키워드 검색 결과의 블로그/사이트에서 <strong>전체 포스트 제목</strong>을 수집합니다.<br>
                                                • 네이버 블로그: 검색 API로 수집<br>
                                                • 티스토리/워드프레스 등: RSS 피드로 수집<br>
                                                • 도메인 필터가 적용되어 차단된 사이트는 제외됩니다
                                            </p>
                                        </div>
                                        <div class="grid grid-cols-2 gap-4">
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">🔢 주기당 처리 URL 수</label>
                                                <div class="flex items-center gap-2">
                                                    <input type="number" x-model.number="formData.bulk_urls_per_cycle" min="1" max="10" step="1"
                                                           class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500">
                                                    <span class="text-sm text-gray-500">개</span>
                                                </div>
                                                <p class="text-xs text-gray-400 mt-1">수집 주기마다 제목을 수집할 URL 수</p>
                                            </div>
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">🕐 사이트 간 딜레이</label>
                                                <div class="flex items-center gap-2">
                                                    <input type="number" x-model.number="formData.bulk_collect_delay" min="0.1" max="5" step="0.1"
                                                           class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500">
                                                    <span class="text-sm text-gray-500">초</span>
                                                </div>
                                                <p class="text-xs text-gray-400 mt-1">각 블로그/사이트 수집 사이의 대기 시간</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- 수집 스케줄 모드 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center">
                                    🕐 수집 스케줄
                                </h3>

                                <div class="flex gap-4 mb-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" x-model="formData.collect_schedule_mode" value="fixed_time" class="text-purple-600 focus:ring-purple-500">
                                        <span class="ml-2 text-sm">고정 시간 (권장)</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio" x-model="formData.collect_schedule_mode" value="interval" class="text-purple-600 focus:ring-purple-500">
                                        <span class="ml-2 text-sm">간격 기반</span>
                                    </label>
                                </div>

                                <!-- 고정 시간 모드 -->
                                <div x-show="formData.collect_schedule_mode === 'fixed_time'" class="p-4 bg-purple-50 rounded-lg">
                                    <label class="block text-sm font-medium text-gray-700 mb-2">수집 시간 설정</label>
                                    <div class="flex flex-wrap gap-2 mb-3">
                                        <template x-for="(time, idx) in formData.collect_fixed_times" :key="idx">
                                            <span class="inline-flex items-center px-3 py-1 bg-purple-200 text-purple-800 rounded-full text-sm">
                                                <span x-text="time"></span>
                                                <button type="button" @click="removeFixedTime(time)" class="ml-2 text-purple-600 hover:text-purple-800">×</button>
                                            </span>
                                        </template>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <input type="time" x-model="newFixedTime"
                                               class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                        <button type="button" @click="addFixedTime()"
                                                class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm">
                                            추가
                                        </button>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">매일 지정된 시간에 수집을 실행합니다</p>
                                </div>

                                <!-- 간격 모드 -->
                                <div x-show="formData.collect_schedule_mode === 'interval'" class="p-4 bg-purple-50 rounded-lg">
                                    <div class="flex items-center gap-2">
                                        <span class="text-gray-700 text-sm">수집 간격:</span>
                                        <input type="number" x-model.number="formData.collect_interval_hours" min="1" max="24"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                        <span class="text-gray-500 text-sm">시간마다</span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 내에서 지정된 간격으로 수집을 실행합니다</p>
                                </div>
                            </div>

                            <!-- 활성 시간대 (스케줄 매트릭스) -->
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">활성 시간대</label>
                                <div class="bg-gray-50 rounded-lg p-4">
                                    <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
                                        <div class="flex flex-wrap gap-2">
                                            <button type="button" @click="selectAllHours()"
                                                    class="px-3 py-1 text-xs bg-purple-100 text-purple-800 rounded-full hover:bg-purple-200">
                                                전체 선택 (24시간)
                                            </button>
                                            <button type="button" @click="clearAllHours()"
                                                    class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                                                전체 해제
                                            </button>
                                            <button type="button" @click="selectWorkingHours()"
                                                    class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                                                평일 9-21시
                                            </button>
                                        </div>
                                        <div class="flex items-center gap-4 text-sm">
                                            <span class="text-purple-800 font-medium">
                                                활성: <span x-text="activeHoursCount"></span>시간/주
                                            </span>
                                        </div>
                                    </div>
                                    <p class="text-xs text-gray-500 mb-3">
                                        보라색 = 활성 (수집 가능), 회색 = 비활성
                                    </p>
                                    <div class="overflow-x-auto">
                                        <table class="w-full text-xs border-collapse">
                                            <thead>
                                                <tr>
                                                    <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                                    <template x-for="(day, dayIdx) in days" :key="dayIdx">
                                                        <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                                            @click="toggleDay(dayIdx)" x-text="day"></th>
                                                    </template>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <template x-for="hour in 24" :key="hour">
                                                    <tr>
                                                        <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                                            x-text="String(hour-1).padStart(2, '0') + '시'"></td>
                                                        <template x-for="(day, dayIdx) in days" :key="dayIdx + '-' + hour">
                                                            <td class="border border-gray-300 p-0">
                                                                <button type="button"
                                                                        class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                                                        :class="schedule[dayIdx][hour-1] ? 'bg-purple-500 hover:bg-purple-600' : 'bg-gray-100 hover:bg-gray-200'"
                                                                        @click="toggleHour(dayIdx, hour-1)"></button>
                                                            </td>
                                                        </template>
                                                    </tr>
                                                </template>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 데이터 모듈 설정 -->
                        <div x-show="formData.type_code === 'data'">
                            <!-- 실행 방식 선택 (라디오 버튼으로 상호 배타적 선택) -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    🔄 실행 방식 선택
                                </h3>
                                <p class="text-xs text-gray-500 mb-3">수집 모듈 연동 또는 데이터 이동 스케줄 중 하나를 선택하세요.</p>

                                <!-- 실행 방식 라디오 버튼 -->
                                <div class="space-y-3">
                                    <!-- 옵션 1: 수집 모듈 연동 -->
                                    <div class="p-4 rounded-lg border-2 cursor-pointer transition-all"
                                         :class="formData.execution_mode === 'collection_link' ? 'bg-teal-50 border-teal-400' : 'bg-white border-gray-200 hover:border-gray-300'"
                                         @click="formData.execution_mode = 'collection_link'">
                                        <label class="flex items-center cursor-pointer">
                                            <input type="radio"
                                                   x-model="formData.execution_mode"
                                                   value="collection_link"
                                                   class="w-4 h-4 text-teal-600 focus:ring-teal-500">
                                            <span class="ml-2 text-sm font-medium text-gray-700">🔗 수집 모듈 연동</span>
                                        </label>
                                        <p class="mt-1 ml-6 text-xs text-gray-500">동일 플로우 내 수집 모듈이 완료되면 자동으로 제목 이동을 수행합니다</p>
                                    </div>

                                    <!-- 옵션 2: 데이터 이동 스케줄 -->
                                    <div class="p-4 rounded-lg border-2 cursor-pointer transition-all"
                                         :class="formData.execution_mode === 'schedule' ? 'bg-blue-50 border-blue-400' : 'bg-white border-gray-200 hover:border-gray-300'"
                                         @click="formData.execution_mode = 'schedule'">
                                        <label class="flex items-center cursor-pointer">
                                            <input type="radio"
                                                   x-model="formData.execution_mode"
                                                   value="schedule"
                                                   class="w-4 h-4 text-blue-600 focus:ring-blue-500">
                                            <span class="ml-2 text-sm font-medium text-gray-700">⏰ 데이터 이동 스케줄</span>
                                        </label>
                                        <p class="mt-1 ml-6 text-xs text-gray-500">설정된 스케줄에 따라 독립적으로 제목 이동을 수행합니다</p>
                                    </div>
                                </div>
                            </div>

                            <!-- 수집 모듈 연동 설정 (연동 모드 선택 시만 표시) -->
                            <div x-show="formData.execution_mode === 'collection_link'" x-transition class="space-y-4 mb-6 pl-4 border-l-2 border-teal-200">
                                <h4 class="text-sm font-semibold text-gray-800 flex items-center gap-2">
                                    🔗 수집 모듈 연동 설정
                                </h4>

                                <!-- 연동할 수집 모듈 선택 -->
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">연동할 수집 모듈</label>
                                    <div class="p-3 bg-teal-50 rounded-lg border border-teal-200">
                                        <span class="text-sm text-teal-800">📌 동일 플로우에 추가된 수집 모듈</span>
                                        <p class="mt-1 text-xs text-gray-500">이 데이터 모듈과 같은 플로우에 수집 모듈을 추가해야 합니다</p>
                                    </div>
                                </div>

                                <!-- 완료 후 대기 시간 -->
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">수집 완료 후 대기 시간</label>
                                    <div class="flex items-center gap-2">
                                        <input type="number"
                                               x-model.number="formData.collection_link_delay"
                                               min="0"
                                               max="300"
                                               class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent">
                                        <span class="text-sm text-gray-500">초</span>
                                    </div>
                                    <p class="mt-1 text-xs text-gray-500">수집 모듈 완료 후 제목 이동까지 대기할 시간 (기본: 30초)</p>
                                </div>

                                <!-- 경고 메시지 -->
                                <div class="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                                    <p class="text-xs text-yellow-800">
                                        ⚠️ <strong>주의:</strong> 플로우에 수집 모듈이 없으면 테스트/오토런 실행 시 경고가 표시됩니다.
                                    </p>
                                </div>
                            </div>

                            <!-- 데이터 이동 스케줄 설정 (스케줄 모드 선택 시만 표시) -->
                            <div x-show="formData.execution_mode === 'schedule'" x-transition class="space-y-4 mb-6 pl-4 border-l-2 border-blue-200">
                                <h4 class="text-sm font-semibold text-gray-800 flex items-center gap-2">
                                    ⏰ 데이터 이동 스케줄 설정
                                </h4>

                                <!-- 스케줄 모드 선택 -->
                                <div class="flex gap-4 mb-4">
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.data_schedule_mode"
                                               value="fixed_time"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">고정 시간</span>
                                    </label>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="radio"
                                               x-model="formData.data_schedule_mode"
                                               value="interval"
                                               class="text-blue-600 focus:ring-blue-500 h-4 w-4">
                                        <span class="ml-2 text-sm text-gray-700">일정 간격</span>
                                    </label>
                                </div>

                                <!-- 고정 시간 모드 -->
                                <div x-show="formData.data_schedule_mode === 'fixed_time'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2 mb-3">
                                        <input type="time"
                                               x-model="newDataFixedTime"
                                               class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                        <button type="button"
                                                @click="addDataFixedTime()"
                                                class="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                                            추가
                                        </button>
                                    </div>
                                    <div class="flex flex-wrap gap-2">
                                        <template x-for="time in formData.data_fixed_times" :key="time">
                                            <span class="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                                                <span x-text="time"></span>
                                                <button type="button"
                                                        @click="removeDataFixedTime(time)"
                                                        class="ml-2 text-blue-600 hover:text-blue-800">
                                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                                    </svg>
                                                </button>
                                            </span>
                                        </template>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">설정된 시간에 데이터 이동이 실행됩니다</p>
                                </div>

                                <!-- 일정 간격 모드 -->
                                <div x-show="formData.data_schedule_mode === 'interval'" class="p-4 bg-gray-50 rounded-lg">
                                    <div class="flex items-center gap-2">
                                        <span class="text-gray-700 text-sm">이동 간격:</span>
                                        <input type="number"
                                               x-model.number="formData.data_interval_hours"
                                               min="1"
                                               max="24"
                                               class="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                                        <span class="text-gray-500 text-sm">시간마다</span>
                                    </div>
                                    <p class="mt-2 text-xs text-gray-500">활성 시간대 내에서 지정된 간격으로 데이터 이동을 실행합니다</p>
                                </div>

                                <!-- 활성 시간대 (스케줄 매트릭스) -->
                                <div class="mt-4">
                                    <label class="block text-sm font-medium text-gray-700 mb-2">활성 시간대</label>
                                    <div class="bg-gray-50 rounded-lg p-4">
                                        <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
                                            <div class="flex flex-wrap gap-2">
                                                <button type="button" @click="selectAllHours()"
                                                        class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                                                    전체 선택 (24시간)
                                                </button>
                                                <button type="button" @click="clearAllHours()"
                                                        class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                                                    전체 해제
                                                </button>
                                                <button type="button" @click="selectWorkingHours()"
                                                        class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                                                    평일 9-21시
                                                </button>
                                            </div>
                                            <div class="flex items-center gap-4 text-sm">
                                                <span class="text-blue-800 font-medium">
                                                    활성: <span x-text="activeHoursCount"></span>시간/주
                                                </span>
                                            </div>
                                        </div>
                                        <p class="text-xs text-gray-500 mb-3">
                                            파란색 = 활성 (이동 가능), 회색 = 비활성
                                        </p>
                                        <div class="overflow-x-auto">
                                            <table class="w-full text-xs border-collapse">
                                                <thead>
                                                    <tr>
                                                        <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                                        <template x-for="(day, dayIdx) in days" :key="dayIdx">
                                                            <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                                                @click="toggleDay(dayIdx)" x-text="day"></th>
                                                        </template>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    <template x-for="hour in 24" :key="hour">
                                                        <tr>
                                                            <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                                                x-text="String(hour-1).padStart(2, '0') + '시'"></td>
                                                            <template x-for="(day, dayIdx) in days" :key="dayIdx + '-' + hour">
                                                                <td class="border border-gray-300 p-0">
                                                                    <button type="button"
                                                                            class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                                                            :class="schedule[dayIdx][hour-1] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'"
                                                                            @click="toggleHour(dayIdx, hour-1)"></button>
                                                                </td>
                                                            </template>
                                                        </tr>
                                                    </template>
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>

                                <!-- 안내 메시지 -->
                                <div class="p-3 bg-blue-50 rounded-lg border border-blue-200 mt-4">
                                    <p class="text-xs text-blue-800">
                                        ℹ️ 스케줄 모드는 플로우에 수집 모듈이 없어도 독립적으로 동작합니다.
                                    </p>
                                </div>
                            </div>

                            <!-- 2. 실행 조건 설정 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    ⚙️ 실행 조건
                                </h3>

                                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <!-- 최대 이동 개수 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">최대 이동 개수</label>
                                        <div class="flex items-center gap-2">
                                            <label class="flex items-center cursor-pointer mr-3">
                                                <input type="checkbox"
                                                       x-model="formData.max_titles_unlimited"
                                                       class="w-4 h-4 text-teal-600 focus:ring-teal-500 rounded">
                                                <span class="ml-2 text-sm text-gray-600">전체 (카테고리 분류된 제목)</span>
                                            </label>
                                            <input type="number"
                                                   x-model.number="formData.max_titles_per_run"
                                                   min="1"
                                                   max="10000"
                                                   x-show="!formData.max_titles_unlimited"
                                                   class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent">
                                            <span class="text-sm text-gray-500" x-show="!formData.max_titles_unlimited">개</span>
                                        </div>
                                        <p class="mt-1 text-xs text-gray-500" x-show="!formData.max_titles_unlimited">한 번 실행 시 최대 이동할 제목 수</p>
                                        <p class="mt-1 text-xs text-teal-600" x-show="formData.max_titles_unlimited">✅ 카테고리가 분류된 모든 제목을 이동합니다</p>
                                    </div>

                                    <!-- 최소 제목 수 조건 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">최소 제목 수 조건</label>
                                        <div class="flex items-center gap-2">
                                            <input type="number"
                                                   x-model.number="formData.min_titles_required"
                                                   min="1"
                                                   max="100"
                                                   class="w-24 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent">
                                            <span class="text-sm text-gray-500">개 이상</span>
                                        </div>
                                        <p class="mt-1 text-xs text-gray-500">임시 제목이 N개 이상일 때만 동작</p>
                                    </div>
                                </div>
                            </div>

                            <!-- 3. 필터 및 중복 처리 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    🔍 필터 및 중복 처리
                                </h3>

                                <!-- 중복 제목 처리 -->
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">중복 제목 처리</label>
                                    <div class="flex gap-4 flex-wrap">
                                        <label class="flex items-center cursor-pointer">
                                            <input type="radio"
                                                   x-model="formData.duplicate_handling"
                                                   value="skip"
                                                   class="text-teal-600 focus:ring-teal-500 h-4 w-4">
                                            <span class="ml-2 text-sm text-gray-700">건너뛰기</span>
                                        </label>
                                        <label class="flex items-center cursor-pointer">
                                            <input type="radio"
                                                   x-model="formData.duplicate_handling"
                                                   value="overwrite"
                                                   class="text-teal-600 focus:ring-teal-500 h-4 w-4">
                                            <span class="ml-2 text-sm text-gray-700">덮어쓰기</span>
                                        </label>
                                        <label class="flex items-center cursor-pointer">
                                            <input type="radio"
                                                   x-model="formData.duplicate_handling"
                                                   value="suffix"
                                                   class="text-teal-600 focus:ring-teal-500 h-4 w-4">
                                            <span class="ml-2 text-sm text-gray-700">접미사 추가</span>
                                        </label>
                                    </div>
                                    <p class="mt-1 text-xs text-gray-500">이미 존재하는 제목과 중복될 경우 처리 방식</p>
                                </div>

                                <!-- 카테고리 필터 -->
                                <div class="p-4 bg-gray-50 rounded-lg">
                                    <label class="block text-sm font-medium text-gray-700 mb-2">카테고리 필터</label>
                                    <p class="text-xs text-gray-500">특정 카테고리의 제목만 이동합니다. 비어있으면 전체 카테고리를 대상으로 합니다.</p>
                                    <div class="mt-2">
                                        <input type="text"
                                               x-model="formData.category_filter"
                                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                                               placeholder="카테고리명을 쉼표로 구분 (예: IT, 건강, 여행)">
                                    </div>
                                </div>
                            </div>

                            <!-- 4. 그룹화 설정 -->
                            <div class="space-y-4 mb-6">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    📊 그룹화 설정
                                </h3>

                                <div class="p-4 bg-gray-50 rounded-lg">
                                    <label class="flex items-center cursor-pointer mb-3">
                                        <input type="checkbox"
                                               x-model="formData.auto_group"
                                               class="w-4 h-4 text-teal-600 focus:ring-teal-500 rounded">
                                        <span class="ml-2 text-sm font-medium text-gray-700">자동 그룹화 활성화</span>
                                    </label>
                                    <p class="ml-6 text-xs text-gray-500 mb-3">유사한 제목끼리 자동으로 그룹화합니다</p>

                                    <!-- 유사도 임계값 (자동 그룹화 활성화 시) -->
                                    <div x-show="formData.auto_group" x-transition class="ml-6 mt-3">
                                        <label class="block text-sm font-medium text-gray-700 mb-2">유사도 임계값</label>
                                        <div class="flex items-center gap-2">
                                            <input type="range"
                                                   x-model.number="formData.similarity_threshold"
                                                   min="50"
                                                   max="100"
                                                   class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer">
                                            <span class="w-12 text-center text-sm font-medium text-teal-700" x-text="formData.similarity_threshold + '%'"></span>
                                        </div>
                                        <p class="mt-1 text-xs text-gray-500">값이 높을수록 더 엄격하게 그룹화됩니다 (권장: 75%)</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 기타 타입 설정 -->
                        <div x-show="formData.type_code !== 'republish' && formData.type_code !== 'collect' && formData.type_code !== 'data'">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">설정 정보 (JSON)</label>
                                <textarea x-model="settingsJson"
                                          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                                          rows="6"
                                          placeholder='{"key": "value"}'>
                                </textarea>
                                <p class="mt-1 text-xs text-gray-500">모듈별 설정을 JSON 형태로 입력하세요</p>
                            </div>
                        </div>
                    </div>

                    <!-- 폼 액션 -->
                    <div class="flex gap-3 pt-6 border-t border-gray-200 mt-8">
                        <button type="button"
                                @click="closeForm()"
                                class="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500">
                            취소
                        </button>
                        <button type="submit"
                                :disabled="loading"
                                class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed">
                            <span x-show="!loading" x-text="isEdit ? '수정' : '생성'"></span>
                            <span x-show="loading" class="flex items-center justify-center">
                                <svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                처리중...
                            </span>
                        </button>
                    </div>
                </form>
            </div>
            `;
        },

        // 상태별 CSS 클래스 반환
        getStatusClass(isActive) {
            return isActive
                ? 'bg-green-100 text-green-800 border-green-200'
                : 'bg-gray-100 text-gray-600 border-gray-200';
        },

        // 모듈 타입별 배경색 반환
        getModuleColor(typeCode) {
            const colors = {
                'republish': 'bg-sky-200',
                'prompt': 'bg-green-200',
                'generate': 'bg-amber-200',
                'publish': 'bg-rose-200',
                'collect': 'bg-purple-200',
                'data': 'bg-teal-200'
            };
            return colors[typeCode] || 'bg-gray-200';
        },

        // 재발행 적용 구간 텍스트 반환
        getPostRangeText(module) {
            const start = module.post_range_start || 1;
            const end = module.post_range_end;

            if (!end) {
                return `${start}~무제한 (누적 포스트)`;
            }

            return `${start}~${end} (누적 포스트)`;
        },

        // 재발행 간격 텍스트 반환
        getIntervalText(module) {
            // 캐시 확인
            const cacheKey = `${module.id}_${module.updated_at || module.created_at}`;
            if (this.intervalTextCache[cacheKey]) {
                return this.intervalTextCache[cacheKey];
            }

            console.log(`[getIntervalText] 캐시 미스 - 모듈 ID: ${module.id}, 이름: ${module.name}`);
            console.log('[getIntervalText] interval_mode:', module.interval_mode);
            console.log('[getIntervalText] auto_daily_count:', module.auto_daily_count);
            console.log('[getIntervalText] manual_interval_minutes:', module.manual_interval_minutes);

            const mode = module.interval_mode || 'manual';

            // 활성 시간 계산 (스케줄 매트릭스에서)
            const activeMinutes = this.calculateActiveMinutes(module);
            console.log('[getIntervalText] 활성 시간:', activeMinutes, '분');

            let result;

            if (mode === 'auto' && module.auto_daily_count) {
                // 자동 모드: "5회/일 (최소 144분 간격)"
                const minInterval = Math.ceil(activeMinutes / module.auto_daily_count);
                result = `${module.auto_daily_count}회/일 (최소 ${minInterval}분 간격)`;
            } else if (module.manual_interval_minutes) {
                // 수동 모드: "25분마다 (최대 28회/일)"
                const maxDaily = Math.floor(activeMinutes / module.manual_interval_minutes);
                result = `${module.manual_interval_minutes}분마다 (최대 ${maxDaily}회/일)`;
            } else {
                result = "설정 없음";
            }

            // 결과를 캐시에 저장
            this.intervalTextCache[cacheKey] = result;
            return result;
        },

        // 활성 시간 계산 (분 단위)
        calculateActiveMinutes(module) {
            if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
                // 기본값: 12시간 (평일 9-21시)
                return 720; // 12 * 60
            }

            const schedule = module.schedule_matrix;
            let totalActiveMinutes = 0;

            // 각 요일별 활성 시간 계산
            for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
                const daySchedule = schedule[dayIdx];
                if (Array.isArray(daySchedule)) {
                    const activeHours = daySchedule.filter(hour => hour === true).length;
                    totalActiveMinutes += activeHours * 60;
                }
            }

            // 평균 일일 활성 시간 (주 7일 기준)
            const avgDailyMinutes = Math.round(totalActiveMinutes / 7);
            return avgDailyMinutes || 720; // 기본값 12시간
        },

        // 스케줄 요약 텍스트 반환
        getScheduleSummary(module) {
            // 캐시 확인
            const cacheKey = `${module.id}_${module.updated_at || module.created_at}`;
            if (this.scheduleSummaryCache[cacheKey]) {
                return this.scheduleSummaryCache[cacheKey];
            }

            console.log(`[getScheduleSummary] 캐시 미스 - 모듈 ID: ${module.id}, 이름: ${module.name}`);
            console.log('[getScheduleSummary] schedule_matrix:', module.schedule_matrix);
            console.log('[getScheduleSummary] schedule_matrix 타입:', typeof module.schedule_matrix);
            console.log('[getScheduleSummary] schedule_matrix isArray:', Array.isArray(module.schedule_matrix));

            if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
                console.log('[getScheduleSummary] schedule_matrix가 유효하지 않음');
                const result = "설정 없음";
                this.scheduleSummaryCache[cacheKey] = result;
                return result;
            }

            const schedule = module.schedule_matrix;
            const days = ['월', '화', '수', '목', '금', '토', '일'];

            // 각 요일의 활성 시간대 범위 추출
            const dayRanges = {};
            for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
                const daySchedule = schedule[dayIdx];
                if (Array.isArray(daySchedule) && daySchedule.some(hour => hour === true)) {
                    const timeRange = this.extractTimeRange(daySchedule);
                    if (timeRange) {
                        dayRanges[dayIdx] = timeRange;
                    }
                }
            }

            if (Object.keys(dayRanges).length === 0) {
                const result = "설정 없음";
                this.scheduleSummaryCache[cacheKey] = result;
                return result;
            }

            // 동일한 시간대를 가진 요일들을 그룹화
            const timeGroups = {};
            for (const [dayIdx, timeRange] of Object.entries(dayRanges)) {
                const timeKey = timeRange;
                if (!timeGroups[timeKey]) {
                    timeGroups[timeKey] = [];
                }
                timeGroups[timeKey].push(parseInt(dayIdx));
            }

            // 각 그룹별로 요일 범위 텍스트 생성
            const groupTexts = [];
            for (const [timeRange, dayIndices] of Object.entries(timeGroups)) {
                const dayText = this.formatDayRange(dayIndices, days);
                groupTexts.push(`${dayText}(${timeRange})`);
            }

            const result = groupTexts.join('\n');
            this.scheduleSummaryCache[cacheKey] = result;
            return result;
        },

        // 시간대 범위 추출
        extractTimeRange(daySchedule) {
            let startHour = -1;
            let endHour = -1;

            for (let hour = 0; hour < 24; hour++) {
                if (daySchedule[hour]) {
                    if (startHour === -1) startHour = hour;
                    endHour = hour;
                }
            }

            if (startHour === -1) return null;

            return `${String(startHour).padStart(2, '0')}~${String(endHour + 1).padStart(2, '0')}`;
        },

        // 요일 범위 포맷팅
        formatDayRange(dayIndices, days) {
            if (dayIndices.length === 1) {
                return days[dayIndices[0]];
            }

            // 연속된 요일인지 확인
            dayIndices.sort((a, b) => a - b);
            let ranges = [];
            let start = dayIndices[0];
            let end = start;

            for (let i = 1; i < dayIndices.length; i++) {
                if (dayIndices[i] === end + 1) {
                    end = dayIndices[i];
                } else {
                    ranges.push(start === end ? days[start] : `${days[start]}~${days[end]}`);
                    start = dayIndices[i];
                    end = start;
                }
            }
            ranges.push(start === end ? days[start] : `${days[start]}~${days[end]}`);

            return ranges.join(', ');
        },

        // 스케줄 여부 확인
        hasSchedule(module) {
            return module.schedule_matrix &&
                   JSON.stringify(module.schedule_matrix) !== JSON.stringify(this.getEmptySchedule());
        },

        // 빈 스케줄 생성
        getEmptySchedule() {
            return Array(7).fill().map(() => Array(24).fill(false));
        },

        // 시간 경과 포맷
        formatTimeAgo(timestamp) {
            if (!timestamp) return '';

            const now = new Date();
            const time = new Date(timestamp);
            const diffInMs = now - time;
            const diffInMins = Math.floor(diffInMs / 60000);
            const diffInHours = Math.floor(diffInMins / 60);
            const diffInDays = Math.floor(diffInHours / 24);

            if (diffInDays > 0) {
                return `${diffInDays}일 전`;
            } else if (diffInHours > 0) {
                return `${diffInHours}시간 전`;
            } else if (diffInMins > 0) {
                return `${diffInMins}분 전`;
            } else {
                return '방금 전';
            }
        },

        // 모듈 타입 선택 팝업 표시
        async showModuleTypeSelector() {
            try {
                console.log('모듈 타입 선택 팝업 열기 시도...');
                // 팝업 표시 (옵션은 템플릿에 하드코딩되어 있음)
                if (typeof window.openSelectionPopup === 'function') {
                    window.openSelectionPopup('moduleTypeSelector');
                    console.log('모듈 타입 선택 팝업 열기 완료');
                } else {
                    console.error('openSelectionPopup 함수가 정의되지 않았습니다');
                    this.showError('모듈 타입 선택 팝업을 열 수 없습니다. 페이지를 새로고침해주세요.');
                }
            } catch (error) {
                console.error('모듈 타입 선택 팝업 오류:', error);
                this.showError('모듈 타입 선택 팝업을 열 수 없습니다.');
            }
        },

        // 모듈 생성
        async createModule(typeCode) {
            try {
                console.log(`모듈 생성 시작: ${typeCode}`);

                const selectedType = this.moduleTypes.find(t => t.code === typeCode) || {
                    code: typeCode,
                    name: this.getModuleTypeName(typeCode),
                    description: ''
                };

                console.log('선택된 모듈 타입:', selectedType);

                // 바텀시트 제목 업데이트
                const title = document.getElementById('moduleFormTitle');
                if (title) {
                    title.textContent = `${selectedType.name} 생성`;
                } else {
                    console.warn('모듈 폼 제목 엘리먼트를 찾을 수 없습니다');
                }

                // 폼 내용 로드
                console.log('폼 내용 로드 시작...');
                const formContent = await this.loadModuleForm(null, selectedType);
                const contentArea = document.getElementById('moduleFormContent');
                if (contentArea) {
                    contentArea.innerHTML = formContent;
                    console.log('폼 내용 로드 완료');
                } else {
                    console.warn('모듈 폼 컨텐츠 엘리먼트를 찾을 수 없습니다');
                }

                // 바텀시트 표시
                console.log('바텀시트 열기 시도...');
                if (typeof window.openBottomSheet === 'function') {
                    window.openBottomSheet('moduleForm');
                    console.log('바텀시트 열기 완료');
                } else {
                    console.error('openBottomSheet 함수가 정의되지 않았습니다');
                    this.showError('모듈 폼을 열 수 없습니다. 페이지를 새로고침해주세요.');
                }

            } catch (error) {
                console.error('모듈 생성 전체 오류:', error);
                this.showError('모듈 생성 폼을 불러오는 중 오류가 발생했습니다: ' + error.message);
            }
        },

        // 모듈 수정
        async editModule(moduleId) {
            try {
                const module = this.modules.find(m => m.id === moduleId);
                if (!module) {
                    this.showError('모듈을 찾을 수 없습니다');
                    return;
                }

                const moduleType = this.moduleTypes.find(t => t.code === module.module_type.code) || {
                    code: module.module_type.code,
                    name: this.getModuleTypeName(module.module_type.code),
                    description: ''
                };

                // 바텀시트 제목 업데이트
                const title = document.getElementById('moduleFormTitle');
                if (title) {
                    title.textContent = `${module.name} 수정`;
                }

                // 폼 내용 로드
                const formContent = await this.loadModuleForm(module, moduleType);
                const contentArea = document.getElementById('moduleFormContent');
                if (contentArea) {
                    contentArea.innerHTML = formContent;
                }

                // 바텀시트 표시
                openBottomSheet('moduleForm');

            } catch (error) {
                this.showError('모듈 수정 폼을 불러오는 중 오류가 발생했습니다');
                console.error('모듈 수정 오류:', error);
            }
        },

        // 모듈 복사
        async copyModule(moduleId) {
            if (!confirm('이 모듈을 복사하시겠습니까?')) return;

            try {
                const response = await fetch(`/api/v1/modules/${moduleId}/copy`, {
                    method: 'POST',
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('모듈 복사 실패');
                }

                this.showSuccess('모듈이 복사되었습니다');
                await this.loadModules();

            } catch (error) {
                this.showError('모듈 복사 중 오류가 발생했습니다');
                console.error('모듈 복사 오류:', error);
            }
        },

        // 모듈 삭제
        async deleteModule(moduleId) {
            const module = this.modules.find(m => m.id === moduleId);
            if (!module) return;

            if (!confirm(`'${module.name}' 모듈을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;

            try {
                const response = await fetch(`/api/v1/modules/${moduleId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('모듈 삭제 실패');
                }

                this.showSuccess('모듈이 삭제되었습니다');

                // 리스트에서 제거
                this.modules = this.modules.filter(m => m.id !== moduleId);

                // GlobalSummary 통계 새로고침
                this.refreshGlobalSummary();

                // 카드 애니메이션 제거
                const card = document.querySelector(`[data-module-id="${moduleId}"]`);
                if (card) {
                    card.style.transition = 'all 0.3s ease-out';
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';

                    setTimeout(() => {
                        if (card.parentNode) {
                            card.parentNode.removeChild(card);
                        }
                    }, 300);
                }

            } catch (error) {
                this.showError('모듈 삭제 중 오류가 발생했습니다');
                console.error('모듈 삭제 오류:', error);
            }
        },

        // GlobalSummary 통계 새로고침
        refreshGlobalSummary() {
            const summaryEl = document.querySelector('[x-data="globalSummary()"]');
            if (summaryEl && summaryEl.__x) {
                summaryEl.__x.$data.loadStats();
            }
        },


        // 모듈 폼 로드 (HTML 템플릿)
        async loadModuleForm(module, moduleType) {
            // 기본 폼 HTML 반환
            return this.getDefaultFormHTML(module, moduleType);
        },


        // 기본 폼 HTML 생성
        getDefaultFormHTML(module, moduleType) {
            // 전역 변수를 통한 데이터 전달 (더 안전한 방법)
            const moduleId = 'moduleData_' + Date.now();
            const typeId = 'typeData_' + Date.now();

            // 전역 변수에 데이터 저장
            window[moduleId] = module;
            window[typeId] = moduleType;

            // Alpine.js 3.x는 x-data의 init() 메서드를 자동 호출함
            // x-init="init()" 제거하여 중복 호출 방지
            return `
                <div x-data="moduleFormApp(window.${moduleId}, window.${typeId})">
                    ${this.getFullFormTemplate()}
                </div>
            `;
        },

        // 알림 메시지 표시
        showSuccess(message) {
            if (window.showSuccessMessage) {
                window.showSuccessMessage(message);
            } else {
                alert(message);
            }
        },

        showError(message) {
            if (window.showErrorMessage) {
                window.showErrorMessage(message);
            } else {
                alert(message);
            }
        }
    };
}

// 선택 팝업 이벤트 리스너
document.addEventListener('selectionPopup:select', async (e) => {
    if (e.detail.popupId === 'moduleTypeSelector') {
        const app = window.moduleListAppInstance;
        if (app) {
            await app.createModule(e.detail.action);
        }
    }
});

// 팝업 관련 함수들 (selection_popup 컴포넌트와 호환)
window.openSelectionPopup = function(popupId) {
    const popup = document.getElementById(popupId);
    const backdrop = document.getElementById(popupId + '-backdrop');

    if (!popup) return;

    // 백드롭과 팝업 표시
    if (backdrop) {
        backdrop.classList.remove('hidden');
        setTimeout(() => {
            backdrop.style.opacity = '1';
        }, 10);
    }

    popup.classList.remove('hidden');

    // 팝업 애니메이션
    const content = popup.querySelector('div > div');
    if (content) {
        setTimeout(() => {
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }, 10);
    }

    // 스크롤 방지
    document.body.style.overflow = 'hidden';
};

window.closeSelectionPopup = function(popupId) {
    const popup = document.getElementById(popupId);
    const backdrop = document.getElementById(popupId + '-backdrop');
    const content = popup ? popup.querySelector('div > div') : null;

    // 팝업 애니메이션
    if (content) {
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
    }

    // 백드롭 숨기기
    if (backdrop) {
        backdrop.style.opacity = '0';
    }

    setTimeout(() => {
        if (popup) popup.classList.add('hidden');
        if (backdrop) backdrop.classList.add('hidden');
    }, 200);

    // 스크롤 복원
    document.body.style.overflow = '';
};

window.selectOption = function(popupId, action, text) {
    // 커스텀 이벤트 발생
    const event = new CustomEvent('selectionPopup:select', {
        detail: {
            popupId: popupId,
            action: action,
            text: text
        }
    });
    document.dispatchEvent(event);

    // 팝업 닫기
    closeSelectionPopup(popupId);
};

// 전역 인스턴스 저장
document.addEventListener('DOMContentLoaded', () => {
    // Alpine.js가 초기화된 후에 인스턴스를 저장
    setTimeout(() => {
        const container = document.querySelector('[x-data*="moduleListApp"]');
        if (container && container._x_dataStack) {
            window.moduleListAppInstance = container._x_dataStack[0];
        }
    }, 100);
});

// 유틸리티 함수들
window.editModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.editModule(moduleId);
    }
};

window.copyModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.copyModule(moduleId);
    }
};

window.deleteModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.deleteModule(moduleId);
    }
};


// 스크롤 위치 저장용 변수 (modules)
let moduleSavedScrollPosition = 0;

// 바텀시트 관련 함수들 (모듈 로드 전에 정의)
if (typeof window.openBottomSheet === 'undefined') {
    window.openBottomSheet = function(sheetId) {
        const sheet = document.getElementById(sheetId);
        const backdrop = document.getElementById(sheetId + '-backdrop');

        if (!sheet) {
            console.warn(`Bottom sheet '${sheetId}' not found`);
            return;
        }

        // 모바일에서 body 스크롤 고정
        moduleSavedScrollPosition = window.pageYOffset;
        document.body.classList.add('sheet-open');
        document.body.style.top = `-${moduleSavedScrollPosition}px`;

        // 백드롭 표시
        if (backdrop) {
            backdrop.classList.remove('hidden');
            setTimeout(() => {
                backdrop.style.opacity = '1';
            }, 10);
        }

        // 시트 표시
        sheet.classList.remove('translate-y-full');
    };
}

if (typeof window.closeBottomSheet === 'undefined') {
    window.closeBottomSheet = function(sheetId) {
        const sheet = document.getElementById(sheetId);
        const backdrop = document.getElementById(sheetId + '-backdrop');

        // 시트 숨기기
        if (sheet) {
            sheet.classList.add('translate-y-full');
        }

        // 백드롭 숨기기
        if (backdrop) {
            backdrop.style.opacity = '0';
            setTimeout(() => {
                backdrop.classList.add('hidden');

                // body 스크롤 복원
                document.body.classList.remove('sheet-open');
                document.body.style.top = '';
                window.scrollTo(0, moduleSavedScrollPosition);
            }, 300);
        }
    };
}

// ESC 키로 팝업 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (typeof closeSelectionPopup !== 'undefined') {
            closeSelectionPopup('moduleTypeSelector');
        }
        if (typeof closeBottomSheet !== 'undefined') {
            closeBottomSheet('moduleForm');
        }
    }
});


// ========================================
// 모듈 카드 슬라이드 관련 함수
// ========================================

/**
 * 모듈 카드 상태 (Alpine.js용)
 */
function moduleCardState() {
    return {
        initCard(el) {
            // 카드 초기화 로직 (필요시 확장)
        }
    };
}

/**
 * 모듈 타입별 표시할 정보 행 목록 반환
 * @param {Object} module - 모듈 객체
 * @returns {Array} - [{label, value}, ...]
 */
function getModuleInfoRows(module) {
    if (!module) return [];

    const rows = [];
    const typeCode = module.module_type?.code || '';
    const app = window.moduleListAppInstance;

    if (typeCode === 'republish') {
        // 재발행 모듈 - 적용 구간
        const start = module.post_range_start || 1;
        const end = module.post_range_end;
        const rangeText = end ? `${start}~${end} (누적 포스트)` : `${start}~무제한 (누적 포스트)`;
        rows.push({ label: '적용구간', value: rangeText });

        // 재발행 간격
        if (app && typeof app.getIntervalText === 'function') {
            rows.push({ label: '재발행 간격', value: app.getIntervalText(module) });
        } else if (module.manual_interval_minutes) {
            rows.push({ label: '재발행 간격', value: `${module.manual_interval_minutes}분마다` });
        } else if (module.auto_daily_count) {
            rows.push({ label: '재발행 간격', value: `${module.auto_daily_count}회/일` });
        }

        // 스케줄
        if (app && typeof app.getScheduleSummary === 'function') {
            const schedule = app.getScheduleSummary(module);
            if (schedule && schedule !== '설정 없음') {
                rows.push({ label: '스케줄', value: schedule.replace(/\n/g, ' | ') });
            }
        } else if (module.schedule_matrix && Array.isArray(module.schedule_matrix)) {
            // 폴백: app이 없을 때 직접 스케줄 파싱
            const scheduleText = parseScheduleMatrix(module.schedule_matrix);
            if (scheduleText && scheduleText !== '설정 없음') {
                rows.push({ label: '스케줄', value: scheduleText });
            }
        }
    } else if (typeCode === 'publish') {
        // 발행 모듈
        if (app && typeof app.getIntervalText === 'function') {
            rows.push({ label: '간격', value: app.getIntervalText(module) });
        }
        if (app && typeof app.getScheduleSummary === 'function') {
            const schedule = app.getScheduleSummary(module);
            if (schedule && schedule !== '설정 없음') {
                rows.push({ label: '스케줄', value: schedule.replace(/\n/g, ' | ') });
            }
        } else if (module.schedule_matrix && Array.isArray(module.schedule_matrix)) {
            // 폴백: app이 없을 때 직접 스케줄 파싱
            const scheduleText = parseScheduleMatrix(module.schedule_matrix);
            if (scheduleText && scheduleText !== '설정 없음') {
                rows.push({ label: '스케줄', value: scheduleText });
            }
        }
    } else if (typeCode === 'generate') {
        // AI 생성 모듈
        if (module.ai_model) {
            rows.push({ label: 'AI 모델', value: module.ai_model });
        }
        if (module.prompt_template) {
            const preview = module.prompt_template.length > 40
                ? module.prompt_template.substring(0, 40) + '...'
                : module.prompt_template;
            rows.push({ label: '프롬프트', value: preview });
        }
        if (module.settings) {
            if (module.settings.max_tokens) {
                rows.push({ label: '토큰 제한', value: `${module.settings.max_tokens}토큰` });
            }
            if (module.settings.temperature) {
                rows.push({ label: '창의성', value: String(module.settings.temperature) });
            }
        }
    } else if (typeCode === 'prompt') {
        // 프롬프트 모듈
        if (module.template_name || module.prompt_name) {
            rows.push({ label: '템플릿', value: module.template_name || module.prompt_name });
        }
        if (module.category) {
            rows.push({ label: '카테고리', value: module.category });
        }
        if (module.variables && Array.isArray(module.variables)) {
            rows.push({ label: '변수', value: module.variables.join(', ') });
        }
        if (module.settings && module.settings.max_length) {
            rows.push({ label: '길이 설정', value: `${module.settings.max_length}자` });
        }
    } else if (typeCode === 'collect') {
        // 수집 모듈
        const settings = module.settings || {};

        // 수집 대상 소스
        const sources = [];
        if (settings.source_naver_datalab) sources.push('네이버 데이터랩');
        if (settings.source_naver_ads) sources.push('네이버 광고');
        if (settings.source_google_trends) sources.push('구글 트렌드');
        if (settings.source_google_planner) sources.push('구글 플래너');
        if (settings.source_naver_news) sources.push('네이버 뉴스');
        if (settings.source_google_news) sources.push('구글 뉴스');
        if (settings.source_naver_webdoc) sources.push('웹문서');
        if (sources.length > 0) {
            rows.push({ label: '수집 대상', value: sources.join(', ') });
        }

        // 수집 유형
        const collectType = settings.collect_type;
        if (collectType) {
            const typeLabels = { 'keyword': '키워드만', 'title': '제목만', 'both': '키워드+제목' };
            rows.push({ label: '수집 유형', value: typeLabels[collectType] || collectType });
        }

        // 스케줄 모드
        const scheduleMode = settings.schedule_mode;
        if (scheduleMode === 'fixed_time' && settings.fixed_times) {
            rows.push({ label: '수집 시간', value: settings.fixed_times.join(', ') });
        } else if (scheduleMode === 'interval' && settings.interval_hours) {
            rows.push({ label: '수집 간격', value: `${settings.interval_hours}시간마다` });
        }

        // 연관검색 옵션
        if (settings.enable_related_search) {
            rows.push({ label: '연관검색', value: '활성' });
        }

        // 수집 수량 설정
        if (settings.keyword_collect_limit) {
            rows.push({ label: '키워드 수집', value: `최대 ${settings.keyword_collect_limit}개` });
        }
        if (settings.title_collect_limit) {
            rows.push({ label: '제목 수집', value: `최대 ${settings.title_collect_limit}개` });
        }

        // 스케줄 (schedule_matrix가 있으면)
        if (app && typeof app.getScheduleSummary === 'function') {
            const schedule = app.getScheduleSummary(module);
            if (schedule && schedule !== '설정 없음') {
                rows.push({ label: '스케줄', value: schedule.replace(/\n/g, ' | ') });
            }
        } else if (module.schedule_matrix && Array.isArray(module.schedule_matrix)) {
            const scheduleText = parseScheduleMatrix(module.schedule_matrix);
            if (scheduleText && scheduleText !== '설정 없음') {
                rows.push({ label: '스케줄', value: scheduleText });
            }
        }
    } else if (typeCode === 'data') {
        // 데이터 모듈
        const settings = module.settings || {};

        // 수집 모듈 연동
        const collectionLink = settings.collection_link || {};
        if (collectionLink.enabled) {
            const delay = collectionLink.delay_seconds || 30;
            rows.push({ label: '수집 연동', value: `활성 (${delay}초 대기)` });
        } else {
            rows.push({ label: '수집 연동', value: '비활성' });
        }

        // 실행 조건
        const execution = settings.execution || {};
        if (execution.max_titles_per_run) {
            rows.push({ label: '최대 이동', value: `${execution.max_titles_per_run}개` });
        }
        if (execution.min_titles_required && execution.min_titles_required > 1) {
            rows.push({ label: '최소 조건', value: `${execution.min_titles_required}개 이상` });
        }

        // 중복 처리
        const filter = settings.filter || {};
        const duplicateLabels = {
            'skip': '건너뛰기',
            'overwrite': '덮어쓰기',
            'suffix': '접미사 추가'
        };
        if (filter.duplicate_handling) {
            rows.push({ label: '중복 처리', value: duplicateLabels[filter.duplicate_handling] || filter.duplicate_handling });
        }

        // 카테고리 필터
        if (filter.categories && filter.categories.length > 0) {
            rows.push({ label: '카테고리', value: filter.categories.join(', ') });
        }

        // 자동 그룹화
        if (settings.auto_group) {
            const threshold = settings.similarity_threshold || 75;
            rows.push({ label: '자동 그룹화', value: `활성 (${threshold}%)` });
        }
    }

    // 정보가 없으면 생성일 표시 (폴백)
    if (rows.length === 0 && module.created_at) {
        const date = new Date(module.created_at).toLocaleDateString('ko-KR');
        rows.push({ label: '생성일', value: date });
    }

    return rows;
}

/**
 * 슬라이드 필요 여부 판단 (값 길이 기준)
 * @param {string} value - 표시할 값
 * @returns {boolean}
 */
function needsModuleInfoSlide(value) {
    if (!value) return false;
    // 30자 이상이면 슬라이드
    return value.length > 30;
}

/**
 * 슬라이드 속도 계산 (초)
 * @param {string} value - 표시할 값
 * @returns {number}
 */
function getModuleInfoSlideDuration(value) {
    if (!value) return 12;
    const length = value.length;
    const baseSpeed = 10; // 기본 10초 (플로우보다 약간 빠름)
    const perChar = 0.2; // 글자당 0.2초 추가
    const minDuration = 10; // 최소 10초
    const maxDuration = 35; // 최대 35초
    return Math.max(minDuration, Math.min(maxDuration, baseSpeed + (length * perChar)));
}

/**
 * 슬라이드 초기화 체크 (DOM 기반)
 * @param {HTMLElement} element - 행 요소
 */
function initModuleInfoSlideCheck(element) {
    const container = element.querySelector('.module-info-container');
    const track = element.querySelector('.module-info-track');
    if (!container || !track) return;

    // 렌더링 완료 후 너비 체크
    setTimeout(() => {
        const containerWidth = container.clientWidth;
        const trackWidth = track.scrollWidth / 2; // 복제된 콘텐츠 제외

        if (trackWidth <= containerWidth) {
            track.classList.add('no-slide');
        }
    }, 100);
}

/**
 * 터치 일시정지 토글 (모바일용)
 * @param {Event} event - 터치 이벤트
 * @param {HTMLElement} element - 행 요소
 */
function toggleModuleInfoTouch(event, element) {
    if (event.type !== 'touchstart') return;

    const track = element.querySelector('.module-info-track');
    if (!track) return;

    const isPaused = track.classList.contains('paused');
    if (isPaused) {
        track.classList.remove('paused');
        element.classList.remove('touch-paused');
    } else {
        track.classList.add('paused');
        element.classList.add('touch-paused');

        // 5초 후 자동 재개
        setTimeout(() => {
            track.classList.remove('paused');
            element.classList.remove('touch-paused');
        }, 5000);
    }
}

/**
 * 확장/축소 시 슬라이드 재초기화
 * @param {HTMLElement} container - 슬라이드 리스트 컨테이너
 */
function reinitModuleSlides(container) {
    if (!container) return;

    // 모든 module-info-row에 대해 슬라이드 체크 재실행
    const rows = container.querySelectorAll('.module-info-row');
    rows.forEach(row => {
        const track = row.querySelector('.module-info-track');
        if (track) {
            // 기존 no-slide 클래스 제거 후 재체크
            track.classList.remove('no-slide');
            initModuleInfoSlideCheck(row);
        }
    });
}

/**
 * 모바일 탭 전환 시 슬라이드 재초기화
 * display: none 상태에서 너비가 0으로 계산되는 문제 해결
 * @param {HTMLElement} tabContent - 탭 콘텐츠 요소
 */
function reinitMobileTabSlides(tabContent) {
    if (!tabContent) return;

    // 약간의 딜레이 후 실행 (display: block 적용 대기)
    setTimeout(() => {
        const rows = tabContent.querySelectorAll('.module-info-row');
        rows.forEach(row => {
            const container = row.querySelector('.module-info-container');
            const track = row.querySelector('.module-info-track');
            if (!container || !track) return;

            // 기존 상태 초기화
            track.classList.remove('no-slide');

            // 너비 재계산
            const containerWidth = container.clientWidth;
            const trackWidth = track.scrollWidth / 2; // 복제된 콘텐츠 제외

            if (trackWidth > containerWidth) {
                // 슬라이드 필요 - 애니메이션 재시작
                track.style.webkitAnimation = 'none';
                track.style.animation = 'none';
                track.offsetHeight; // reflow 트리거
                track.style.webkitAnimation = '';
                track.style.animation = '';
            } else {
                // 슬라이드 불필요
                track.classList.add('no-slide');
            }
        });
    }, 100);
}

/**
 * 스케줄 매트릭스를 텍스트로 변환 (폴백용)
 * @param {Array} scheduleMatrix - 7x24 스케줄 배열
 * @returns {string} - 스케줄 요약 텍스트
 */
function parseScheduleMatrix(scheduleMatrix) {
    if (!scheduleMatrix || !Array.isArray(scheduleMatrix)) {
        return '설정 없음';
    }

    const days = ['월', '화', '수', '목', '금', '토', '일'];
    const dayRanges = {};

    // 각 요일의 활성 시간대 범위 추출
    for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
        const daySchedule = scheduleMatrix[dayIdx];
        if (Array.isArray(daySchedule) && daySchedule.some(hour => hour === true)) {
            let startHour = -1;
            let endHour = -1;

            for (let hour = 0; hour < 24; hour++) {
                if (daySchedule[hour]) {
                    if (startHour === -1) startHour = hour;
                    endHour = hour;
                }
            }

            if (startHour !== -1) {
                dayRanges[dayIdx] = `${String(startHour).padStart(2, '0')}~${String(endHour + 1).padStart(2, '0')}`;
            }
        }
    }

    if (Object.keys(dayRanges).length === 0) {
        return '설정 없음';
    }

    // 동일한 시간대를 가진 요일들을 그룹화
    const timeGroups = {};
    for (const [dayIdx, timeRange] of Object.entries(dayRanges)) {
        if (!timeGroups[timeRange]) {
            timeGroups[timeRange] = [];
        }
        timeGroups[timeRange].push(parseInt(dayIdx));
    }

    // 각 그룹별로 텍스트 생성
    const groupTexts = [];
    for (const [timeRange, dayIndices] of Object.entries(timeGroups)) {
        dayIndices.sort((a, b) => a - b);

        let dayText;
        if (dayIndices.length === 1) {
            dayText = days[dayIndices[0]];
        } else if (dayIndices.length === 7) {
            dayText = '매일';
        } else {
            // 연속 요일 체크
            let isConsecutive = true;
            for (let i = 1; i < dayIndices.length; i++) {
                if (dayIndices[i] !== dayIndices[i-1] + 1) {
                    isConsecutive = false;
                    break;
                }
            }

            if (isConsecutive && dayIndices.length > 2) {
                dayText = `${days[dayIndices[0]]}~${days[dayIndices[dayIndices.length - 1]]}`;
            } else {
                dayText = dayIndices.map(idx => days[idx]).join(',');
            }
        }

        groupTexts.push(`${dayText}(${timeRange})`);
    }

    return groupTexts.join(' | ');
}