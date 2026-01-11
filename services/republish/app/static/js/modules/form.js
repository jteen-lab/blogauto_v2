/**
 * 모듈 폼 JavaScript
 * Alpine.js 기반 폼 상태 관리 및 검증
 */

function moduleFormApp(module = null, moduleType = null) {
    // 모듈 데이터 초기화
    const initialModule = module || {};
    const initialType = moduleType || { code: null, name: '' };

    return {
        // 폼 상태
        loading: false,
        isEdit: !!initialModule?.id,
        module: initialModule,
        moduleType: initialType,

        // 폼 데이터
        formData: {
            name: initialModule?.name || '',
            type_code: initialType?.code || null,
            description: initialModule?.description || '',
            manual_interval_minutes: initialModule?.manual_interval_minutes || 25,
            settings: initialModule?.settings || {},
            schedule_matrix: initialModule?.schedule_matrix || null,
            is_active: initialModule?.is_active ?? true,
            // 새로운 재발행 조건 필드들
            min_post_count: initialModule?.min_post_count || 10,
            post_range_start: initialModule?.post_range_start || 1,
            post_range_end: initialModule?.post_range_end || null,
            // 새로운 간격 설정 필드들
            interval_mode: initialModule?.interval_mode || 'manual',
            auto_daily_count: initialModule?.auto_daily_count || 5
        },

        // 스케줄 매트릭스 (재발행 모듈용)
        days: ['월', '화', '수', '목', '금', '토', '일'],
        schedule: [],
        activeHoursCount: 0,
        todayActiveHours: 0,
        expectedDailyPosts: 0,

        // 간격 설정 계산 관련
        calculatedDailyCount: 0,
        calculatedInterval: 0,

        // 설정 JSON (기타 타입용)
        settingsJson: '',

        // 초기화
        init() {
            console.log('moduleFormApp init 시작', {
                module: this.module,
                moduleType: this.moduleType,
                formData: this.formData,
                isEdit: this.isEdit
            });

            this.initializeSchedule();
            this.initializeSettings();
            this.calculateStats();

            // Alpine.js $nextTick이 사용 가능한지 확인
            if (this.$nextTick) {
                this.$nextTick(() => {
                    this.updateActiveHoursCount();
                    this.calculateExpectedPosts();
                    console.log('moduleFormApp init 완료');
                });
            } else {
                // $nextTick이 없으면 setTimeout 사용
                setTimeout(() => {
                    this.updateActiveHoursCount();
                    this.calculateExpectedPosts();
                    console.log('moduleFormApp init 완료 (fallback)');
                }, 100);
            }
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

            // 간격 설정 모드에 따라 계산
            if (this.formData.interval_mode === 'manual') {
                this.calculateFromInterval();
            } else if (this.formData.interval_mode === 'auto') {
                this.calculateFromDailyCount();
            }
        },

        // 스케줄 매트릭스 조작
        toggleHour(dayIdx, hourIdx) {
            if (!this.schedule[dayIdx]) {
                this.schedule[dayIdx] = Array(24).fill(false);
            }
            this.schedule[dayIdx][hourIdx] = !this.schedule[dayIdx][hourIdx];
            this.calculateStats();
        },

        toggleDay(dayIdx) {
            if (!this.schedule[dayIdx]) {
                this.schedule[dayIdx] = Array(24).fill(false);
            }
            const allActive = this.schedule[dayIdx].every(h => h);
            this.schedule[dayIdx] = this.schedule[dayIdx].map(() => !allActive);
            this.calculateStats();
        },

        selectAllHours() {
            this.schedule = Array(7).fill().map(() => Array(24).fill(true));
            this.calculateStats();
        },

        clearAllHours() {
            this.schedule = Array(7).fill().map(() => Array(24).fill(false));
            this.calculateStats();
        },

        selectWorkingHours() {
            this.schedule = Array(7).fill().map((_, dayIdx) =>
                Array(24).fill().map((_, hour) =>
                    dayIdx < 5 && hour >= 9 && hour <= 21
                )
            );
            this.calculateStats();
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

        // 간격에서 일일 발행 수 계산 (Manual 모드)
        calculateFromInterval() {
            if (this.formData.manual_interval_minutes && this.todayActiveHours > 0) {
                const postsPerHour = 60 / this.formData.manual_interval_minutes;
                this.calculatedDailyCount = Math.round(this.todayActiveHours * postsPerHour * 10) / 10;
            } else {
                this.calculatedDailyCount = 0;
            }
        },

        // 일일 발행 수에서 간격 계산 (Auto 모드)
        calculateFromDailyCount() {
            if (this.formData.auto_daily_count && this.todayActiveHours > 0) {
                const requiredInterval = (this.todayActiveHours * 60) / this.formData.auto_daily_count;
                this.calculatedInterval = Math.max(15, Math.round(requiredInterval));

                // Auto 모드에서는 계산된 간격을 manual_interval_minutes에 반영
                this.formData.manual_interval_minutes = this.calculatedInterval;
            } else {
                this.calculatedInterval = 15;
                this.formData.manual_interval_minutes = 15;
            }
        },

        // 폼 제출
        async submitForm() {
            if (!this.validateForm()) {
                return;
            }

            // 중복 제출 방지
            if (this.loading) {
                console.log('[submitForm] 이미 처리 중입니다. 중복 제출 방지');
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
                    // 동적 레이아웃 재적용
                    setTimeout(() => {
                        window.moduleListAppInstance.applyDynamicLayout();
                    }, 100);
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

            // 동일 타입 내 중복 이름 검증
            if (window.moduleListAppInstance) {
                const existingModules = window.moduleListAppInstance.getModulesByType(this.formData.type_code);
                const duplicateModule = existingModules.find(module =>
                    module.name === this.formData.name.trim() &&
                    (!this.isEdit || module.id !== (this.formData.id || this.module.id))
                );

                if (duplicateModule) {
                    const typeName = window.moduleListAppInstance.getModuleTypeName(this.formData.type_code);
                    this.showError(`${typeName} 모듈에 이미 '${this.formData.name.trim()}' 이름이 존재합니다`);
                    return false;
                }
            }

            // 재발행 모듈 검증
            if (this.formData.type_code === 'republish') {
                // 재발행 조건 검증
                if (!this.formData.min_post_count || this.formData.min_post_count < 1) {
                    this.showError('재발행 가능 최소 포스트 수는 1개 이상이어야 합니다');
                    return false;
                }

                if (!this.formData.post_range_start || this.formData.post_range_start < 1) {
                    this.showError('재발행 적용 구간 시작값은 1 이상이어야 합니다');
                    return false;
                }

                if (this.formData.post_range_end && this.formData.post_range_end < this.formData.post_range_start) {
                    this.showError('재발행 적용 구간 종료값은 시작값보다 커야 합니다');
                    return false;
                }

                // 간격 설정 모드 검증
                if (!this.formData.interval_mode) {
                    this.showError('간격 설정 모드를 선택해주세요');
                    return false;
                }

                if (this.formData.interval_mode === 'auto') {
                    if (!this.formData.auto_daily_count || this.formData.auto_daily_count < 1) {
                        this.showError('하루 목표 발행 횟수는 1회 이상이어야 합니다');
                        return false;
                    }
                }

                // 간격 검증
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
            // description: 빈 문자열도 명시적으로 전송 (null로 변환하지 않음)
            const descriptionValue = this.formData.description?.trim();

            const data = {
                name: this.formData.name.trim(),
                module_type_code: this.formData.type_code,
                description: descriptionValue !== undefined ? descriptionValue : null,
            };

            // 디버깅: 요청 데이터 로깅
            console.log('[prepareRequestData] 모듈 타입:', this.formData.type_code);
            console.log('[prepareRequestData] 전송 데이터:', data);

            if (this.formData.type_code === 'republish') {
                data.schedule_matrix = this.schedule;

                // 재발행 조건 필드들
                data.min_post_count = this.formData.min_post_count;
                data.post_range_start = this.formData.post_range_start;
                data.post_range_end = this.formData.post_range_end || null;

                // 간격 설정 필드들 (항상 둘 다 저장)
                data.interval_mode = this.formData.interval_mode;
                data.manual_interval_minutes = this.formData.manual_interval_minutes;
                data.auto_daily_count = this.formData.auto_daily_count;
            } else {
                // 설정 JSON 파싱
                try {
                    // settings 필드 제거 (스키마에 없음)
                } catch (e) {
                    // 제거됨
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