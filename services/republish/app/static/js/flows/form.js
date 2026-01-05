/**
 * 플로우 폼 JavaScript
 * Alpine.js 기반 폼 관리 및 API 통신
 */

// Bottom Sheet 관리 함수들 (모듈 폼과 공통)
function showBottomSheet(sheetId) {
    const backdrop = document.getElementById(sheetId + '-backdrop');
    const sheet = document.getElementById(sheetId);

    if (backdrop && sheet) {
        backdrop.classList.remove('hidden');
        sheet.classList.remove('hidden');

        setTimeout(() => {
            backdrop.classList.add('opacity-100');
            sheet.classList.remove('translate-y-full');
        }, 10);
    }
}

function closeBottomSheet(sheetId) {
    const backdrop = document.getElementById(sheetId + '-backdrop');
    const sheet = document.getElementById(sheetId);

    if (backdrop && sheet) {
        backdrop.classList.remove('opacity-100');
        sheet.classList.add('translate-y-full');

        setTimeout(() => {
            backdrop.classList.add('hidden');
            sheet.classList.add('hidden');

            // 폼 리셋 (플로우 폼만)
            if (sheetId === 'flowForm' && window.flowFormApp) {
                window.flowFormApp.resetForm();
            }
        }, 300);
    }
}

// Selection Popup 관리 함수들
function showSelectionPopup(popupId) {
    const backdrop = document.getElementById(popupId + '-backdrop');
    const popup = document.getElementById(popupId);

    if (backdrop && popup) {
        backdrop.classList.remove('hidden');
        popup.classList.remove('hidden');

        setTimeout(() => {
            backdrop.classList.add('opacity-100');
            const popupContent = popup.querySelector('div');
            if (popupContent) {
                popupContent.classList.remove('scale-95');
                popupContent.classList.add('scale-100');
            }
        }, 10);
    }
}

function closeSelectionPopup(popupId) {
    const backdrop = document.getElementById(popupId + '-backdrop');
    const popup = document.getElementById(popupId);

    if (backdrop && popup) {
        backdrop.classList.remove('opacity-100');
        const popupContent = popup.querySelector('div');
        if (popupContent) {
            popupContent.classList.remove('scale-100');
            popupContent.classList.add('scale-95');
        }

        setTimeout(() => {
            backdrop.classList.add('hidden');
            popup.classList.add('hidden');
        }, 200);
    }
}

// 플로우 폼 데이터 관리
function flowFormData() {
    return {
        // 폼 상태
        isEditMode: false,
        saving: false,

        // 폼 데이터
        formData: {
            id: null,
            name: '',
            description: '',
            selectedModules: [],
            selectedBlogs: []
        },

        // 모듈 관련 데이터
        modules: [],
        moduleTypes: [],
        modulesLoading: true,
        activeModuleTab: 'republish',

        // 블로그 관련 데이터
        blogs: [],
        blogsLoading: true,
        activeBlogTab: 'blogger',

        // 메시지
        message: {
            text: '',
            type: 'info' // success, error, info
        },

        async init() {
            this.resetForm();
            await Promise.all([this.loadModules(), this.loadBlogs()]);
            console.log('플로우 폼 초기화 완료');
        },

        resetForm() {
            this.formData = {
                id: null,
                name: '',
                description: '',
                selectedModules: [],
                selectedBlogs: []
            };
            this.isEditMode = false;
            this.saving = false;
            this.message = { text: '', type: 'info' };
            this.activeModuleTab = 'republish';
            this.activeBlogTab = 'blogger';
        },

        async loadBlogs() {
            this.blogsLoading = true;
            try {
                const response = await fetch('/api/v1/blogs', {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('블로그 목록 조회 실패');
                }

                const data = await response.json();
                this.blogs = data.blogs || [];
                console.log('블로그 목록 로드 완료:', this.blogs.length, '개');

            } catch (error) {
                this.showError('블로그 목록을 불러올 수 없습니다');
                console.error('블로그 목록 로드 오류:', error);
            } finally {
                this.blogsLoading = false;
            }
        },

        async loadModules() {
            this.modulesLoading = true;
            try {
                const response = await fetch('/api/v1/modules', {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('모듈 목록 조회 실패');
                }

                const data = await response.json();
                this.modules = data.modules || [];
                console.log('모듈 목록 로드 완료:', this.modules.length, '개');

            } catch (error) {
                this.showError('모듈 목록을 불러올 수 없습니다');
                console.error('모듈 목록 로드 오류:', error);
            } finally {
                this.modulesLoading = false;
            }
        },

        getModulesByType(typeCode) {
            return this.modules.filter(module =>
                module.module_type && module.module_type.code === typeCode
            );
        },

        getBlogsByPlatform(platform) {
            return this.blogs.filter(blog => blog.platform === platform);
        },

        isBlogSelected(blogId) {
            return this.formData.selectedBlogs.includes(blogId);
        },

        isModuleSelected(moduleId) {
            return this.formData.selectedModules.includes(moduleId);
        },

        getModuleColor(typeCode) {
            const colors = {
                republish: 'bg-blue-100',
                publish: 'bg-green-100',
                generate: 'bg-purple-100',
                prompt: 'bg-yellow-100'
            };
            return colors[typeCode] || 'bg-gray-100';
        },

        getPostRangeText(module) {
            const start = module.post_range_start || 1;
            const end = module.post_range_end;
            if (!end) {
                return `${start}~무제한 (누적 포스트)`;
            }
            return `${start}~${end} (누적 포스트)`;
        },

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

        // 모듈 아이콘 반환
        getModuleIcon(typeCode) {
            const icons = {
                republish: '🔄',
                publish: '📤',
                generate: '✨',
                prompt: '📝'
            };
            return icons[typeCode] || '📦';
        },

        // 모듈 타입 이름 반환
        getModuleTypeName(typeCode) {
            const names = {
                republish: '재발행',
                publish: '발행',
                generate: '생성',
                prompt: '프롬프트'
            };
            return names[typeCode] || typeCode;
        },

        // 기존 플로우 데이터 로드 (편집 모드)
        async loadFlowData(flowId) {
            try {
                const response = await fetch(`/api/v1/flows/${flowId}`, {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('플로우 데이터 로드 실패');
                }

                const flow = await response.json();

                this.formData = {
                    id: flow.id,
                    name: flow.name,
                    description: flow.description || '',
                    selectedModules: (flow.module_links || []).map(link => link.module.id),
                    selectedBlogs: (flow.blog_links || []).map(link => link.blog.id)
                };

                this.isEditMode = true;

            } catch (error) {
                this.showError('플로우 데이터를 불러올 수 없습니다');
                console.error('플로우 데이터 로드 오류:', error);
            }
        },

        // 폼 유효성 검사 (버튼 활성화용 - alert 없음)
        isFormValid() {
            if (!this.formData.name.trim()) {
                return false;
            }
            return true;
        },

        // 중복 이름 검사 (제출 시에만 사용)
        checkDuplicateName() {
            if (window.flowListApp && window.flowListApp.flows) {
                const duplicateFlow = window.flowListApp.flows.find(flow =>
                    flow.name === this.formData.name.trim() &&
                    (!this.isEditMode || flow.id !== this.formData.id)
                );

                if (duplicateFlow) {
                    return duplicateFlow;
                }
            }
            return null;
        },

        // 폼 제출
        async submitForm() {
            if (!this.isFormValid()) {
                return;
            }

            // 중복 이름 검사 (제출 시에만 alert)
            const duplicateFlow = this.checkDuplicateName();
            if (duplicateFlow) {
                alert(`이미 '${this.formData.name.trim()}' 이름의 플로우가 존재합니다.`);
                return;
            }

            this.saving = true;
            this.message = { text: '', type: 'info' };

            try {
                const url = this.isEditMode ?
                    `/api/v1/flows/${this.formData.id}` :
                    '/api/v1/flows';

                const method = this.isEditMode ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        name: this.formData.name.trim(),
                        description: this.formData.description.trim() || null,
                        is_active: false,
                        module_ids: this.formData.selectedModules,
                        blog_ids: this.formData.selectedBlogs
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || `플로우 ${this.isEditMode ? '수정' : '생성'} 실패`);
                }

                const result = await response.json();

                // 성공 메시지 표시 (전역 메시지 시스템 사용)
                const action = this.isEditMode ? '수정' : '생성';
                const successMessage = `플로우가 ${action}되었습니다`;

                // list.js의 showSuccess 함수 호출
                if (window.flowListApp && typeof window.flowListApp.showSuccess === 'function') {
                    window.flowListApp.showSuccess(successMessage);
                }

                // 목록 새로고침
                if (window.flowListApp && typeof window.flowListApp.loadFlows === 'function') {
                    await window.flowListApp.loadFlows();
                }

                // 폼 즉시 닫기
                closeBottomSheet('flowForm');

            } catch (error) {
                this.showError(error.message);
                console.error('폼 제출 오류:', error);
            } finally {
                this.saving = false;
            }
        },

        // 성공 메시지 표시
        showSuccess(text) {
            this.message = {
                text: text,
                type: 'success'
            };
        },

        // 오류 메시지 표시
        showError(text) {
            this.message = {
                text: text,
                type: 'error'
            };
        },

        // 정보 메시지 표시
        showInfo(text) {
            this.message = {
                text: text,
                type: 'info'
            };
        }
    };
}

// 전역 참조 설정 및 이벤트 리스너
document.addEventListener('DOMContentLoaded', function() {
    // 플로우 폼 앱 전역 참조 (약간의 지연 후)
    setTimeout(() => {
        const flowForm = document.querySelector('[x-data*="flowFormData"]');
        if (flowForm && flowForm._x_dataStack && flowForm._x_dataStack[0]) {
            window.flowFormApp = flowForm._x_dataStack[0];
            console.log('플로우 폼 앱 전역 참조 설정 완료:', window.flowFormApp);
        } else {
            console.warn('플로우 폼 Alpine.js 인스턴스를 찾을 수 없습니다');
        }
    }, 100);

    // ESC 키로 팝업/시트 닫기
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // 열린 팝업들 확인 및 닫기
            const visibleBackdrops = document.querySelectorAll('[id$="-backdrop"]:not(.hidden)');
            if (visibleBackdrops.length > 0) {
                const lastBackdrop = visibleBackdrops[visibleBackdrops.length - 1];
                const popupId = lastBackdrop.id.replace('-backdrop', '');

                if (popupId.includes('Selector')) {
                    closeSelectionPopup(popupId);
                } else {
                    closeBottomSheet(popupId);
                }
            }
        }
    });

    // 클릭으로 백드롭 닫기 방지 (이벤트 전파 중단)
    document.addEventListener('click', function(e) {
        // 팝업/시트 내부 클릭 시 이벤트 전파 중단
        if (e.target.closest('[id^="flowForm"], [id^="addSelector"], [id^="itemSelector"]')) {
            if (!e.target.closest('button[onclick*="close"]')) {
                e.stopPropagation();
            }
        }
    });
});

// 유틸리티 함수들
function validateFlowName(name) {
    if (!name || name.trim().length === 0) {
        return '플로우 이름을 입력해주세요';
    }

    if (name.trim().length > 100) {
        return '플로우 이름은 100자를 초과할 수 없습니다';
    }

    return null;
}

function validateFlowDescription(description) {
    if (description && description.length > 500) {
        return '설명은 500자를 초과할 수 없습니다';
    }

    return null;
}

// 디버깅용 함수
function debugFlowForm() {
    console.log('Flow Form Debug Info:');
    console.log('- flowFormApp:', window.flowFormApp);
    console.log('- formData:', window.flowFormApp?.formData);
    console.log('- isEditMode:', window.flowFormApp?.isEditMode);
    console.log('- saving:', window.flowFormApp?.saving);
    console.log('- message:', window.flowFormApp?.message);
}

// 개발 모드에서만 디버깅 함수 전역 노출
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.debugFlowForm = debugFlowForm;
}