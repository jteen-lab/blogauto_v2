/**
 * 플로우 폼 JavaScript
 * Alpine.js 기반 폼 관리 및 API 통신
 */

// 스크롤 위치 저장용 변수
let savedScrollPosition = 0;

// Bottom Sheet 관리 함수들 (모듈 폼과 공통)
function showBottomSheet(sheetId) {
    const backdrop = document.getElementById(sheetId + '-backdrop');
    const sheet = document.getElementById(sheetId);

    if (backdrop && sheet) {
        // 모바일에서 body 스크롤 고정
        savedScrollPosition = window.pageYOffset;
        document.body.classList.add('sheet-open');
        document.body.style.top = `-${savedScrollPosition}px`;

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

            // body 스크롤 복원
            document.body.classList.remove('sheet-open');
            document.body.style.top = '';
            window.scrollTo(0, savedScrollPosition);

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
        activeModuleTab: 'prompt_generate',

        // 블로그 관련 데이터
        blogs: [],
        blogsLoading: true,
        activeBlogTab: 'wordpress',

        // 메시지
        message: {
            text: '',
            type: 'info' // success, error, info
        },

        // 프롬프트 모듈 블로그 연동
        promptLinkedBlogIds: [],

        // 모듈 실행 상태
        executingModuleId: null,
        // 블로그 실행 상태 (예: "5_publish", "3_republish")
        executingBlogAction: null,

        // GP(Growth Profile) 관련 상태
        flowHasGP: false,
        gpModuleName: '',
        gpSettings: null,
        blogStageMap: {},

        async init() {
            this.resetForm();
            await Promise.all([this.loadModules(), this.loadBlogs()]);

            // 참고: 모듈/블로그 선택 변경은 체크박스 @change 이벤트로 처리
            // Alpine.js $watch는 배열 인플레이스 변경(.push/.splice)을 감지하지 못함
            // → onModuleSelectionChange(), onBlogSelectionChange()에서 직접 처리

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
            this.activeModuleTab = 'prompt_generate';
            this.activeBlogTab = 'wordpress';
            this.promptLinkedBlogIds = [];
            if (this.resetGPState) this.resetGPState();
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
                this.blogs = Array.isArray(data) ? data : (data.blogs || []);
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
            if (typeCode === 'prompt_generate') {
                return this.modules.filter(module =>
                    module.module_type && ['prompt', 'generate'].includes(module.module_type.code)
                );
            }
            return this.modules.filter(module =>
                module.module_type && module.module_type.code === typeCode
            );
        },

        getSelectedCountByTypes(typeCodes) {
            return this.modules.filter(module =>
                module.module_type &&
                typeCodes.includes(module.module_type.code) &&
                this.formData.selectedModules.includes(module.id)
            ).length;
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
            // 모듈 관리 페이지와 동일한 색상 적용
            const colors = {
                generate: 'bg-amber-200',
                prompt: 'bg-green-200',
                collect: 'bg-purple-200',
                bulk_collect: 'bg-sky-200',
                data: 'bg-teal-200',
                growth_profile: 'bg-emerald-200',
                contact_form: 'bg-fuchsia-200'
            };
            return colors[typeCode] || 'bg-gray-200';
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
                generate: '✨',
                prompt: '📝',
                prompt_generate: '📝✨',
                collect: '🔍',
                bulk_collect: '🚀',
                data: '📊',
                growth_profile: '📈',
                contact_form: '📋'
            };
            return icons[typeCode] || '📦';
        },

        // 모듈 타입 이름 반환
        getModuleTypeName(typeCode) {
            const names = {
                generate: '생성',
                prompt: '프롬프트',
                prompt_generate: '프롬프트/생성',
                collect: '수집',
                bulk_collect: '대량 수집',
                data: '데이터',
                growth_profile: '성장 프로파일',
                contact_form: '애드센스 필수구성'
            };
            return names[typeCode] || typeCode;
        },

        // 모듈 카드 정보 반환 (타입별)
        getModuleCardInfo(module) {
            const typeCode = module.module_type?.code;
            const settings = module.settings || {};
            const info = [];

            if (typeCode === 'prompt') {
                // 블로그 수
                const bcm = settings.blog_category_map || [];
                const blogCount = new Set(bcm.map(m => m.blog_id)).size;
                if (blogCount > 0) info.push({ label: '블로그', value: `${blogCount}개 연결` });
                // 카테고리 수
                const catCount = bcm.length;
                if (catCount > 0) info.push({ label: '카테고리', value: `${catCount}개` });
            } else if (typeCode === 'generate') {
                const cg = settings.content_generation || {};
                if (cg.provider) info.push({ label: 'AI', value: cg.provider });
                if (settings.image_generation?.enabled) info.push({ label: '이미지', value: settings.image_generation.provider || 'ON' });
            } else if (typeCode === 'collect') {
                info.push({ label: '수집 대상', value: this.getCollectSourcesText(module) });
                info.push({ label: '수집 타입', value: this.getCollectTypeText(module) });
            } else if (typeCode === 'data') {
                if (settings.target_type) info.push({ label: '이동 대상', value: settings.target_type });
            } else if (typeCode === 'growth_profile') {
                const stages = settings.stages || [];
                if (stages.length > 0) info.push({ label: '단계', value: `${stages.length}개` });
            }

            return info;
        },

        // 모듈 실행 버튼 라벨
        getModuleExecLabel(typeCode) {
            const labels = {
                prompt: '▶️ 1회 생성',
                generate: '▶️ 1회 생성',
                collect: '▶️ 1회 수집',
                data: '▶️ 1회 이동',
                contact_form: '▶️ 필수구성 생성'
            };
            return labels[typeCode] || '▶️ 실행';
        },

        // 모듈 실행 버튼 색상 클래스
        getModuleExecBtnClass(typeCode) {
            const classes = {
                prompt: 'bg-green-100 text-green-700 hover:bg-green-200',
                generate: 'bg-green-100 text-green-700 hover:bg-green-200',
                collect: 'bg-purple-100 text-purple-700 hover:bg-purple-200',
                data: 'bg-teal-100 text-teal-700 hover:bg-teal-200',
                contact_form: 'bg-fuchsia-100 text-fuchsia-700 hover:bg-fuchsia-200'
            };
            return classes[typeCode] || 'bg-gray-100 text-gray-700 hover:bg-gray-200';
        },

        // 모듈 개별 실행
        async executeModule(moduleId, typeCode) {
            if (this.executingModuleId || !this.formData.id) return;

            this.executingModuleId = moduleId;
            try {
                const resp = await fetch(
                    `/api/v1/flows/${this.formData.id}/modules/${moduleId}/execute`,
                    { method: 'POST', credentials: 'include' }
                );

                const result = await resp.json();

                if (!resp.ok) {
                    this.executingModuleId = null;
                    this.showError(result.detail || '모듈 실행 실패');
                    return;
                }

                // 백그라운드 실행 (prompt/generate) — 폴링으로 완료 대기
                if (result.status === 'started') {
                    this.showSuccess('생성을 시작했습니다. 완료까지 잠시 대기합니다...');
                    await this._pollModuleExecStatus(result.execution_id);
                    return;
                }

                // Celery 큐에 등록됨 (기능 플래그 활성화 시)
                if (result.status === 'queued') {
                    this.executingModuleId = null;
                    const taskInfo = result.task_ids
                        ? `${result.task_ids.length}건`
                        : (result.task_id ? '1건' : '');
                    this.showSuccess(
                        `${result.module_name}: Celery 큐에 등록되었습니다 ${taskInfo} (실행은 백그라운드에서 진행)`
                    );
                    return;
                }

                // 동기 실행 완료 (collect/data)
                this.executingModuleId = null;
                const results = result.results || [];
                const successCount = results.filter(r => r.status === 'success').length;
                const totalCount = results.length;
                this.showSuccess(`${result.module_name}: ${successCount}/${totalCount}건 완료 (${result.duration_ms}ms)`);

            } catch (error) {
                this.executingModuleId = null;
                this.showError('모듈 실행 중 오류가 발생했습니다');
                console.error('모듈 실행 오류:', error);
            }
        },

        // 백그라운드 실행 상태 폴링 (5초 간격, 최대 5분)
        async _pollModuleExecStatus(executionId) {
            const maxAttempts = 60;
            const intervalMs = 5000;

            for (let i = 0; i < maxAttempts; i++) {
                await new Promise(r => setTimeout(r, intervalMs));
                try {
                    const resp = await fetch(
                        `/api/v1/flows/module-exec/${executionId}/status`,
                        { credentials: 'include' }
                    );
                    if (!resp.ok) continue;

                    const state = await resp.json();
                    if (state.status === 'completed') {
                        this.executingModuleId = null;
                        this.showSuccess(`생성 완료: ${state.message}`);
                        return;
                    }
                    if (state.status === 'failed') {
                        this.executingModuleId = null;
                        this.showError(`생성 실패: ${state.message}`);
                        return;
                    }
                    // still running — keep polling
                } catch (e) {
                    console.warn('[pollModuleExec] 폴링 오류:', e);
                }
            }
            // 타임아웃
            this.executingModuleId = null;
            this.showError('생성 시간이 초과되었습니다. 생성 이력에서 결과를 확인하세요.');
        },

        // 블로그별 발행/재발행 실행
        async executeBlogAction(blogId, action) {
            if (this.executingBlogAction || !this.formData.id) return;

            this.executingBlogAction = blogId + '_' + action;
            const actionLabel = action === 'publish' ? '발행' : '재발행';

            try {
                const resp = await fetch(
                    `/api/v1/flows/${this.formData.id}/blogs/${blogId}/${action}`,
                    { method: 'POST', credentials: 'include' }
                );

                const result = await resp.json();

                if (!resp.ok) {
                    this.showError(result.detail || `${actionLabel} 실패`);
                    return;
                }

                if (result.result?.success) {
                    const detail = result.result.post_title
                        ? `"${result.result.post_title}" ${actionLabel} 완료`
                        : `${result.blog_name} ${actionLabel} 완료`;
                    this.showSuccess(`${detail} (${result.duration_ms}ms)`);
                } else {
                    this.showError(result.result?.detail || `${actionLabel} 실패`);
                }

            } catch (error) {
                this.showError(`${actionLabel} 중 오류가 발생했습니다`);
                console.error(`${actionLabel} 실행 오류:`, error);
            } finally {
                this.executingBlogAction = null;
            }
        },

        // 수집 모듈 - 수집 대상 텍스트 반환
        getCollectSourcesText(module) {
            const settings = module.settings || {};
            const sources = [];
            if (settings.source_naver_datalab) sources.push('네이버 데이터랩');
            if (settings.source_naver_ads) sources.push('네이버 광고');
            if (settings.source_google_trends) sources.push('구글 트렌드');
            if (settings.source_google_planner) sources.push('구글 플래너');
            return sources.length > 0 ? sources.join(', ') : '설정 없음';
        },

        // 수집 모듈 - 수집 타입 텍스트 반환
        getCollectTypeText(module) {
            const settings = module.settings || {};
            const typeMap = {
                'keyword': '키워드만',
                'title': '제목만',
                'both': '키워드+제목'
            };
            return typeMap[settings.collect_type] || '전체';
        },

        // 수집 모듈 - 스케줄 텍스트 반환
        getCollectScheduleText(module) {
            const settings = module.settings || {};
            if (settings.schedule_mode === 'fixed_time') {
                const times = settings.fixed_times || [];
                return times.length > 0 ? `고정시간: ${times.join(', ')}` : '설정 없음';
            } else if (settings.schedule_mode === 'interval') {
                return `${settings.interval_hours || 6}시간 간격`;
            }
            return '설정 없음';
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

                // 프롬프트 모듈 블로그 동기화
                this.syncPromptModuleBlogs();

                // GP 모듈 감지 및 프리뷰 로드
                this.detectGPModule(flow);

            } catch (error) {
                this.showError('플로우 데이터를 불러올 수 없습니다');
                console.error('플로우 데이터 로드 오류:', error);
            }
        },

        // 프롬프트 모듈 블로그 자동 동기화
        syncPromptModuleBlogs() {
            const selectedPromptModules = this.modules.filter(m =>
                m.module_type?.code === 'prompt' &&
                this.formData.selectedModules.includes(m.id)
            );

            // 프롬프트 모듈들의 블로그 ID 수집
            const newLinkedIds = new Set();
            for (const mod of selectedPromptModules) {
                const bcm = mod.settings?.blog_category_map;
                if (bcm && bcm.length > 0) {
                    // blog_category_map에서 고유 blog_id 추출
                    bcm.forEach(m => {
                        if (typeof m.blog_id === 'number') newLinkedIds.add(m.blog_id);
                    });
                } else {
                    // 레거시: settings.blogs 사용
                    const blogIds = mod.settings?.blogs || [];
                    blogIds.forEach(item => {
                        const id = typeof item === 'number' ? item : item?.id;
                        if (typeof id === 'number') newLinkedIds.add(id);
                    });
                }
            }

            const prevLinkedIds = new Set(this.promptLinkedBlogIds);
            const newLinkedArray = [...newLinkedIds];

            // 이전에 자동 추가된 블로그 중 더이상 연동 대상이 아닌 것 제거
            for (const blogId of prevLinkedIds) {
                if (!newLinkedIds.has(blogId)) {
                    const idx = this.formData.selectedBlogs.indexOf(blogId);
                    if (idx !== -1) {
                        this.formData.selectedBlogs.splice(idx, 1);
                    }
                }
            }

            // 새로 연동된 블로그 추가
            for (const blogId of newLinkedIds) {
                if (!this.formData.selectedBlogs.includes(blogId)) {
                    this.formData.selectedBlogs.push(blogId);
                }
            }

            this.promptLinkedBlogIds = newLinkedArray;

            // 배열 재할당으로 Alpine 반응성 보장
            // (.push/.splice 인플레이스 변경은 Alpine이 감지 못할 수 있음)
            this.formData.selectedBlogs = [...this.formData.selectedBlogs];

            // 프롬프트 연동 블로그가 있으면 안내
            if (newLinkedArray.length > 0) {
                console.log('[syncPromptModuleBlogs] 프롬프트 연동 블로그:', newLinkedArray.length, '개');
            }

            // 블로그 변경 후 GP stageMap도 갱신
            if (this.flowHasGP && !this.isEditMode && this.gpSettings) {
                this._buildLocalGPStageMap(this.gpSettings);
            }
        },

        // 모듈 체크박스 변경 시 호출 (@change 이벤트)
        onModuleSelectionChange() {
            // 체크박스 value는 문자열 → 숫자로 정규화 (API module.id는 숫자)
            this.formData.selectedModules = this.formData.selectedModules.map(Number);
            console.log('[onModuleSelectionChange] selectedModules:', JSON.stringify(this.formData.selectedModules));
            this.syncPromptModuleBlogs();
            this.updateGPFromSelection();
        },

        // 블로그 체크박스 변경 시 호출 (@change 이벤트)
        onBlogSelectionChange() {
            // 체크박스 value는 문자열 → 숫자로 정규화 (API blog.id는 숫자)
            this.formData.selectedBlogs = this.formData.selectedBlogs.map(Number);
            if (this.flowHasGP && !this.isEditMode && this.gpSettings) {
                this._buildLocalGPStageMap(this.gpSettings);
            }
        },

        // 프롬프트 연동 블로그 여부 확인
        isPromptLinkedBlog(blogId) {
            return this.promptLinkedBlogIds.includes(blogId);
        },

        // 선택된 프롬프트 모듈 존재 여부
        hasSelectedPromptModule() {
            return this.modules.some(m =>
                m.module_type?.code === 'prompt' &&
                this.formData.selectedModules.includes(m.id)
            );
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

        // GP 모듈 감지
        detectGPModule(flow) {
            const moduleLinks = flow.module_links || [];
            const gpLink = moduleLinks.find(link =>
                link.module?.module_type?.code === 'growth_profile'
            );
            if (gpLink) {
                this.flowHasGP = true;
                this.gpModuleName = gpLink.module.name || '';
                this.gpSettings = gpLink.module.settings || {};
                this.loadGPPreview(flow.id, this.gpSettings);
            } else {
                this.resetGPState();
            }
        },

        // GP 프리뷰 로드 (편집 모드에서 사용)
        async loadGPPreview(flowId, gpSettings) {
            try {
                // flow_id는 Query 파라미터, settings는 Body (embed=False)
                const url = '/api/v1/growth-profile/preview' + (flowId ? '?flow_id=' + flowId : '');
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(gpSettings),
                });
                console.log('[loadGPPreview] resp status:', resp.status, 'flowId:', flowId);
                if (!resp.ok) return;
                const data = await resp.json();
                console.log('[loadGPPreview] blogs count:', (data.blogs || []).length, 'data:', JSON.stringify(data).substring(0, 500));
                const stageMap = {};
                (data.blogs || []).forEach(b => {
                    stageMap[b.blog_id] = {
                        stageName: b.stage_label || b.stage_name,
                        summary: [b.generate, b.publish, b.republish].filter(Boolean).join(' / '),
                        publishEnabled: b.publish_enabled || false,
                        republishEnabled: b.republish_enabled || false,
                    };
                });
                this.blogStageMap = stageMap;
                console.log('[loadGPPreview] blogStageMap:', JSON.stringify(stageMap));
            } catch (error) {
                console.error('GP 프리뷰 로드 오류:', error);
            }
        },

        // 선택된 모듈에서 GP 감지 (생성/편집 모드 공통)
        updateGPFromSelection() {
            const gpModule = this.modules.find(m =>
                m.module_type?.code === 'growth_profile' &&
                this.formData.selectedModules.includes(m.id)
            );

            console.log('[updateGPFromSelection] gpModule found:', !!gpModule, 'isEditMode:', this.isEditMode);

            if (!gpModule) {
                this.resetGPState();
                return;
            }

            this.flowHasGP = true;
            this.gpModuleName = gpModule.name || '';
            this.gpSettings = gpModule.settings || {};
            console.log('[updateGPFromSelection] gpSettings stages:', this.gpSettings?.stages?.length, 'settings keys:', Object.keys(this.gpSettings));

            if (this.isEditMode && this.formData.id) {
                // 편집 모드: API로 정확한 블로그별 스테이지 로드
                this.loadGPPreview(this.formData.id, this.gpSettings);
            } else {
                // 생성 모드: GP 설정에서 직접 활성화 상태 추출
                this._buildLocalGPStageMap(this.gpSettings);
            }
        },

        // GP 설정에서 로컬로 blogStageMap 구성 (생성 모드용).
        // 각 블로그의 total_post_count로 stages에서 해당 구간 선택.
        // post_count_min/post_count_max (inclusive) 기준 매칭.
        _buildLocalGPStageMap(gpSettings) {
            const stages = gpSettings?.stages || [];
            if (stages.length === 0) {
                this.blogStageMap = {};
                return;
            }

            // 블로그 ID → post_count 빠른 조회용 맵
            const blogPostCounts = {};
            (this.blogs || []).forEach(b => {
                blogPostCounts[b.id] = b.total_post_count || 0;
            });

            // 한 블로그의 post_count로 해당 stage 찾기
            const resolveStage = (postCount) => {
                for (let i = 0; i < stages.length; i++) {
                    const s = stages[i];
                    const minV = s.post_count_min ?? 0;
                    const maxV = s.post_count_max;
                    if (maxV === null || maxV === undefined) {
                        if (postCount >= minV) return s;
                    } else if (postCount >= minV && postCount <= maxV) {
                        return s;
                    }
                }
                return stages[stages.length - 1];  // fallback: 마지막 stage
            };

            const stageMap = {};
            this.formData.selectedBlogs.forEach(blogId => {
                const postCount = blogPostCounts[blogId] || 0;
                const stage = resolveStage(postCount) || {};
                const publishEnabled = stage.publish?.enabled || false;
                const republishEnabled = stage.republish?.enabled || false;
                const stageName = stage.label || stage.name || '기본';
                const summaryParts = [];
                if (stage.generate?.enabled) summaryParts.push('생성');
                if (publishEnabled) summaryParts.push('발행');
                if (republishEnabled) summaryParts.push('재발행');
                stageMap[blogId] = {
                    stageName,
                    summary: summaryParts.join(' / '),
                    publishEnabled,
                    republishEnabled,
                };
            });
            this.blogStageMap = stageMap;
            console.log('[_buildLocalGPStageMap] post_count별 분류 완료:',
                JSON.stringify(blogPostCounts), '→', JSON.stringify(this.blogStageMap));
        },

        // GP 상태 리셋
        resetGPState() {
            this.flowHasGP = false;
            this.gpModuleName = '';
            this.gpSettings = null;
            this.blogStageMap = {};
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
                        description: this.formData.description.trim(),
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