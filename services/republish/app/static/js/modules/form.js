/**
 * 모듈 폼 JavaScript
 * Alpine.js 기반 폼 상태 관리 및 검증
 */

function moduleFormApp(module = null, moduleType = null) {
    // 모듈 데이터 초기화
    const initialModule = module || {};
    const initialType = moduleType || { code: 'republish', name: '재발행' };

    return {
        // 폼 상태
        loading: false,
        isEdit: !!initialModule?.id,
        module: initialModule,
        moduleType: initialType,

        // 폼 데이터
        formData: {
            name: initialModule?.name || '',
            type_code: initialType?.code || 'republish',
            description: initialModule?.description || '',
            manual_interval_minutes: initialModule?.manual_interval_minutes || 25,
            settings: initialModule?.settings || {},
            schedule_matrix: initialModule?.schedule_matrix || null,
            is_active: initialModule?.is_active ?? true
        },

        // 스케줄 매트릭스 (재발행 모듈용)
        days: ['월', '화', '수', '목', '금', '토', '일'],
        schedule: [],
        activeHoursCount: 0,
        todayActiveHours: 0,
        expectedDailyPosts: 0,

        // 설정 JSON (기타 타입용)
        settingsJson: '',

        // 초기화
        init() {
            this.initializeSchedule();
            this.initializeSettings();
            this.calculateStats();

            // 형식 값 갱신
            this.$nextTick(() => {
                this.updateActiveHoursCount();
                this.calculateExpectedPosts();
            });
        },

        // 스케줄 매트릭스 초기화
        initializeSchedule() {
            if (this.formData.type_code === 'republish') {
                if (this.isEdit && this.formData.schedule_matrix) {
                    this.schedule = JSON.parse(JSON.stringify(this.formData.schedule_matrix));
                } else {
                    // 기본 평일 9-21시 스케줄
                    this.schedule = Array(7).fill().map((_, dayIdx) =>
                        Array(24).fill().map((_, hour) =>
                            dayIdx < 5 && hour >= 9 && hour <= 21
                        )
                    );
                }
                this.updateActiveHoursCount();
            } else {
                this.schedule = Array(7).fill().map(() => Array(24).fill(false));
            }
        },

        // 설정 JSON 초기화
        initializeSettings() {
            if (this.formData.type_code !== 'republish') {
                try {
                    const settings = this.formData.settings || {};
                    this.settingsJson = JSON.stringify(settings, null, 2);
                    if (this.settingsJson === '{}' && !this.isEdit) {
                        this.settingsJson = '';
                    }
                } catch (e) {
                    this.settingsJson = '';
                }
            } else {
                this.settingsJson = '';
            }
        },

        // 통계 계산
        calculateStats() {
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        // 스케줄 매트릭스 조작
        toggleHour(dayIdx, hourIdx) {
            if (!this.schedule[dayIdx]) {
                this.schedule[dayIdx] = Array(24).fill(false);
            }
            this.schedule[dayIdx][hourIdx] = !this.schedule[dayIdx][hourIdx];
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        toggleDay(dayIdx) {
            if (!this.schedule[dayIdx]) {
                this.schedule[dayIdx] = Array(24).fill(false);
            }
            const allActive = this.schedule[dayIdx].every(h => h);
            this.schedule[dayIdx] = this.schedule[dayIdx].map(() => !allActive);
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        selectAllHours() {
            this.schedule = Array(7).fill().map(() => Array(24).fill(true));
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        clearAllHours() {
            this.schedule = Array(7).fill().map(() => Array(24).fill(false));
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        selectWorkingHours() {
            this.schedule = Array(7).fill().map((_, dayIdx) =>
                Array(24).fill().map((_, hour) =>
                    dayIdx < 5 && hour >= 9 && hour <= 21
                )
            );
            this.updateActiveHoursCount();
            this.calculateExpectedPosts();
        },

        // 활성 시간 수 계산
        updateActiveHoursCount() {
            let count = 0;
            this.schedule.forEach(day => {
                if (day) {
                    day.forEach(hour => {
                        if (hour) count++;
                    });
                }
            });
            this.activeHoursCount = count;

            // 오늘 요일 기준 활성 시간 계산
            const todayIdx = (new Date().getDay() + 6) % 7; // 월=0, 일=6
            this.todayActiveHours = this.schedule[todayIdx]
                ? this.schedule[todayIdx].filter(h => h).length
                : 0;
        },

        // 예상 일일 발행 수 계산
        calculateExpectedPosts() {
            if (this.formData.manual_interval_minutes && this.todayActiveHours > 0) {
                const postsPerHour = 60 / this.formData.manual_interval_minutes;
                this.expectedDailyPosts = Math.round(this.todayActiveHours * postsPerHour * 10) / 10;
            } else {
                this.expectedDailyPosts = 0;
            }
        },

        // 폼 제출
        async submitForm() {
            if (!this.validateForm()) {
                return;
            }

            this.loading = true;

            try {
                // 요청 데이터 준비
                const requestData = this.prepareRequestData();

                const url = this.isEdit
                    ? `/api/v1/modules/${this.formData.id || this.module.id}`
                    : '/api/v1/modules';

                const method = this.isEdit ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(requestData)
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.detail || '요청 처리 중 오류가 발생했습니다');
                }

                // 성공 처리
                const action = this.isEdit ? '수정' : '생성';
                this.showSuccess(`모듈이 ${action}되었습니다`);

                // 목록 새로고침
                if (window.moduleListAppInstance) {
                    await window.moduleListAppInstance.loadModules();
                }

                // 폼 닫기
                this.closeForm();

            } catch (error) {
                this.showError(error.message);
                console.error('폼 제출 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 폼 유효성 검증
        validateForm() {
            // 기본 필드 검증
            if (!this.formData.name?.trim()) {
                this.showError('모듈 이름을 입력해주세요');
                return false;
            }

            // 재발행 모듈 검증
            if (this.formData.type_code === 'republish') {
                if (!this.formData.manual_interval_minutes || this.formData.manual_interval_minutes < 15) {
                    this.showError('재발행 간격은 최소 15분 이상이어야 합니다');
                    return false;
                }

                if (this.activeHoursCount === 0) {
                    this.showError('최소 1시간 이상의 활성 스케줄을 설정해주세요');
                    return false;
                }
            }

            // 기타 타입 설정 JSON 검증
            if (this.formData.type_code !== 'republish' && this.settingsJson) {
                try {
                    JSON.parse(this.settingsJson);
                } catch (e) {
                    this.showError('설정 JSON 형식이 올바르지 않습니다');
                    return false;
                }
            }

            return true;
        },

        // 요청 데이터 준비
        prepareRequestData() {
            const data = {
                name: this.formData.name.trim(),
                type_code: this.formData.type_code,
                description: this.formData.description?.trim() || null,
                is_active: this.formData.is_active
            };

            if (this.formData.type_code === 'republish') {
                data.manual_interval_minutes = this.formData.manual_interval_minutes;
                data.schedule_matrix = this.schedule;
            } else {
                // 설정 JSON 파싱
                try {
                    data.settings = this.settingsJson ? JSON.parse(this.settingsJson) : {};
                } catch (e) {
                    data.settings = {};
                }
            }

            return data;
        },

        // 폼 닫기
        closeForm() {
            if (window.closeBottomSheet) {
                window.closeBottomSheet('moduleForm');
            }
        },

        // 알림 메시지
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

// 전역 함수로 노출
window.moduleFormApp = moduleFormApp;