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
            { key: 'aggressive', name: '공격적 성장', description: '빠른 콘텐츠 축적, 발행 빈도 극대화', stageCount: 3, warmupEnabled: true },
            { key: 'balanced', name: '균형 성장', description: '균형 잡힌 생성/발행/재발행 설정', stageCount: 3, warmupEnabled: true },
            { key: 'conservative', name: '보수적 운영', description: '안정적 운영, 느린 생성', stageCount: 3, warmupEnabled: false }
        ],

        // --- 커스텀 프로파일 ---
        customProfiles: [],
        _nextCustomId: 1,

        // --- 프리셋 상세 정보 캐시 ---
        presetDetails: {},
        presetDetailsLoading: false,

        /** 프리셋 카드에 표시할 데이터 반환 (선택된 프리셋은 실시간 상태 반영) */
        getCardData(key) {
            if (this.selectedPreset === key) {
                return { schedule_matrix: this.schedule_matrix, jitter: this.jitter,
                    stages: this.stages, warmup: this.warmup };
            }
            if (key.startsWith('custom_')) {
                const cp = this.customProfiles.find(c => c.key === key);
                return cp ? cp.data : null;
            }
            return this.presetDetails[key] || null;
        },

        // --- 활성 시간대 ---
        schedule_matrix: null,
        days: ['월', '화', '수', '목', '금', '토', '일'],

        // --- 지터 ---
        jitter: { enabled: true, min_percent: -20, max_percent: 30 },

        // --- 성장 구간 ---
        stages: [],

        // --- 워밍업 ---
        warmup: { enabled: true, warmup_days: 14, initial_daily_posts: 1, max_daily_posts: 3, ramp_rate: 0.5 },

        // --- 검증 ---
        validationError: null,

        /** 전체 활성 시간 수 (주간 합계) */
        get activeHoursCount() {
            if (!this.schedule_matrix) return 0;
            return this.schedule_matrix.flat().filter(Boolean).length;
        },

        /** 오늘 요일 기준 활성 시간 수 */
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
                const daily = Math.min(initial_daily_posts + Math.floor(day * ramp_rate), max_daily_posts);
                const interval = daily > 0 ? Math.floor((activeHours * 60) / daily) : 0;
                sims.push({ day, daily, interval });
            }
            return sims;
        },

        /** 현재 커스텀 프로파일이면 data를 현재 상태로 갱신 */
        _saveCurrentToCustom() {
            if (!this.selectedPreset || !this.selectedPreset.startsWith('custom_')) return;
            const cp = this.customProfiles.find(c => c.key === this.selectedPreset);
            if (!cp) return;
            const clone = (v) => JSON.parse(JSON.stringify(v));
            cp.data = { schedule_matrix: clone(this.schedule_matrix), jitter: clone(this.jitter),
                stages: clone(this.stages), warmup: clone(this.warmup) };
            const preset = this.presets.find(p => p.key === this.selectedPreset);
            if (preset) { preset.stageCount = this.stages.length; preset.warmupEnabled = this.warmup.enabled; }
        },

        /** 커스텀 프로파일 추가 */
        addCustomProfile(name) {
            if (!name || !name.trim()) return;
            const key = 'custom_' + this._nextCustomId++;
            const data = { schedule_matrix: this._makeDefaultMatrix(),
                jitter: { enabled: false, min_percent: -20, max_percent: 30 },
                stages: [], warmup: { enabled: false } };
            this.customProfiles.push({ key, name: name.trim(), data });
            this.presets.push({ key, name: name.trim(), description: '사용자 정의 프로파일',
                stageCount: 0, warmupEnabled: false, isCustom: true });
            this.loadPreset(key);
        },

        /** 커스텀 프로파일 삭제 */
        removeCustomProfile(key) {
            if (!key.startsWith('custom_')) return;
            if (!confirm('이 커스텀 프로파일을 삭제하시겠습니까?')) return;
            this.customProfiles = this.customProfiles.filter(c => c.key !== key);
            this.presets = this.presets.filter(p => p.key !== key);
            if (this.selectedPreset === key) this.loadPreset('balanced');
        },

        /** 프리셋 로드 - API 호출 또는 커스텀 데이터로 상태 반영 */
        async loadPreset(key) {
            this._saveCurrentToCustom();
            this.selectedPreset = key;
            this.validationError = null;
            const clone = (v) => JSON.parse(JSON.stringify(v));
            const defaults = { jitter: { enabled: false, min_percent: -20, max_percent: 30 },
                stages: [], warmup: { enabled: false } };

            // 커스텀 프로파일 로드
            if (key.startsWith('custom_')) {
                const cp = this.customProfiles.find(c => c.key === key);
                if (cp && cp.data) {
                    this.schedule_matrix = clone(cp.data.schedule_matrix || this._makeDefaultMatrix());
                    this.jitter = clone(cp.data.jitter || defaults.jitter);
                    this.stages = clone(cp.data.stages || []);
                    this.warmup = clone(cp.data.warmup || defaults.warmup);
                } else {
                    this.schedule_matrix = this._makeDefaultMatrix();
                    this.jitter = { ...defaults.jitter }; this.stages = []; this.warmup = { ...defaults.warmup };
                }
                return;
            }
            // API 프리셋 로드
            try {
                const resp = await fetch(`/api/v1/growth-profile/presets/${key}`, { credentials: 'include' });
                if (!resp.ok) throw new Error('프리셋 로드 실패');
                const data = await resp.json();
                this.schedule_matrix = clone(data.schedule_matrix || this._makeDefaultMatrix());
                this.jitter = clone(data.jitter || { enabled: true, min_percent: -20, max_percent: 30 });
                this.stages = clone(data.stages || []);
                this.warmup = clone(data.warmup || { enabled: false });
                console.log(`[GrowthProfile] 프리셋 '${key}' 로드 완료`);
            } catch (error) {
                console.error('[GrowthProfile] 프리셋 로드 실패:', error);
                this.schedule_matrix = this._makeDefaultMatrix();
                this.stages = [];
            }
        },

        /** 기존 Module.settings에서 상태 복원 (편집 모드) */
        async initFromSettings(settings) {
            if (!settings || Object.keys(settings).length === 0) {
                await this.loadPreset('balanced');
                return;
            }
            const clone = (v) => JSON.parse(JSON.stringify(v));
            this.schedule_matrix = settings.schedule_matrix ? clone(settings.schedule_matrix) : this._makeDefaultMatrix();
            this.jitter = settings.jitter ? clone(settings.jitter) : { enabled: true, min_percent: -20, max_percent: 30 };
            this.stages = settings.stages ? clone(settings.stages) : [];
            this.warmup = settings.warmup ? clone(settings.warmup) : { enabled: false };
            // warmup 기본 필드 보정
            if (this.warmup.enabled && !this.warmup.warmup_days) {
                Object.assign(this.warmup, { warmup_days: 14,
                    initial_daily_posts: this.warmup.initial_daily_posts || 1,
                    max_daily_posts: this.warmup.max_daily_posts || 3,
                    ramp_rate: this.warmup.ramp_rate || 0.5 });
            }
            // custom_profiles 복원 (selectedPreset보다 먼저 복원해야 커스텀 프리셋 참조 가능)
            if (settings.custom_profiles && Array.isArray(settings.custom_profiles)) {
                this.customProfiles = settings.custom_profiles;
                let maxId = 0;
                for (const cp of this.customProfiles) {
                    const num = parseInt(cp.key.replace('custom_', ''), 10);
                    if (num > maxId) maxId = num;
                    this.presets.push({ key: cp.key, name: cp.name, description: '사용자 정의 프로파일',
                        stageCount: cp.data?.stages?.length || 0,
                        warmupEnabled: cp.data?.warmup?.enabled || false, isCustom: true });
                }
                this._nextCustomId = maxId + 1;
            }
            // 저장된 selectedPreset 복원 (커스텀 프로파일 복원 후 실행)
            if (settings.selectedPreset) {
                this.selectedPreset = settings.selectedPreset;
            }
            console.log('[GrowthProfile] 기존 설정에서 복원 완료');
            this.loadAllPresetDetails();
        },

        /** stage 내 모듈(generate/publish/republish) 직렬화 헬퍼 */
        _serializeModule(s, mod) {
            const base = { enabled: s[mod].enabled,
                ...(mod === 'generate' ? { min_inventory: s[mod].enabled ? s.generate.min_inventory : null } : {}),
                interval_mode: s[mod].enabled ? s[mod].interval_mode : null,
                interval_minutes: s[mod].enabled && s[mod].interval_mode === 'manual' ? s[mod].interval_minutes : null,
                daily_count: s[mod].enabled && s[mod].interval_mode === 'auto' ? s[mod].daily_count : null,
            };
            return base;
        },

        /** 저장 시 호출 - gpModule 상태를 settings JSONB로 직렬화 */
        toSettings() {
            this._saveCurrentToCustom();
            return {
                selectedPreset: this.selectedPreset,
                schedule_matrix: this.schedule_matrix,
                jitter: this.jitter,
                stages: this.stages.map(s => ({
                    name: s.name, label: s.label,
                    post_count_min: s.post_count_min, post_count_max: s.post_count_max,
                    description: s.description,
                    generate: this._serializeModule(s, 'generate'),
                    publish: this._serializeModule(s, 'publish'),
                    republish: this._serializeModule(s, 'republish'),
                })),
                warmup: this.warmup.enabled ? this.warmup : { enabled: false },
                custom_profiles: this.customProfiles.length > 0 ? this.customProfiles : undefined,
            };
        },

        /** 성장 구간 추가 */
        addStage() {
            const last = this.stages.length > 0 ? this.stages[this.stages.length - 1] : null;
            let newMin = 0;
            if (last) {
                if (last.post_count_max === null || last.post_count_max === undefined)
                    last.post_count_max = last.post_count_min + 49;
                newMin = last.post_count_max + 1;
            }
            const defMod = { enabled: true, min_inventory: 5, interval_mode: 'auto', interval_minutes: 60, daily_count: 3 };
            this.stages.push({
                name: `stage_${this.stages.length + 1}`, label: `구간 ${this.stages.length + 1}`,
                post_count_min: newMin, post_count_max: null, description: '',
                generate: { ...defMod }, publish: { ...defMod, min_inventory: undefined }, republish: { ...defMod, min_inventory: undefined },
            });
        },

        /** 성장 구간 삭제 (최소 1개 유지) */
        removeStage(idx) {
            if (this.stages.length <= 1) { this.validationError = '최소 1개의 성장 구간이 필요합니다'; return; }
            if (!confirm(`'${this.stages[idx].label}' 구간을 삭제하시겠습니까?`)) return;
            this.stages.splice(idx, 1);
            this.validateContinuity();
        },

        /** post_count_max 변경 시 다음 구간의 min 자동 갱신 */
        onMaxChanged(idx) {
            const max = this.stages[idx].post_count_max;
            if (max !== null && max !== undefined && idx < this.stages.length - 1)
                this.stages[idx + 1].post_count_min = max + 1;
            this.validateContinuity();
        },

        /** 성장 구간 연속성 검증 */
        validateContinuity() {
            this.validationError = null;
            if (this.stages.length === 0) { this.validationError = '최소 1개의 성장 구간이 필요합니다'; return false; }
            if (this.stages[0].post_count_min !== 0) { this.validationError = '첫 번째 구간의 시작값은 0이어야 합니다'; return false; }
            for (let i = 1; i < this.stages.length; i++) {
                const prev = this.stages[i - 1], curr = this.stages[i];
                if (prev.post_count_max !== null && prev.post_count_max !== undefined) {
                    const expected = prev.post_count_max + 1;
                    if (curr.post_count_min !== expected) { curr.post_count_min = expected; }
                }
            }
            this.stages[this.stages.length - 1].post_count_max = null;
            return true;
        },

        toggleHour(dayIdx, hour) { this.schedule_matrix[dayIdx][hour] = !this.schedule_matrix[dayIdx][hour]; },

        toggleDay(dayIdx) {
            const newVal = !this.schedule_matrix[dayIdx].every(Boolean);
            this.schedule_matrix[dayIdx] = this.schedule_matrix[dayIdx].map(() => newVal);
        },

        selectAllHours() { this.schedule_matrix = Array.from({ length: 7 }, () => Array(24).fill(true)); },
        clearAllHours() { this.schedule_matrix = Array.from({ length: 7 }, () => Array(24).fill(false)); },

        selectWeekdayHours() {
            this.schedule_matrix = Array.from({ length: 7 }, (_, d) =>
                Array.from({ length: 24 }, (_, h) => d < 5 && h >= 6 && h <= 21));
        },

        selectWeekendHours() {
            this.schedule_matrix = Array.from({ length: 7 }, (_, d) =>
                Array.from({ length: 24 }, (_, h) => d >= 5 && h >= 7 && h <= 20));
        },

        /** 분 간격에서 일일 횟수 계산 */
        calcDailyFromMinutes(minutes) {
            if (!minutes || minutes <= 0) return 'N/A';
            const r = Math.floor((this.todayActiveHours * 60) / minutes);
            return r > 0 ? r : 'N/A';
        },

        /** 일일 횟수에서 분 간격 계산 */
        calcMinutesFromDaily(count) {
            if (!count || count <= 0) return 'N/A';
            const r = Math.floor((this.todayActiveHours * 60) / count);
            return r > 0 ? r : 'N/A';
        },

        /** 전체 검증 - 연속성 + 구간 이름 + 활성 모듈 간격 체크 */
        validate() {
            this.validationError = null;
            if (!this.validateContinuity()) return false;
            for (let i = 0; i < this.stages.length; i++) {
                if (!this.stages[i].label || !this.stages[i].label.trim()) {
                    this.validationError = `구간 ${i + 1}의 이름을 입력해주세요`; return false;
                }
            }
            for (let i = 0; i < this.stages.length; i++) {
                const s = this.stages[i];
                for (const mod of ['generate', 'publish', 'republish']) {
                    if (!s[mod].enabled) continue;
                    if (s[mod].interval_mode === 'manual' && (!s[mod].interval_minutes || s[mod].interval_minutes < 1)) {
                        this.validationError = `'${s.label}'의 ${mod} 간격을 설정해주세요`; return false;
                    }
                    if (s[mod].interval_mode === 'auto' && (!s[mod].daily_count || s[mod].daily_count < 1)) {
                        this.validationError = `'${s.label}'의 ${mod} 일일 횟수를 설정해주세요`; return false;
                    }
                }
            }
            return true;
        },

        /** 모든 프리셋의 상세 정보를 API로 일괄 로드 (카드 표시용) */
        async loadAllPresetDetails() {
            if (Object.keys(this.presetDetails).length > 0) return;
            this.presetDetailsLoading = true;
            try {
                const keys = ['aggressive', 'balanced', 'conservative'];
                const results = await Promise.all(
                    keys.map(k => fetch(`/api/v1/growth-profile/presets/${k}`, { credentials: 'include' }).then(r => r.ok ? r.json() : null))
                );
                keys.forEach((k, i) => { if (results[i]) this.presetDetails[k] = results[i]; });
            } catch (error) {
                console.error('[GrowthProfile] 프리셋 상세 정보 로드 실패:', error);
            } finally { this.presetDetailsLoading = false; }
        },

        /** schedule_matrix를 요약 텍스트로 변환 */
        getScheduleSummaryText(matrix) {
            if (!matrix) return '미설정';
            const getRange = (days) => {
                let min = 24, max = -1;
                for (const d of days) for (let h = 0; h < 24; h++)
                    if (matrix[d] && matrix[d][h]) { if (h < min) min = h; if (h > max) max = h; }
                return min <= max ? `${min}~${max}시` : null;
            };
            const parts = [];
            const wd = getRange([0, 1, 2, 3, 4]), we = getRange([5, 6]);
            if (wd) parts.push(`평일 ${wd}`);
            if (we) parts.push(`주말 ${we}`);
            return parts.length > 0 ? parts.join(' / ') : '미설정';
        },

        /** jitter 설정을 요약 텍스트로 변환 */
        getJitterSummaryText(jitter) {
            if (!jitter || !jitter.enabled) return 'OFF';
            return `${jitter.min_percent}% ~ +${jitter.max_percent}%`;
        },

        /** stages를 구간별 요약 배열로 변환 */
        getStagesSummary(stages) {
            if (!stages || stages.length === 0) return [];
            return stages.map(s => {
                const range = (s.post_count_max !== null && s.post_count_max !== undefined)
                    ? `~${s.post_count_max}` : `${s.post_count_min}+`;
                const parts = [];
                for (const [mod, label] of [['generate','생성'],['publish','발행'],['republish','재발행']]) {
                    if (s[mod] && s[mod].enabled) {
                        const cnt = s[mod].interval_mode === 'auto' ? s[mod].daily_count : null;
                        parts.push(`${label}${cnt || ''}`);
                    }
                }
                return { label: s.label || s.name, range, modules: parts.join('/') };
            });
        },

        /** warmup 설정을 요약 텍스트로 변환 */
        getWarmupSummaryText(warmup) {
            if (!warmup || !warmup.enabled) return 'OFF';
            return `${warmup.warmup_days}일, ${warmup.initial_daily_posts}→${warmup.max_daily_posts}회`;
        },

        /** 해당 섹션으로 부드러운 스크롤 이동 */
        scrollToSection(sectionId) {
            const el = document.getElementById(sectionId);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        },

        /** 기본 schedule_matrix 생성 (평일 6~21시, 주말 7~20시) */
        _makeDefaultMatrix() {
            return Array.from({ length: 7 }, (_, d) => {
                const [s, e] = d < 5 ? [6, 21] : [7, 20];
                return Array.from({ length: 24 }, (_, h) => h >= s && h <= e);
            });
        }
    };
}
// 전역 등록
window.createGrowthProfileState = createGrowthProfileState;
