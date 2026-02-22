/**
 * Growth Profile 모듈 폼 Alpine.js 상태 및 로직
 * _growth_profile_form.html과 함께 사용
 *
 * @description 성장 프로필 모듈의 프리셋, 활성 시간대, 지터,
 *              성장 구간, 워밍업 설정을 관리합니다.
 *              form.js에서 window.createGrowthProfileState() 호출로 초기화됩니다.
 */
function createGrowthProfileState() {
    return {
        // --- 프리셋 ---
        selectedPreset: 'balanced',
        presets: [
            {
                key: 'aggressive',
                name: '공격적 성장',
                description: '빠른 콘텐츠 축적, 발행 빈도 극대화',
                stageCount: 3,
                warmupEnabled: true
            },
            {
                key: 'balanced',
                name: '균형 성장',
                description: '균형 잡힌 생성/발행/재발행 설정',
                stageCount: 3,
                warmupEnabled: true
            },
            {
                key: 'conservative',
                name: '보수적 운영',
                description: '안정적 운영, 느린 생성',
                stageCount: 3,
                warmupEnabled: false
            }
        ],

        // --- 활성 시간대 ---
        schedule_matrix: null, // initFromSettings 또는 loadPreset에서 설정
        days: ['월', '화', '수', '목', '금', '토', '일'],

        // --- 지터 ---
        jitter: { enabled: true, min_percent: -20, max_percent: 30 },

        // --- 성장 구간 ---
        stages: [],

        // --- 워밍업 ---
        warmup: {
            enabled: true,
            warmup_days: 14,
            initial_daily_posts: 1,
            max_daily_posts: 3,
            ramp_rate: 0.5
        },

        // --- 프리뷰 ---
        previewBlogs: [],
        previewLoading: false,

        // --- 검증 ---
        validationError: null,

        // --- Computed Getters ---

        /** 전체 활성 시간 수 (주간 합계) */
        get activeHoursCount() {
            if (!this.schedule_matrix) return 0;
            return this.schedule_matrix.flat().filter(Boolean).length;
        },

        /** 오늘 요일 기준 활성 시간 수 (JS Sunday=0 -> Monday=0 변환) */
        get todayActiveHours() {
            if (!this.schedule_matrix) return 16;
            const dayIdx = (new Date().getDay() + 6) % 7;
            return this.schedule_matrix[dayIdx].filter(Boolean).length || 16;
        },

        /** 워밍업 시뮬레이션 - 주요 시점의 예상 발행량과 간격 */
        get warmupSimulation() {
            if (!this.warmup.enabled) return [];
            const { initial_daily_posts, max_daily_posts, ramp_rate, warmup_days } = this.warmup;
            const activeHours = this.todayActiveHours || 16;
            const sims = [];
            for (const day of [0, 2, 4, 7, 10, 14]) {
                if (day > warmup_days) break;
                const daily = Math.min(
                    initial_daily_posts + Math.floor(day * ramp_rate),
                    max_daily_posts
                );
                const interval = daily > 0 ? Math.floor((activeHours * 60) / daily) : 0;
                sims.push({ day, daily, interval });
            }
            return sims;
        },

        // --- 프리셋 관련 메서드 ---

        /** 프리셋 로드 - API 호출로 프리셋 데이터를 가져와 상태에 반영 */
        async loadPreset(key) {
            this.selectedPreset = key;
            this.validationError = null;
            try {
                const response = await fetch(`/api/v1/growth-profile/presets/${key}`, {
                    credentials: 'include'
                });
                if (!response.ok) {
                    throw new Error('프리셋 로드 실패');
                }
                const data = await response.json();
                // 각 필드를 deep copy하여 반영
                this.schedule_matrix = JSON.parse(JSON.stringify(
                    data.schedule_matrix || this._makeDefaultMatrix()
                ));
                this.jitter = JSON.parse(JSON.stringify(
                    data.jitter || { enabled: true, min_percent: -20, max_percent: 30 }
                ));
                this.stages = JSON.parse(JSON.stringify(data.stages || []));
                this.warmup = JSON.parse(JSON.stringify(
                    data.warmup || { enabled: false }
                ));
                console.log(`[GrowthProfile] 프리셋 '${key}' 로드 완료`);
            } catch (error) {
                console.error('[GrowthProfile] 프리셋 로드 실패:', error);
                // 실패 시 기본 매트릭스와 빈 구간으로 초기화
                this.schedule_matrix = this._makeDefaultMatrix();
                this.stages = [];
            }
        },

        // --- 초기화 / 직렬화 메서드 ---

        /** 기존 Module.settings에서 상태 복원 (편집 모드). 빈 값이면 balanced 프리셋 로드 */
        async initFromSettings(settings) {
            if (!settings || Object.keys(settings).length === 0) {
                await this.loadPreset('balanced');
                return;
            }
            // schedule_matrix 복원
            this.schedule_matrix = settings.schedule_matrix
                ? JSON.parse(JSON.stringify(settings.schedule_matrix))
                : this._makeDefaultMatrix();
            // jitter 복원
            this.jitter = settings.jitter
                ? JSON.parse(JSON.stringify(settings.jitter))
                : { enabled: true, min_percent: -20, max_percent: 30 };
            // stages 복원
            this.stages = settings.stages
                ? JSON.parse(JSON.stringify(settings.stages))
                : [];
            // warmup 복원
            this.warmup = settings.warmup
                ? JSON.parse(JSON.stringify(settings.warmup))
                : { enabled: false };
            // warmup 기본 필드 보정
            if (this.warmup.enabled && !this.warmup.warmup_days) {
                this.warmup.warmup_days = 14;
                this.warmup.initial_daily_posts = this.warmup.initial_daily_posts || 1;
                this.warmup.max_daily_posts = this.warmup.max_daily_posts || 3;
                this.warmup.ramp_rate = this.warmup.ramp_rate || 0.5;
            }
            console.log('[GrowthProfile] 기존 설정에서 복원 완료');
        },

        /** 저장 시 호출 - gpModule 상태를 settings JSONB로 직렬화. 비활성 필드는 null */
        toSettings() {
            return {
                schedule_matrix: this.schedule_matrix,
                jitter: this.jitter,
                stages: this.stages.map(s => ({
                    name: s.name,
                    label: s.label,
                    post_count_min: s.post_count_min,
                    post_count_max: s.post_count_max,
                    description: s.description,
                    generate: {
                        enabled: s.generate.enabled,
                        min_inventory: s.generate.enabled ? s.generate.min_inventory : null,
                        interval_mode: s.generate.enabled ? s.generate.interval_mode : null,
                        interval_minutes: s.generate.interval_mode === 'manual'
                            ? s.generate.interval_minutes : null,
                        daily_count: s.generate.interval_mode === 'auto'
                            ? s.generate.daily_count : null,
                    },
                    publish: {
                        enabled: s.publish.enabled,
                        interval_mode: s.publish.enabled ? s.publish.interval_mode : null,
                        interval_minutes: s.publish.interval_mode === 'manual'
                            ? s.publish.interval_minutes : null,
                        daily_count: s.publish.interval_mode === 'auto'
                            ? s.publish.daily_count : null,
                    },
                    republish: {
                        enabled: s.republish.enabled,
                        interval_mode: s.republish.enabled ? s.republish.interval_mode : null,
                        interval_minutes: s.republish.interval_mode === 'manual'
                            ? s.republish.interval_minutes : null,
                        daily_count: s.republish.interval_mode === 'auto'
                            ? s.republish.daily_count : null,
                    },
                })),
                warmup: this.warmup.enabled ? this.warmup : { enabled: false },
            };
        },

        // --- 성장 구간 관리 메서드 ---

        /** 성장 구간 추가. 이전 구간의 max+1을 새 구간의 min으로 설정 */
        addStage() {
            const lastStage = this.stages.length > 0
                ? this.stages[this.stages.length - 1]
                : null;
            let newMin = 0;
            if (lastStage) {
                if (lastStage.post_count_max === null || lastStage.post_count_max === undefined) {
                    // 마지막 구간의 max가 null이면 임의값 할당
                    lastStage.post_count_max = lastStage.post_count_min + 49;
                }
                newMin = lastStage.post_count_max + 1;
            }
            this.stages.push({
                name: `stage_${this.stages.length + 1}`,
                label: `구간 ${this.stages.length + 1}`,
                post_count_min: newMin,
                post_count_max: null,
                description: '',
                generate: { enabled: true, min_inventory: 5, interval_mode: 'auto', interval_minutes: 60, daily_count: 3 },
                publish: { enabled: true, interval_mode: 'auto', interval_minutes: 60, daily_count: 3 },
                republish: { enabled: true, interval_mode: 'auto', interval_minutes: 60, daily_count: 3 },
            });
        },

        /** 성장 구간 삭제 (최소 1개 유지) */
        removeStage(idx) {
            if (this.stages.length <= 1) {
                this.validationError = '최소 1개의 성장 구간이 필요합니다';
                return;
            }
            if (!confirm(`'${this.stages[idx].label}' 구간을 삭제하시겠습니까?`)) {
                return;
            }
            this.stages.splice(idx, 1);
            this.validateContinuity();
        },

        /** post_count_max 변경 시 다음 구간의 post_count_min을 자동 갱신 */
        onMaxChanged(idx) {
            const currentMax = this.stages[idx].post_count_max;
            if (currentMax !== null && currentMax !== undefined && idx < this.stages.length - 1) {
                this.stages[idx + 1].post_count_min = currentMax + 1;
            }
            this.validateContinuity();
        },

        /** 성장 구간 연속성 검증. 중간 구간 불일치 시 자동 보정, 마지막 max는 항상 null */
        validateContinuity() {
            this.validationError = null;

            if (this.stages.length === 0) {
                this.validationError = '최소 1개의 성장 구간이 필요합니다';
                return false;
            }
            if (this.stages[0].post_count_min !== 0) {
                this.validationError = '첫 번째 구간의 시작값은 0이어야 합니다';
                return false;
            }
            // 중간 구간 연속성 보정
            for (let i = 1; i < this.stages.length; i++) {
                const prev = this.stages[i - 1];
                const curr = this.stages[i];
                if (prev.post_count_max !== null && prev.post_count_max !== undefined) {
                    const expectedMin = prev.post_count_max + 1;
                    if (curr.post_count_min !== expectedMin) {
                        curr.post_count_min = expectedMin;
                        console.log(`[GrowthProfile] 구간 ${i} min 자동 보정: ${expectedMin}`);
                    }
                }
            }
            // 마지막 구간 max는 항상 null (무한대)
            const lastStage = this.stages[this.stages.length - 1];
            lastStage.post_count_max = null;

            return true;
        },

        // --- 활성 시간대 조작 메서드 ---

        /** 개별 시간 슬롯 토글 */
        toggleHour(dayIdx, hour) {
            this.schedule_matrix[dayIdx][hour] = !this.schedule_matrix[dayIdx][hour];
        },

        /** 해당 요일의 모든 시간 토글 (하나라도 false면 전체 true, 전부 true면 전체 false) */
        toggleDay(dayIdx) {
            const allActive = this.schedule_matrix[dayIdx].every(Boolean);
            const newVal = !allActive;
            this.schedule_matrix[dayIdx] = this.schedule_matrix[dayIdx].map(() => newVal);
        },

        /** 전체 시간대 활성화 */
        selectAllHours() {
            this.schedule_matrix = Array.from({ length: 7 }, () => Array(24).fill(true));
        },

        /** 전체 시간대 비활성화 */
        clearAllHours() {
            this.schedule_matrix = Array.from({ length: 7 }, () => Array(24).fill(false));
        },

        /** 평일(월~금) 6~21시 활성화, 나머지 비활성화 */
        selectWeekdayHours() {
            this.schedule_matrix = Array.from({ length: 7 }, (_, d) =>
                Array.from({ length: 24 }, (_, h) => d < 5 && h >= 6 && h <= 21)
            );
        },

        /** 주말(토~일) 7~20시 활성화, 나머지 비활성화 */
        selectWeekendHours() {
            this.schedule_matrix = Array.from({ length: 7 }, (_, d) =>
                Array.from({ length: 24 }, (_, h) => d >= 5 && h >= 7 && h <= 20)
            );
        },

        // --- 간격/횟수 계산 헬퍼 ---

        /** 분 간격에서 일일 횟수 계산. 0이면 'N/A' 반환 */
        calcDailyFromMinutes(minutes) {
            if (!minutes || minutes <= 0) return 'N/A';
            const result = Math.floor((this.todayActiveHours * 60) / minutes);
            return result > 0 ? result : 'N/A';
        },

        /** 일일 횟수에서 분 간격 계산. 0이면 'N/A' 반환 */
        calcMinutesFromDaily(count) {
            if (!count || count <= 0) return 'N/A';
            const result = Math.floor((this.todayActiveHours * 60) / count);
            return result > 0 ? result : 'N/A';
        },

        // --- 프리뷰 관련 메서드 ---

        /** 현재 설정으로 블로그별 적용 프리뷰 로드 */
        async loadPreview() {
            this.previewLoading = true;
            this.previewBlogs = [];
            try {
                const flowIdEl = document.querySelector('[data-flow-id]');
                const flowId = flowIdEl ? flowIdEl.dataset.flowId : null;
                const body = {
                    settings: this.toSettings(),
                    flow_id: flowId ? parseInt(flowId, 10) : null
                };
                const response = await fetch('/api/v1/growth-profile/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(body)
                });
                if (!response.ok) {
                    throw new Error('프리뷰 로드 실패');
                }
                const data = await response.json();
                this.previewBlogs = data.blogs || data || [];
                console.log('[GrowthProfile] 프리뷰 로드 완료:', this.previewBlogs.length, '개 블로그');
            } catch (error) {
                console.error('[GrowthProfile] 프리뷰 로드 실패:', error);
                this.previewBlogs = [];
            } finally {
                this.previewLoading = false;
            }
        },

        // --- 검증 메서드 ---

        /** 전체 검증 - 연속성 + 구간 이름 + 활성 모듈 간격 체크 */
        validate() {
            this.validationError = null;

            // 연속성 검증
            if (!this.validateContinuity()) {
                return false;
            }
            // 구간 이름 검증
            for (let i = 0; i < this.stages.length; i++) {
                if (!this.stages[i].label || !this.stages[i].label.trim()) {
                    this.validationError = `구간 ${i + 1}의 이름을 입력해주세요`;
                    return false;
                }
            }
            // 활성 모듈 간격 체크
            for (let i = 0; i < this.stages.length; i++) {
                const s = this.stages[i];
                const modules = ['generate', 'publish', 'republish'];
                for (const mod of modules) {
                    if (!s[mod].enabled) continue;
                    if (s[mod].interval_mode === 'manual' && (!s[mod].interval_minutes || s[mod].interval_minutes < 1)) {
                        this.validationError = `'${s.label}'의 ${mod} 간격을 설정해주세요`;
                        return false;
                    }
                    if (s[mod].interval_mode === 'auto' && (!s[mod].daily_count || s[mod].daily_count < 1)) {
                        this.validationError = `'${s.label}'의 ${mod} 일일 횟수를 설정해주세요`;
                        return false;
                    }
                }
            }
            return true;
        },

        // --- 내부 헬퍼 ---

        /** 기본 schedule_matrix 생성 (평일 6~21시, 주말 7~20시) */
        _makeDefaultMatrix() {
            const matrix = [];
            for (let d = 0; d < 7; d++) {
                const row = [];
                const [start, end] = d < 5 ? [6, 21] : [7, 20];
                for (let h = 0; h < 24; h++) {
                    row.push(h >= start && h <= end);
                }
                matrix.push(row);
            }
            return matrix;
        }
    };
}

// 전역 등록
window.createGrowthProfileState = createGrowthProfileState;
