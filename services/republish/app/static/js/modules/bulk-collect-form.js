/**
 * 대량 수집(bulk_collect) 모듈 폼 Alpine.js 상태 및 템플릿 (Phase D).
 *
 * 4섹션 구조:
 *   1. 기본 정보 (모듈명/설명) - list.js의 기본 폼 영역에서 처리
 *   2. 📥 수집 대상 URL (직접 입력 / 수집 모듈 DB 모드)
 *   3. ⚙️ 대량 수집 파라미터 8개
 *   4. ⏰ 수집 스케줄 (schedule_matrix + interval + jitter)
 *
 * form.js의 moduleFormApp 안에서 `this.bcModule = window.createBulkCollectState()`
 * 형태로 사용되며, list.js의 getDefaultFormHTML 안에서
 * `${window.getBulkCollectFormTemplate()}`로 HTML 을 끼워 넣는다.
 *
 * 저장 시 settings JSON 스키마:
 *   {
 *     "url_source_mode": "direct_input" | "from_collect_module",
 *     "input_urls": ["https://...", ...],           // direct_input 모드
 *     "from_collect": { "order_mode": "stored"|"random", "max_urls": 0 },
 *     "bulk_params": { ...8개 },
 *     "schedule": { "schedule_matrix", "interval_minutes", "jitter_*" }
 *   }
 */

/** 기본 schedule_matrix 생성 (24시간 활성, 7일) */
function _bcDefaultMatrix() {
    return Array(7).fill().map(() => Array(24).fill(true));
}

/** Alpine 상태 팩토리 */
function createBulkCollectState() {
    return {
        // --- 1. URL 소스 (URL탭 고정; 직접 입력 모드 제거) ---
        url_source_mode: 'from_collect_module',
        input_urls_text: '',  // (레거시 호환용, 미사용)

        // --- 수집 모듈 DB(URL탭) 옵션 ---
        from_collect: {
            order_mode: 'stored',  // 'stored' | 'random'
            max_urls: 3            // 사이클당 블로그 수 (기본 3)
        },

        // --- 2. 대량 수집 파라미터 (8개) ---
        bulk_params: {
            cycle_max_duration_sec: 300,
            chunk_size_initial: 100,
            adaptive_chunk_enabled: true,
            domain_concurrency: 2,
            parallel_titles: 10,
            lastmod_only_after_first: true,
            pause_on_callback_backlog: true,
            quiet_hours_chunk_boost: false
        },

        // --- 3. 스케줄 ---
        // 스케줄 모드: 'fixed_time'(고정 시간, 권장·기본) | 'interval'(간격+매트릭스)
        schedule_mode: 'fixed_time',
        fixed_times: ['06:00', '18:00'],
        newFixedTime: '',
        schedule_matrix: _bcDefaultMatrix(),
        days: ['월', '화', '수', '목', '금', '토', '일'],
        interval_minutes: 60,
        // 지터: GP 폼과 동일한 ±% 객체 구조
        // (settings.schedule.jitter 로 저장됨)
        schedule_jitter: {
            enabled: true,
            min_percent: -20,
            max_percent: 30
        },

        // --- 검증 ---
        validationError: null,

        // ───────────────────────────────────────────────
        // URL 텍스트 파싱
        // ───────────────────────────────────────────────
        /**
         * textarea 의 원본 텍스트를 URL 배열로 변환.
         * - 줄바꿈으로 split
         * - trim
         * - 빈 줄 / 주석(#로 시작) 제거
         */
        parseUrls() {
            if (!this.input_urls_text) return [];
            return this.input_urls_text
                .split(/\r?\n/)
                .map(s => s.trim())
                .filter(s => s.length > 0 && !s.startsWith('#'));
        },

        /** 파싱된 URL 수 (UI 노출용) */
        get parsedUrlCount() {
            return this.parseUrls().length;
        },

        /**
         * 단일 URL 의 라벨 ("블로그" / "포스트" / "불명") 반환.
         * 사이트맵 추출은 백엔드에서 처리하므로 여기는 시각 표시 용도.
         *
         * 패턴:
         *   - path 없거나 "/" 만 있으면 → 블로그
         *   - path 가 있고 숫자/슬러그 포함이면 → 포스트
         *   - 그 외 / 잘못된 URL → 불명
         */
        urlPreview(url) {
            try {
                const u = new URL(url);
                const path = (u.pathname || '/').replace(/\/+$/g, '');
                if (!path || path === '') return { label: '블로그', cls: 'text-blue-600' };
                // /post/123, /entry/foo-bar 같은 형태는 포스트로 간주
                if (path.split('/').filter(Boolean).length >= 1) {
                    return { label: '포스트', cls: 'text-emerald-600' };
                }
                return { label: '블로그', cls: 'text-blue-600' };
            } catch (e) {
                return { label: '불명', cls: 'text-gray-400' };
            }
        },

        /** 미리보기용: 첫 N개 URL 라벨만 반환 */
        get urlPreviewSamples() {
            const urls = this.parseUrls();
            return urls.slice(0, 5).map(u => ({
                url: u,
                ...this.urlPreview(u)
            }));
        },

        // ───────────────────────────────────────────────
        // 고정 시간(fixed_time) 편집 (collect 폼 패턴 재사용)
        // ───────────────────────────────────────────────
        addFixedTime() {
            if (!this.newFixedTime) return;
            if (this.fixed_times.includes(this.newFixedTime)) {
                this.validationError = '이미 등록된 시간입니다';
                return;
            }
            this.fixed_times.push(this.newFixedTime);
            this.fixed_times.sort();
            this.newFixedTime = '';
        },

        removeFixedTime(time) {
            const idx = this.fixed_times.indexOf(time);
            if (idx > -1) this.fixed_times.splice(idx, 1);
        },

        // ───────────────────────────────────────────────
        // schedule_matrix 토글 (GP 폼 패턴 재사용)
        // ───────────────────────────────────────────────
        toggleHour(dayIdx, hourIdx) {
            if (!this.schedule_matrix[dayIdx]) {
                this.schedule_matrix[dayIdx] = Array(24).fill(false);
            }
            this.schedule_matrix[dayIdx][hourIdx] =
                !this.schedule_matrix[dayIdx][hourIdx];
        },

        toggleDay(dayIdx) {
            if (!this.schedule_matrix[dayIdx]) {
                this.schedule_matrix[dayIdx] = Array(24).fill(false);
            }
            const allActive = this.schedule_matrix[dayIdx].every(h => h);
            this.schedule_matrix[dayIdx] =
                this.schedule_matrix[dayIdx].map(() => !allActive);
        },

        selectAllHours() {
            this.schedule_matrix = Array(7).fill().map(() => Array(24).fill(true));
        },

        clearAllHours() {
            this.schedule_matrix = Array(7).fill().map(() => Array(24).fill(false));
        },

        selectWeekdayHours() {
            // 평일(월~금) 6~21시 활성
            this.schedule_matrix = Array(7).fill().map((_, d) =>
                Array(24).fill().map((_, h) => d < 5 && h >= 6 && h <= 21)
            );
        },

        get activeHoursCount() {
            if (!this.schedule_matrix) return 0;
            return this.schedule_matrix.flat().filter(Boolean).length;
        },

        get todayActiveHours() {
            if (!this.schedule_matrix) return 0;
            const dayIdx = (new Date().getDay() + 6) % 7;
            return this.schedule_matrix[dayIdx].filter(Boolean).length;
        },

        // ───────────────────────────────────────────────
        // 편집 모드 초기화 / 저장 직렬화
        // ───────────────────────────────────────────────
        /**
         * 기존 Module.settings → 현재 상태로 매핑.
         * (수정 모드 진입 시 form.js init에서 호출)
         */
        initFromSettings(settings) {
            if (!settings || typeof settings !== 'object') return;

            if (settings.url_source_mode) {
                this.url_source_mode = settings.url_source_mode;
            }
            if (Array.isArray(settings.input_urls)) {
                this.input_urls_text = settings.input_urls.join('\n');
            }
            if (settings.from_collect) {
                this.from_collect = {
                    order_mode: settings.from_collect.order_mode || 'stored',
                    max_urls: settings.from_collect.max_urls ?? 0
                };
            }
            if (settings.bulk_params) {
                this.bulk_params = { ...this.bulk_params, ...settings.bulk_params };
            }
            const sch = settings.schedule || {};
            // 스케줄 모드/고정시간 (없으면 기본 fixed_time + 기본 시각)
            if (sch.schedule_mode === 'interval' || sch.schedule_mode === 'fixed_time') {
                this.schedule_mode = sch.schedule_mode;
            }
            if (Array.isArray(sch.fixed_times) && sch.fixed_times.length > 0) {
                this.fixed_times = [...sch.fixed_times];
            }
            if (Array.isArray(sch.schedule_matrix)) {
                this.schedule_matrix = JSON.parse(JSON.stringify(sch.schedule_matrix));
            }
            if (typeof sch.interval_minutes === 'number') {
                this.interval_minutes = sch.interval_minutes;
            }

            // 지터 로드 — 신규(객체) 우선, 없으면 레거시(평탄 키, 양수 %)에서 변환
            //   레거시: jitter_enabled / jitter_min_percent(80) / jitter_max_percent(120)
            //   신규: schedule.jitter.{enabled, min_percent(-20), max_percent(30)}
            // 변환 규칙: 양수 - 100 = ±%   (예: 80 → -20, 120 → +20, 130 → +30)
            if (sch.jitter && typeof sch.jitter === 'object') {
                // 신규 객체 형식
                this.schedule_jitter = {
                    enabled: sch.jitter.enabled ?? this.schedule_jitter.enabled,
                    min_percent: typeof sch.jitter.min_percent === 'number'
                        ? sch.jitter.min_percent
                        : this.schedule_jitter.min_percent,
                    max_percent: typeof sch.jitter.max_percent === 'number'
                        ? sch.jitter.max_percent
                        : this.schedule_jitter.max_percent
                };
            } else if (sch.jitter_enabled !== undefined ||
                       sch.jitter_min_percent !== undefined ||
                       sch.jitter_max_percent !== undefined) {
                // 레거시 평탄 키 — 양수 → ±% 변환
                this.schedule_jitter = {
                    enabled: sch.jitter_enabled ?? this.schedule_jitter.enabled,
                    min_percent: typeof sch.jitter_min_percent === 'number'
                        ? (sch.jitter_min_percent - 100)
                        : this.schedule_jitter.min_percent,
                    max_percent: typeof sch.jitter_max_percent === 'number'
                        ? (sch.jitter_max_percent - 100)
                        : this.schedule_jitter.max_percent
                };
            }
        },

        /**
         * 현재 상태 → settings JSONB 객체 직렬화.
         * (form.js prepareRequestData 에서 호출)
         */
        toSettings() {
            const urls = this.parseUrls();
            return {
                url_source_mode: this.url_source_mode,
                input_urls: this.url_source_mode === 'direct_input' ? urls : [],
                from_collect: {
                    order_mode: this.from_collect.order_mode,
                    max_urls: Number(this.from_collect.max_urls) || 0
                },
                bulk_params: {
                    cycle_max_duration_sec:
                        Number(this.bulk_params.cycle_max_duration_sec) || 300,
                    chunk_size_initial:
                        Number(this.bulk_params.chunk_size_initial) || 100,
                    adaptive_chunk_enabled: !!this.bulk_params.adaptive_chunk_enabled,
                    domain_concurrency:
                        Number(this.bulk_params.domain_concurrency) || 2,
                    parallel_titles:
                        Number(this.bulk_params.parallel_titles) || 10,
                    lastmod_only_after_first:
                        !!this.bulk_params.lastmod_only_after_first,
                    pause_on_callback_backlog:
                        !!this.bulk_params.pause_on_callback_backlog,
                    quiet_hours_chunk_boost:
                        !!this.bulk_params.quiet_hours_chunk_boost
                },
                schedule: {
                    schedule_mode: this.schedule_mode,
                    fixed_times: [...this.fixed_times],
                    schedule_matrix: JSON.parse(JSON.stringify(this.schedule_matrix)),
                    interval_minutes: Number(this.interval_minutes) || 60,
                    // 지터를 GP 폼과 동일한 객체 구조로 저장
                    // (백엔드는 신규 객체와 레거시 평탄 키 양쪽 모두 지원해야 함)
                    jitter: {
                        enabled: !!this.schedule_jitter.enabled,
                        min_percent: Number(this.schedule_jitter.min_percent) || -20,
                        max_percent: Number(this.schedule_jitter.max_percent) || 30
                    }
                }
            };
        },

        // ───────────────────────────────────────────────
        // 검증
        // ───────────────────────────────────────────────
        /** URL 소스 검증 (URL탭 고정) */
        _validateUrlSource() {
            // 직접 입력 모드 제거: URL탭(from_collect_module)으로 고정
            this.url_source_mode = 'from_collect_module';
            if (Number(this.from_collect.max_urls) < 1) {
                this.validationError = '사이클당 블로그 수는 1 이상이어야 합니다.';
                return false;
            }
            return true;
        },

        /** 파라미터 범위 검증 (validate 헬퍼) */
        _validateBulkParams() {
            const bp = this.bulk_params;
            const checks = [
                [bp.cycle_max_duration_sec, 30, 3600, '1사이클 최대 시간은 30~3600초 범위여야 합니다.'],
                [bp.chunk_size_initial, 1, 10000, '시작 청크 크기는 1~10000 범위여야 합니다.'],
                [bp.domain_concurrency, 1, 20, '도메인 동시 접속 수는 1~20 범위여야 합니다.'],
                [bp.parallel_titles, 1, 100, '전체 동시 요청 수는 1~100 범위여야 합니다.']
            ];
            for (const [val, min, max, msg] of checks) {
                if (val < min || val > max) {
                    this.validationError = msg;
                    return false;
                }
            }
            return true;
        },

        /** 스케줄 검증 (validate 헬퍼) */
        _validateSchedule() {
            if (this.activeHoursCount === 0) {
                this.validationError = '최소 1시간 이상의 활성 시간대를 설정해주세요.';
                return false;
            }
            if (this.interval_minutes < 1) {
                this.validationError = '실행 간격은 1분 이상이어야 합니다.';
                return false;
            }
            if (this.schedule_jitter.enabled
                && this.schedule_jitter.min_percent > this.schedule_jitter.max_percent) {
                this.validationError = '지터 최소값은 최대값보다 작아야 합니다.';
                return false;
            }
            return true;
        },

        /**
         * 폼 검증. 실패 시 validationError 에 메시지 저장.
         * @returns {boolean} 통과 여부
         */
        validate() {
            this.validationError = null;
            return this._validateUrlSource()
                && this._validateBulkParams()
                && this._validateSchedule();
        }
    };
}

// 전역 노출
window.createBulkCollectState = createBulkCollectState;
