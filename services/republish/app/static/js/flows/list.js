/**
 * 플로우 목록 페이지 JavaScript
 * Alpine.js 기반 상태 관리 및 API 통신
 */

function flowListApp() {
    return {
        // 상태 데이터
        loading: false,
        flows: [],
        modules: [],
        blogs: [],

        // 메시지 상태
        message: '',
        messageType: 'info',

        // 선택 상태
        selectedFlowId: null,
        selectedAddType: null,
        selectedItems: [],
        availableItems: [],

        // 정렬 상태
        sortBy: 'name',
        sortOrder: 'asc',

        // 플로우 실행 상태
        executingFlowId: null,
        executeResult: null,
        showExecuteResult: false,

        // 정렬된 플로우 목록 (computed property)
        get sortedFlows() {
            if (!this.flows || this.flows.length === 0) {
                return [];
            }

            const sorted = [...this.flows].sort((a, b) => {
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

                    case 'module_count':
                        valueA = this.getFlowModules(a).length;
                        valueB = this.getFlowModules(b).length;
                        return valueA - valueB;

                    case 'blog_count':
                        valueA = this.getFlowBlogs(a).length;
                        valueB = this.getFlowBlogs(b).length;
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

        // 정렬 방향 토글
        toggleSortOrder() {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            this.saveSortPreference();
        },

        // 정렬 설정 저장 (localStorage)
        saveSortPreference() {
            try {
                localStorage.setItem('flowSortBy', this.sortBy);
                localStorage.setItem('flowSortOrder', this.sortOrder);
            } catch (e) {
                console.warn('정렬 설정 저장 실패:', e);
            }
        },

        // 정렬 설정 로드 (localStorage)
        loadSortPreference() {
            try {
                const savedSortBy = localStorage.getItem('flowSortBy');
                const savedSortOrder = localStorage.getItem('flowSortOrder');
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

        // 초기화
        async init() {
            // 전역 참조 즉시 설정 (템플릿 헬퍼 함수들이 사용)
            window.flowListApp = this;

            // 저장된 정렬 설정 로드
            this.loadSortPreference();

            this.loading = true;
            try {
                await Promise.all([
                    this.loadFlows(),
                    this.loadModules(),
                    this.loadBlogs()
                ]);
            } catch (error) {
                this.showError('데이터를 불러오는 중 오류가 발생했습니다');
                console.error('초기화 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 플로우 목록 로드
        async loadFlows() {
            const response = await fetch('/api/v1/flows', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('플로우 목록 조회 실패');
            }

            const data = await response.json();
            this.flows = data.flows || [];
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
        },

        async loadBlogs() {
            const response = await fetch('/api/v1/blogs', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('블로그 목록 조회 실패');
            }

            const data = await response.json();
            this.blogs = Array.isArray(data) ? data : (data.blogs || []);
        },

        // 플로우 생성 폼 표시
        showFlowForm(flowId = null) {
            // 폼 제목 설정
            const titleElement = document.getElementById('flowFormTitle');
            if (titleElement) {
                titleElement.textContent = flowId ? '플로우 수정' : '플로우 생성';
            }

            // 하단 시트 표시
            showBottomSheet('flowForm');

            // 폼 데이터 초기화
            if (window.flowFormApp && flowId) {
                window.flowFormApp.loadFlowData(flowId);
            }
        },

        // 플로우 편집
        editFlow(flowId) {
            this.showFlowForm(flowId);
        },

        // 플로우 복사
        async copyFlow(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            try {
                // 복사 API 호출 (모듈, 블로그 포함)
                const response = await fetch(`/api/v1/flows/${flowId}/copy`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 복사 실패');
                }

                // 목록 새로고침
                await this.loadFlows();
                this.showSuccess('플로우가 복사되었습니다 (모듈, 블로그 포함)');

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 복사 오류:', error);
            }
        },

        // 플로우 삭제
        async deleteFlow(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            if (!confirm(`'${flow.name}' 플로우를 정말 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 삭제 실패');
                }

                // 목록에서 제거
                this.flows = this.flows.filter(f => f.id !== flowId);
                this.showSuccess('플로우가 삭제되었습니다');

                // GlobalSummary 통계 새로고침
                this.refreshGlobalSummary();

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 삭제 오류:', error);
            }
        },

        // GlobalSummary 통계 새로고침
        refreshGlobalSummary() {
            const summaryEl = document.querySelector('[x-data="globalSummary()"]');
            if (summaryEl && summaryEl.__x) {
                summaryEl.__x.$data.loadStats();
            }
        },

        // 플로우 활성화/비활성화 토글
        async toggleFlowStatus(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            const newStatus = !flow.is_active;
            const action = newStatus ? '시작' : '중지';

            if (!confirm(`'${flow.name}' 플로우를 ${action}하시겠습니까?`)) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        is_active: newStatus
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 상태 변경 실패');
                }

                // 상태 업데이트
                flow.is_active = newStatus;
                this.showSuccess(`플로우가 ${action}되었습니다`);

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 상태 변경 오류:', error);
            }
        },

        // 추가 선택기 표시
        showAddSelector(flowId) {
            this.selectedFlowId = flowId;
            showSelectionPopup('addSelector');
        },

        // 추가 타입 선택
        selectAddType(type) {
            this.selectedAddType = type;
            closeSelectionPopup('addSelector');

            // 아이템 선택기 표시
            this.showItemSelector();
        },

        // 아이템 선택기 표시
        showItemSelector() {
            const titleElement = document.getElementById('itemSelectorTitle');
            const contentElement = document.getElementById('itemSelectorContent');

            if (this.selectedAddType === 'module') {
                titleElement.textContent = '모듈 선택';
                this.availableItems = this.getAvailableModules();
                contentElement.innerHTML = this.renderModuleSelector();
            } else if (this.selectedAddType === 'blog') {
                titleElement.textContent = '블로그 선택';
                this.availableItems = this.getAvailableBlogs();
                contentElement.innerHTML = this.renderBlogSelector();
            }

            this.selectedItems = [];
            this.updateAddButtonText();

            showBottomSheet('itemSelector');
        },

        // 사용 가능한 모듈 목록 (현재 플로우에 포함되지 않은 것들)
        getAvailableModules() {
            const flow = this.flows.find(f => f.id === this.selectedFlowId);
            if (!flow) return this.modules;

            const usedModuleIds = this.getFlowModules(flow).map(fm => fm.module.id);
            return this.modules.filter(m => !usedModuleIds.includes(m.id));
        },

        // 사용 가능한 블로그 목록 (현재 플로우에 포함되지 않은 것들)
        getAvailableBlogs() {
            const flow = this.flows.find(f => f.id === this.selectedFlowId);
            if (!flow) return this.blogs;

            const usedBlogIds = this.getFlowBlogs(flow).map(fb => fb.blog.id);
            return this.blogs.filter(b => !usedBlogIds.includes(b.id));
        },

        // 모듈 선택기 렌더링
        renderModuleSelector() {
            return this.availableItems.map(module => `
                <label class="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input type="checkbox"
                           value="${module.id}"
                           onchange="window.flowListApp?.toggleItemSelection(${module.id})"
                           class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2">
                    <div class="flex items-center gap-2 flex-1">
                        <span class="text-lg">${this.getModuleIcon(module.module_type.code)}</span>
                        <div>
                            <span class="text-sm font-medium text-gray-900">${module.name}</span>
                            <span class="text-xs text-gray-500 ml-2">${this.getModuleTypeLabel(module.module_type.code)}</span>
                        </div>
                    </div>
                </label>
            `).join('') || '<div class="text-center py-8 text-gray-500">추가할 수 있는 모듈이 없습니다</div>';
        },

        // 블로그 선택기 렌더링
        renderBlogSelector() {
            return this.availableItems.map(blog => `
                <label class="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input type="checkbox"
                           value="${blog.id}"
                           onchange="window.flowListApp?.toggleItemSelection(${blog.id})"
                           class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2">
                    <div class="flex items-center gap-2 flex-1">
                        <span class="text-lg">${this.getBlogIcon(blog.platform)}</span>
                        <div>
                            <span class="text-sm font-medium text-gray-900">${blog.name}</span>
                            <span class="text-xs text-gray-500 ml-2">${this.getBlogPlatformLabel(blog.platform)}</span>
                        </div>
                    </div>
                </label>
            `).join('') || '<div class="text-center py-8 text-gray-500">추가할 수 있는 블로그가 없습니다</div>';
        },

        // 아이템 선택 토글
        toggleItemSelection(itemId) {
            const index = this.selectedItems.indexOf(itemId);
            if (index === -1) {
                this.selectedItems.push(itemId);
            } else {
                this.selectedItems.splice(index, 1);
            }
            this.updateAddButtonText();
        },

        // 추가 버튼 텍스트 업데이트
        updateAddButtonText() {
            const buttonTextElement = document.getElementById('addButtonText');
            const addButton = document.getElementById('addSelectedItems');

            if (buttonTextElement) {
                buttonTextElement.textContent = `추가 (${this.selectedItems.length})`;
            }

            if (addButton) {
                addButton.disabled = this.selectedItems.length === 0;
            }
        },

        // 선택된 아이템들 추가
        async addSelectedItems() {
            if (this.selectedItems.length === 0) return;

            try {
                const endpoint = this.selectedAddType === 'module' ? 'modules' : 'blogs';
                const response = await fetch(`/api/v1/flows/${this.selectedFlowId}/${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        item_ids: this.selectedItems
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '아이템 추가 실패');
                }

                const result = await response.json();

                // 플로우 데이터 새로고침
                await this.loadFlows();

                // 결과 표시
                if (result.failed_items && result.failed_items.length > 0) {
                    this.showAddResult(result);
                } else {
                    const itemTypeName = this.selectedAddType === 'module' ? '모듈' : '블로그';
                    this.showSuccess(`${this.selectedItems.length}개 ${itemTypeName}이 추가되었습니다`);
                }

                closeBottomSheet('itemSelector');

            } catch (error) {
                this.showError(error.message);
                console.error('아이템 추가 오류:', error);
            }
        },

        // 추가 결과 표시 (성공/실패 혼합)
        showAddResult(result) {
            const successCount = result.success_count || 0;
            const failedItems = result.failed_items || [];

            let message = '';
            if (successCount > 0) {
                message += `✅ 성공: ${successCount}개\n`;
            }
            if (failedItems.length > 0) {
                message += `❌ 실패: ${failedItems.length}개\n`;
                failedItems.forEach(item => {
                    message += `  - ${item.name}: ${item.reason}\n`;
                });
            }

            alert(message);
        },

        // 플로우에서 모듈 제거
        async removeModuleFromFlow(flowId, flowModuleId) {
            if (!confirm('이 모듈을 플로우에서 제거하시겠습니까?')) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}/modules/${flowModuleId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '모듈 제거 실패');
                }

                // 플로우 데이터 새로고침
                await this.loadFlows();
                this.showSuccess('모듈이 제거되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('모듈 제거 오류:', error);
            }
        },

        // 플로우에서 블로그 제거
        async removeBlogFromFlow(flowId, flowBlogId) {
            if (!confirm('이 블로그를 플로우에서 제거하시겠습니까?')) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}/blogs/${flowBlogId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '블로그 제거 실패');
                }

                // 플로우 데이터 새로고침
                await this.loadFlows();
                this.showSuccess('블로그가 제거되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('블로그 제거 오류:', error);
            }
        },

        // 플로우의 모듈 목록 반환
        getFlowModules(flow) {
            return flow.module_links || flow.flow_modules || [];
        },

        // 플로우의 블로그 목록 반환
        getFlowBlogs(flow) {
            return flow.blog_links || flow.flow_blogs || [];
        },

        // Flow에 GP 모듈이 포함되어 있는지 확인
        flowHasGP(flow) {
            const modules = this.getFlowModules(flow);
            return modules.some(m => m.module?.module_type?.code === 'growth_profile');
        },

        // Flow의 GP 모듈 이름 반환
        getGPModuleName(flow) {
            const modules = this.getFlowModules(flow);
            const gp = modules.find(m => m.module?.module_type?.code === 'growth_profile');
            return gp?.module?.name || '';
        },

        // 모듈 아이콘 반환
        getModuleIcon(typeCode) {
            const icons = {
                republish: '🔄',
                publish: '📤',
                generate: '✨',
                prompt: '📝',
                collect: '🔍',
                growth_profile: '📈'
            };
            return icons[typeCode] || '📦';
        },

        // 모듈 타입 레이블 반환
        getModuleTypeLabel(typeCode) {
            const labels = {
                republish: '재발행',
                publish: '발행',
                generate: '생성',
                prompt: '프롬프트',
                growth_profile: '성장 프로파일'
            };
            return labels[typeCode] || typeCode;
        },

        // 블로그 아이콘 반환
        getBlogIcon(platform) {
            const icons = {
                blogger: '📙',
                wordpress: '🌐'
            };
            return icons[platform] || '📝';
        },

        // 블로그 플랫폼 레이블 반환
        getBlogPlatformLabel(platform) {
            const labels = {
                blogger: 'Blogger',
                wordpress: 'WordPress'
            };
            return labels[platform] || platform;
        },

        // 모듈 타입별 색상 반환 (모듈 관리 페이지와 동일)
        getModuleColor(typeCode) {
            const colors = {
                republish: 'bg-sky-200',
                publish: 'bg-rose-200',
                generate: 'bg-amber-200',
                prompt: 'bg-green-200',
                collect: 'bg-purple-200',
                growth_profile: 'bg-emerald-200'
            };
            return colors[typeCode] || 'bg-gray-200';
        },

        // 모듈 타입 이름 반환
        getModuleTypeName(typeCode) {
            const names = {
                republish: '재발행',
                publish: '발행',
                generate: '생성',
                prompt: '프롬프트',
                collect: '수집',
                growth_profile: '성장 프로파일'
            };
            return names[typeCode] || typeCode;
        },

        // 포스트 범위 텍스트 반환
        getPostRangeText(module) {
            const start = module.post_range_start || 1;
            const end = module.post_range_end;
            if (!end) {
                return `${start}~무제한 (누적 포스트)`;
            }
            return `${start}~${end} (누적 포스트)`;
        },

        // 간격 텍스트 반환
        getIntervalText(module) {
            const mode = module.interval_mode || 'manual';
            const activeMinutes = this.calculateActiveMinutes(module);

            if (mode === 'auto' && module.auto_daily_count) {
                const minInterval = Math.ceil(activeMinutes / module.auto_daily_count);
                return `${module.auto_daily_count}회/일 (최소 ${minInterval}분 간격)`;
            } else if (module.manual_interval_minutes) {
                const maxDaily = Math.floor(activeMinutes / module.manual_interval_minutes);
                return `${module.manual_interval_minutes}분마다 (최대 ${maxDaily}회/일)`;
            }
            return "설정 없음";
        },

        // 활성 시간 계산
        calculateActiveMinutes(module) {
            if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
                return 720;
            }
            let totalActiveMinutes = 0;
            for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
                const daySchedule = module.schedule_matrix[dayIdx];
                if (Array.isArray(daySchedule)) {
                    const activeHours = daySchedule.filter(hour => hour === true).length;
                    totalActiveMinutes += activeHours * 60;
                }
            }
            return Math.round(totalActiveMinutes / 7) || 720;
        },

        // 스케줄 요약 반환
        getScheduleSummary(module) {
            if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
                return "설정 없음";
            }
            const schedule = module.schedule_matrix;
            const days = ['월', '화', '수', '목', '금', '토', '일'];
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
                return "설정 없음";
            }

            const timeGroups = {};
            for (const [dayIdx, timeRange] of Object.entries(dayRanges)) {
                if (!timeGroups[timeRange]) {
                    timeGroups[timeRange] = [];
                }
                timeGroups[timeRange].push(parseInt(dayIdx));
            }

            const groupTexts = [];
            for (const [timeRange, dayIndices] of Object.entries(timeGroups)) {
                const dayText = this.formatDayRange(dayIndices, days);
                groupTexts.push(`${dayText}(${timeRange})`);
            }
            return groupTexts.join('\n');
        },

        // 시간 범위 추출
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

        // 요일 범위 포맷
        formatDayRange(dayIndices, days) {
            if (dayIndices.length === 1) {
                return days[dayIndices[0]];
            }
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

        // ========================================
        // 슬라이드 UI 헬퍼 함수들
        // ========================================

        // 모듈 타입별 표시할 정보 아이템 반환
        getModuleInfoItems(module) {
            const items = [];
            const typeCode = module.module_type?.code || '';

            if (typeCode === 'republish') {
                items.push({ label: '범위', value: this.getPostRangeText(module) });
                items.push({ label: '간격', value: this.getIntervalText(module) });
                const schedule = this.getScheduleSummary(module);
                if (schedule !== '설정 없음') {
                    items.push({ label: '스케줄', value: schedule });
                }
            } else if (typeCode === 'publish') {
                items.push({ label: '간격', value: this.getIntervalText(module) });
                const schedule = this.getScheduleSummary(module);
                if (schedule !== '설정 없음') {
                    items.push({ label: '스케줄', value: schedule });
                }
            } else if (typeCode === 'generate') {
                if (module.ai_model) {
                    items.push({ label: 'AI', value: module.ai_model });
                }
                if (module.prompt_template) {
                    const promptPreview = module.prompt_template.substring(0, 30) + '...';
                    items.push({ label: '프롬프트', value: promptPreview });
                }
            } else if (typeCode === 'prompt') {
                if (module.prompt_name) {
                    items.push({ label: '이름', value: module.prompt_name });
                }
                if (module.category) {
                    items.push({ label: '카테고리', value: module.category });
                }
            } else if (typeCode === 'collect') {
                // 수집 모듈 정보 표시
                const settings = module.settings || {};

                // 수집 대상
                const sources = [];
                if (settings.source_naver_datalab) sources.push('데이터랩');
                if (settings.source_naver_ads) sources.push('네이버광고');
                if (settings.source_google_trends) sources.push('트렌드');
                if (settings.source_google_planner) sources.push('플래너');
                if (sources.length > 0) {
                    items.push({ label: '수집', value: sources.join(', ') });
                }

                // 수집 타입
                const typeMap = { 'keyword': '키워드', 'title': '제목', 'both': '키워드+제목' };
                if (settings.collect_type) {
                    items.push({ label: '타입', value: typeMap[settings.collect_type] || '전체' });
                }

                // 스케줄
                if (settings.schedule_mode === 'fixed_time' && settings.fixed_times?.length > 0) {
                    items.push({ label: '시간', value: settings.fixed_times.join(', ') });
                } else if (settings.schedule_mode === 'interval' && settings.interval_hours) {
                    items.push({ label: '간격', value: `${settings.interval_hours}시간` });
                }
            } else if (typeCode === 'growth_profile') {
                // 성장 프로파일 모듈 정보 표시
                const settings = module.settings || {};
                const stages = settings.stages || [];
                if (stages.length > 0) {
                    items.push({ label: '구간', value: `${stages.length}단계` });
                }
                // 활성 모듈 표시
                const activeModules = [];
                const firstStage = stages[0] || {};
                if (firstStage.generate?.enabled) activeModules.push('생성');
                if (firstStage.publish?.enabled) activeModules.push('발행');
                if (firstStage.republish?.enabled) activeModules.push('재발행');
                if (activeModules.length > 0) {
                    items.push({ label: '활성', value: activeModules.join('/') });
                }
                // 워밍업 표시
                if (settings.warmup?.enabled) {
                    items.push({ label: '워밍업', value: `${settings.warmup.warmup_days || 0}일` });
                }
            }

            // 기본 정보가 없으면 생성일 표시
            if (items.length === 0 && module.created_at) {
                const date = new Date(module.created_at).toLocaleDateString('ko-KR');
                items.push({ label: '생성일', value: date });
            }

            return items;
        },

        // 모듈 정보 텍스트 길이에 따른 슬라이드 속도 계산 (초)
        getModuleSlideDuration(module) {
            const items = this.getModuleInfoItems(module);
            // 모든 아이템의 텍스트 길이 합산
            const totalLength = items.reduce((sum, item) => {
                return sum + (item.label?.length || 0) + (item.value?.length || 0);
            }, 0);
            const baseSpeed = 12; // 기본 12초
            const perChar = 0.25; // 글자당 0.25초 추가
            const minDuration = 12; // 최소 12초
            const maxDuration = 40; // 최대 40초
            return Math.max(minDuration, Math.min(maxDuration, baseSpeed + (totalLength * perChar)));
        },

        // 블로그 개수에 따른 슬라이드 속도 계산 (초) - 20% 느림 적용
        getBlogSlideDuration(count) {
            const baseSpeed = 5.4; // 블로그당 기본 5.4초 (기존 4.5초의 1.2배)
            const minDuration = 14; // 최소 14초 (기존 12초의 1.2배)
            const maxDuration = 44; // 최대 44초 (기존 37초의 1.2배)
            const duration = Math.max(minDuration, Math.min(maxDuration, count * baseSpeed));
            return duration;
        },

        // 모듈 슬라이드 필요 여부 판단 (정보 아이템 3개 이상)
        needsModuleSlide(module) {
            const items = this.getModuleInfoItems(module);
            return items.length >= 3;
        },

        // 블로그 슬라이드 필요 여부 판단 (2개 이상이면 일단 슬라이드 활성화, 실제로는 initBlogSlideCheck에서 너비 기반 체크)
        needsBlogSlide(count) {
            return count >= 2;
        },

        // 모듈 슬라이드 초기화 체크 (DOM 너비 기반)
        // no-slide 제거 → 측정 → 결과에 따라 적용 (동기 실행으로 깜빡임 없음)
        initSlideCheck(element) {
            const container = element.querySelector('.module-slide-container');
            const track = element.querySelector('.module-slide-track');
            if (!container || !track) return;

            setTimeout(() => {
                const containerWidth = container.clientWidth;
                if (containerWidth === 0) return;

                // 측정을 위해 no-slide 일시 제거 (복제 콘텐츠 display:none 해제)
                track.classList.remove('no-slide');
                const trackWidth = track.scrollWidth / 2;

                if (trackWidth > containerWidth) {
                    // 슬라이드 필요 - no-slide 이미 제거됨
                } else {
                    // 슬라이드 불필요 - no-slide 복원
                    track.classList.add('no-slide');
                }
            }, 100);
        },

        // 블로그 슬라이드 초기화 체크 (DOM 너비 기반)
        initBlogSlideCheck(element, count) {
            const container = element.querySelector('.blog-slide-container');
            const track = element.querySelector('.blog-slide-track');
            if (!container || !track) return;

            setTimeout(() => {
                const containerWidth = container.clientWidth;
                if (containerWidth === 0) return;

                track.classList.remove('no-slide');
                const trackWidth = track.scrollWidth / 2;

                if (trackWidth > containerWidth) {
                    // 슬라이드 필요
                } else {
                    track.classList.add('no-slide');
                }
            }, 100);
        },

        // 슬라이드 재초기화 (더보기 클릭 시 호출)
        reinitSlides(containerEl) {
            if (!containerEl) return;

            // 약간의 딜레이 (x-transition 완료 대기)
            setTimeout(() => {
                // 모듈 슬라이드 재초기화
                containerEl.querySelectorAll('.module-slide-row').forEach(row => {
                    const container = row.querySelector('.module-slide-container');
                    const track = row.querySelector('.module-slide-track');
                    if (!container || !track) return;

                    const containerWidth = container.clientWidth;
                    if (containerWidth === 0) return;

                    track.classList.remove('no-slide');
                    const trackWidth = track.scrollWidth / 2;

                    if (trackWidth <= containerWidth) {
                        track.classList.add('no-slide');
                    }
                });

                // 블로그 슬라이드 재초기화
                containerEl.querySelectorAll('.blog-slide-section').forEach(section => {
                    const container = section.querySelector('.blog-slide-container');
                    const track = section.querySelector('.blog-slide-track');
                    if (!container || !track) return;

                    const containerWidth = container.clientWidth;
                    if (containerWidth === 0) return;

                    track.classList.remove('no-slide');
                    const trackWidth = track.scrollWidth / 2;

                    if (trackWidth <= containerWidth) {
                        track.classList.add('no-slide');
                    }
                });
            }, 50);
        },

        // 터치 일시정지 토글 (모바일용)
        toggleSlideTouch(event, element) {
            // 터치 이벤트에서만 동작
            if (event.type !== 'touchstart') return;

            const track = element.querySelector('.module-slide-track, .blog-slide-track');
            if (!track) return;

            // 현재 상태 토글
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
        },

        // ========================================
        // 플로우 1회 실행
        // ========================================

        // 플로우 실행
        async executeFlow(flowId) {
            if (this.executingFlowId) return;

            this.executingFlowId = flowId;
            this.executeResult = null;

            try {
                const response = await fetch(`/api/v1/flows/${flowId}/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `HTTP ${response.status}`);
                }

                const result = await response.json();
                this.executeResult = result;
                this.showExecuteResult = true;

                // 백그라운드 작업 응답 처리
                if (result.status === 'started') {
                    this.showSuccess('플로우 실행이 시작되었습니다. 결과는 실행 로그에서 확인하세요.');
                } else if (result.success) {
                    // 기존 동기 실행 응답 (하위 호환)
                    this.showSuccess(`플로우 실행 완료 (${result.duration_ms}ms)`);
                } else {
                    this.showError(`플로우 실행 실패: ${result.error}`);
                }

            } catch (error) {
                console.error('플로우 실행 오류:', error);
                this.showError(`실행 오류: ${error.message}`);
            } finally {
                this.executingFlowId = null;
            }
        },

        // 실행 결과 모달 닫기
        closeExecuteResult() {
            this.showExecuteResult = false;
            this.executeResult = null;
        },

        // 성공 메시지 표시
        showSuccess(message) {
            this.showMessage('success', message);
        },

        // 오류 메시지 표시
        showError(message) {
            this.showMessage('error', message);
        },

        // 메시지 표시 (토스트)
        showMessage(type, text) {
            // 이미 메시지가 있다면 제거
            const existingToast = document.querySelector('.message-toast');
            if (existingToast) {
                existingToast.remove();
            }

            // 새 토스트 생성
            const toast = document.createElement('div');
            toast.className = 'message-toast fixed top-4 right-4 z-60 max-w-sm';

            const bgColor = type === 'success' ? 'bg-green-50' : type === 'error' ? 'bg-red-50' : 'bg-blue-50';
            const borderColor = type === 'success' ? 'border-green-400' : type === 'error' ? 'border-red-400' : 'border-blue-400';
            const textColor = type === 'success' ? 'text-green-800' : type === 'error' ? 'text-red-800' : 'text-blue-800';
            const iconColor = type === 'success' ? 'text-green-400' : type === 'error' ? 'text-red-400' : 'text-blue-400';

            const icon = type === 'success' ?
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>' :
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>';

            toast.innerHTML = `
                <div class="bg-white rounded-lg shadow-lg border-l-4 ${borderColor} ${bgColor} p-4">
                    <div class="flex items-start">
                        <div class="flex-shrink-0">
                            <svg class="w-5 h-5 ${iconColor}" fill="currentColor" viewBox="0 0 20 20">
                                ${icon}
                            </svg>
                        </div>
                        <div class="ml-3 flex-1">
                            <p class="text-sm font-medium ${textColor}">${text}</p>
                        </div>
                        <button onclick="this.closest('.message-toast').remove()" class="ml-4 text-gray-400 hover:text-gray-600">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(toast);

            // 자동 제거 (성공 메시지만)
            if (type === 'success') {
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.remove();
                    }
                }, 3000);
            }
        }
    };
}

function flowCardState() {
    return {
        expanded: false,
        needsExpand: false,
        initCard(el) {
            setTimeout(() => {
                const content = el.querySelector('.flow-content-area');
                if (content) {
                    this.needsExpand = content.scrollHeight > 128;
                }
            }, 150);
        }
    };
}

// 전역 참조 설정
document.addEventListener('DOMContentLoaded', function() {
    const flowList = document.querySelector('[x-data*="flowListApp"]');
    if (flowList) {
        window.flowListApp = flowList._x_dataStack[0];
    }
});

// 추가 타입 선택 (전역 함수)
function selectAddType(type) {
    if (window.flowListApp) {
        window.flowListApp.selectAddType(type);
    }
}

// 선택된 아이템 추가 (전역 함수)
function addSelectedItems() {
    if (window.flowListApp) {
        window.flowListApp.addSelectedItems();
    }
}

// 슬라이드 재초기화 (전역 함수)
function reinitSlides(containerEl) {
    if (window.flowListApp) {
        window.flowListApp.reinitSlides(containerEl);
    }
}

// 모듈 슬라이드 체크 (전역 함수)
function initSlideCheck(element) {
    if (window.flowListApp) {
        window.flowListApp.initSlideCheck(element);
    }
}

// 블로그 슬라이드 체크 (전역 함수)
function initBlogSlideCheck(element, count) {
    if (window.flowListApp) {
        window.flowListApp.initBlogSlideCheck(element, count);
    }
}

// 슬라이드 터치 토글 (전역 함수)
function toggleSlideTouch(event, element) {
    if (window.flowListApp) {
        window.flowListApp.toggleSlideTouch(event, element);
    }
}

// 모듈 슬라이드 필요 여부 (전역 함수)
function needsModuleSlide(module) {
    if (window.flowListApp) {
        return window.flowListApp.needsModuleSlide(module);
    }
    return false;
}

// 블로그 슬라이드 필요 여부 (전역 함수)
function needsBlogSlide(count) {
    if (window.flowListApp) {
        return window.flowListApp.needsBlogSlide(count);
    }
    return false;
}

// 모듈 슬라이드 속도 (전역 함수)
function getModuleSlideDuration(module) {
    if (window.flowListApp) {
        return window.flowListApp.getModuleSlideDuration(module);
    }
    return 30;
}

// 블로그 슬라이드 속도 (전역 함수)
function getBlogSlideDuration(count) {
    if (window.flowListApp) {
        return window.flowListApp.getBlogSlideDuration(count);
    }
    return 22;
}

// 모듈 정보 아이템 (전역 함수)
function getModuleInfoItems(module) {
    if (window.flowListApp) {
        return window.flowListApp.getModuleInfoItems(module);
    }
    return [];
}

// 플로우 모듈 목록 (전역 함수)
function getFlowModules(flow) {
    if (window.flowListApp) {
        return window.flowListApp.getFlowModules(flow);
    }
    return flow.module_links || flow.flow_modules || [];
}

// 플로우 블로그 목록 (전역 함수)
function getFlowBlogs(flow) {
    if (window.flowListApp) {
        return window.flowListApp.getFlowBlogs(flow);
    }
    return flow.blog_links || flow.flow_blogs || [];
}

// GP 모듈 포함 여부 (전역 함수)
function flowHasGP(flow) {
    if (window.flowListApp) {
        return window.flowListApp.flowHasGP(flow);
    }
    const modules = flow.module_links || flow.flow_modules || [];
    return modules.some(m => m.module?.module_type?.code === 'growth_profile');
}

// GP 모듈 이름 (전역 함수)
function getGPModuleName(flow) {
    if (window.flowListApp) {
        return window.flowListApp.getGPModuleName(flow);
    }
    const modules = flow.module_links || flow.flow_modules || [];
    const gp = modules.find(m => m.module?.module_type?.code === 'growth_profile');
    return gp?.module?.name || '';
}

// 모듈 아이콘 (전역 함수)
function getModuleIcon(typeCode) {
    if (window.flowListApp) {
        return window.flowListApp.getModuleIcon(typeCode);
    }
    const icons = { republish: '🔄', publish: '📤', generate: '✨', prompt: '📝', collect: '🔍', growth_profile: '📈' };
    return icons[typeCode] || '📦';
}