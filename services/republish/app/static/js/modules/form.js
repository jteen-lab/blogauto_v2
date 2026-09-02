/**
 * 모듈 폼 JavaScript
 * Alpine.js 기반 폼 상태 관리 및 검증
 */

function moduleFormApp(module = null, moduleType = null) {
    // 모듈 데이터 초기화
    const initialModule = module || {};
    const initialType = moduleType || { code: null, name: '' };

    // 프롬프트 모듈 초기 상태 (전역 함수에서 가져옴)
    const promptModuleState = window.createPromptModuleState
        ? window.createPromptModuleState()
        : {};

    // 양방향 연동 상태 머지
    if (window.createPromptModuleLinkingState) {
        promptModuleState.linking = window.createPromptModuleLinkingState();
    }

    return {
        // 폼 상태
        loading: false,
        isEdit: !!initialModule?.id,
        module: initialModule,
        moduleType: initialType,

        // 프롬프트 모듈 상태
        promptModule: promptModuleState,

        // 파이프라인 테스트 상태
        promptTest: window.createPromptTestState
            ? window.createPromptTestState()
            : {},

        // Growth Profile 모듈 상태
        gpModule: window.createGrowthProfileState
            ? window.createGrowthProfileState()
            : {},

        // 대량 수집(bulk_collect) 모듈 상태 (Phase D)
        bcModule: window.createBulkCollectState
            ? window.createBulkCollectState()
            : {},

        // API 상태 (수집 모듈용)
        apiStatus: {
            naver_ads: false,
            naver_datalab: false,
            google_trends: true,  // 구글 트렌드는 API 키 불필요
            google_planner: false,
            naver_news: false,    // 네이버 API 사용 (client_id, client_secret)
            google_news: true,    // 구글 뉴스 RSS는 API 키 불필요
            naver_webdoc: false   // 네이버 웹문서 (client_id, client_secret)
        },
        apiStatusLoading: false,

        // 문의폼(contact_form) 모듈: 템플릿 목록 + 디자인 프리셋 목록
        contactFormTemplates: [],
        contactFormDesigns: [],
        // 애드센스 필수구성: 필수페이지 문체 프리셋 목록
        requiredPagePresets: [],
        _pagesPresetPrev: 'standard',

        // 키워드 모듈 테스트 패널 상태 (모듈 안에서 바로 결과 확인)
        kwTest: { busy: false, error: '', result: null, models: [], elapsed: 0 },

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
            auto_daily_count: initialModule?.auto_daily_count || 5,
            // 수집 모듈 필드들
            collect_schedule_mode: initialModule?.settings?.schedule_mode || 'fixed_time',
            collect_fixed_times: initialModule?.settings?.fixed_times || ['06:00', '18:00'],
            collect_interval_hours: initialModule?.settings?.interval_hours || 6,
            collect_type: initialModule?.settings?.collect_type || 'both',
            // 문의폼(contact_form) 모듈: 선택 템플릿 코드 + 디자인 코드
            contact_template_code: initialModule?.settings?.template_code || 'basic',
            contact_design_code: initialModule?.settings?.design_code || 'default',
            // 애드센스 필수구성: 필수페이지 생성 여부 + 문체 프리셋 + 페이지별 편집본
            generate_pages: initialModule?.settings?.generate_pages ?? true,
            pages_preset_code: initialModule?.settings?.pages_preset_code || 'standard',
            pages_body: { privacy: '', terms: '', about: '', contact: '' },
            _pages_overrides_init: initialModule?.settings?.pages_overrides || {},
            // 키워드 수집 소스 (기본값 False - 사용자가 명시적으로 선택)
            source_google_trends: initialModule?.settings?.source_google_trends ?? false,
            source_naver_datalab: initialModule?.settings?.source_naver_datalab ?? false,
            source_naver_ads: initialModule?.settings?.source_naver_ads ?? false,
            source_google_planner: initialModule?.settings?.source_google_planner ?? false,
            // 제목 수집 소스 (기본값 False - 사용자가 명시적으로 선택)
            source_naver_news: initialModule?.settings?.source_naver_news ?? false,
            source_google_news: initialModule?.settings?.source_google_news ?? false,
            source_naver_webdoc: initialModule?.settings?.source_naver_webdoc ?? false,
            // 추가 옵션
            enable_related_search: initialModule?.settings?.enable_related_search ?? true,
            enable_title_extraction: initialModule?.settings?.enable_title_extraction ?? false,
            // 키워드 추출 옵션
            enable_keyword_extraction: initialModule?.settings?.enable_keyword_extraction ?? false,
            keyword_extraction_method: initialModule?.settings?.keyword_extraction_method || 'all',
            keyword_extraction_title_limit: initialModule?.settings?.keyword_extraction_title_limit || 100,
            keyword_extraction_limit: initialModule?.settings?.keyword_extraction_limit || 50,
            // 수집 유형 선택 (일반/대량)
            enable_normal_collect: initialModule?.settings?.enable_normal_collect ?? true,
            // 키워드 모듈 설정. 화면은 문자열로 다루고 저장할 때 배열로 바꾼다
            // (사용자가 쉼표로 입력하는 편이 자연스럽다).
            keyword: {
                seeds_text: (initialModule?.settings?.keyword?.seeds || []).join(', '),
                modifiers_text: (initialModule?.settings?.keyword?.modifiers
                    || ['방법', '추천', '후기', '비교', '초보']).join(', '),
                use_blog_categories: initialModule?.settings?.keyword?.use_blog_categories ?? true,
                // 수집 소스 — 체크박스별 상태로 펼쳐 두고 저장할 때 배열로 접는다
                src_naver_suggest: (initialModule?.settings?.keyword?.sources || []).includes('naver_suggest'),
                src_google_suggest: (initialModule?.settings?.keyword?.sources || []).includes('google_suggest'),
                src_gsc: (initialModule?.settings?.keyword?.sources || []).includes('gsc'),
                src_google_planner: (initialModule?.settings?.keyword?.sources || []).includes('google_planner'),
                src_google_trends: (initialModule?.settings?.keyword?.sources || []).includes('google_trends'),
                enrich_limit: initialModule?.settings?.keyword?.enrich_limit ?? 100,
                recurse_adopted: initialModule?.settings?.keyword?.recurse_adopted ?? true,
                min_volume: initialModule?.settings?.keyword?.min_volume ?? 100,
                max_volume: initialModule?.settings?.keyword?.max_volume ?? 100000,
                pub_window_days: initialModule?.settings?.keyword?.pub_window_days ?? 30,
                min_saturation: initialModule?.settings?.keyword?.min_saturation ?? 0.2,
                seed_limit: initialModule?.settings?.keyword?.seed_limit ?? 10,
                measure_limit: initialModule?.settings?.keyword?.measure_limit ?? 50,
                make_titles: initialModule?.settings?.keyword?.make_titles ?? true,
                dry_run: initialModule?.settings?.keyword?.dry_run ?? true,
                ai_provider: initialModule?.settings?.keyword?.ai_provider || '',
                ai_model: initialModule?.settings?.keyword?.ai_model || '',
                titles_per_keyword: initialModule?.settings?.keyword?.titles_per_keyword ?? 3,
                cluster_enabled: initialModule?.settings?.keyword?.cluster_enabled ?? true,
                cluster_threshold: initialModule?.settings?.keyword?.cluster_threshold ?? 0.34,
                cluster_min_size: initialModule?.settings?.keyword?.cluster_min_size ?? 3,
                cluster_max_size: initialModule?.settings?.keyword?.cluster_max_size ?? 12,
                titles_per_cluster: initialModule?.settings?.keyword?.titles_per_cluster ?? 0,
                min_inventory: initialModule?.settings?.keyword?.min_inventory ?? 30,
                interval_minutes: initialModule?.settings?.schedule?.interval_minutes ?? 360,
            },

            // DEPRECATED (Phase E): 기존 collect 모듈 호환용 — 신규 모듈은 bulk_collect 타입 사용
            enable_bulk_collect: initialModule?.settings?.enable_bulk_collect ?? false,
            // 일반 수집 수량 설정 (키워드/제목 각각)
            keyword_collect_limit: initialModule?.settings?.keyword_collect_limit || 100,
            title_collect_limit: initialModule?.settings?.title_collect_limit || 100,
            // 대량 수집 설정
            // DEPRECATED (Phase E): 기존 collect 모듈 호환용 — 신규 모듈은 bulk_collect 타입 사용
            bulk_collect_delay: initialModule?.settings?.bulk_collect_delay || 0.5,
            bulk_urls_per_cycle: initialModule?.settings?.bulk_urls_per_cycle || 3,
            // 데이터 모듈 필드들
            // 실행 방식 (상호 배타적: collection_link 또는 schedule)
            // 하위 호환: 기존 collection_link.enabled가 true면 collection_link, schedule.enabled가 true면 schedule
            execution_mode: (() => {
                const s = initialModule?.settings;
                if (s?.execution_mode) return s.execution_mode;
                if (s?.schedule?.enabled) return 'schedule';
                if (s?.collection_link?.enabled !== false) return 'collection_link';
                return 'collection_link';
            })(),
            // 수집 모듈 연동 옵션
            collection_link_delay: initialModule?.settings?.collection_link?.delay_seconds ?? 30,
            // 데이터 이동 스케줄 옵션
            data_schedule_mode: initialModule?.settings?.schedule?.mode || 'fixed_time',
            data_fixed_times: initialModule?.settings?.schedule?.fixed_times || ['06:00', '18:00'],
            data_interval_hours: initialModule?.settings?.schedule?.interval_hours || 6,
            // 실행 조건
            max_titles_per_run: (() => {
                const val = initialModule?.settings?.execution?.max_titles_per_run;
                return (val === -1 || val === null || val === undefined) ? 100 : val;
            })(),
            max_titles_unlimited: (() => {
                const exec = initialModule?.settings?.execution;
                return exec?.max_titles_unlimited === true || exec?.max_titles_per_run === -1;
            })(),
            min_titles_required: initialModule?.settings?.execution?.min_titles_required ?? 1,
            // 필터 및 중복 처리
            duplicate_handling: initialModule?.settings?.filter?.duplicate_handling || 'skip',
            category_filter: initialModule?.settings?.filter?.categories?.join(', ') || '',
            // 그룹화 설정
            auto_group: initialModule?.settings?.auto_group ?? true,
            similarity_threshold: initialModule?.settings?.similarity_threshold ?? 75,
            // 생성 모듈 필드들 - 내부링크 설정
            il_enabled: initialModule?.settings?.internal_links?.enabled ?? false,
            il_intro_count: initialModule?.settings?.internal_links?.intro_count ?? 3,
            il_intro_link_type: initialModule?.settings?.internal_links?.intro_link_type || 'button',
            il_conclusion_count: initialModule?.settings?.internal_links?.conclusion_count ?? 3,
            il_conclusion_list_style: initialModule?.settings?.internal_links?.conclusion_list_style || 'dash',
            il_similarity_threshold: initialModule?.settings?.internal_links?.similarity_threshold ?? 75,
            // 생성 모듈 필드들 - 텍스트 치환 설정
            text_replace_enabled: initialModule?.settings?.substitution?.text_replace_enabled ?? false
        },

        // 수집 시간 입력용
        newFixedTime: '',
        // 데이터 이동 시간 입력용
        newDataFixedTime: '',

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

            // 수집 모듈인 경우 API 상태 로드
            // moduleType.code 또는 formData.type_code 둘 다 체크
            const typeCode = this.formData.type_code || this.moduleType?.code;
            console.log('typeCode 확인:', typeCode, 'formData.type_code:', this.formData.type_code, 'moduleType:', this.moduleType);
            if (typeCode === 'keyword') {
                // 제목 생성 AI 선택지를 채운다
                this.loadKeywordModels();
            }
            if (typeCode === 'contact_form') {
                this.loadContactFormTemplates();
                this.loadContactFormDesigns();
                this.loadRequiredPagePresets();
            }
            if (typeCode === 'collect') {
                console.log('수집 모듈 감지 - API 상태 로드 시작');
                this.loadApiStatus();

                // 수집 유형 변경 시 키워드 추출 옵션 자동 리셋
                this.$watch('formData.collect_type', (newVal) => {
                    if (newVal === 'keyword') {
                        // 키워드만 선택 시 키워드 추출 비활성화 (제목이 없으므로)
                        this.formData.enable_keyword_extraction = false;
                        console.log('[collect_type] 키워드만 선택 - 키워드 추출 옵션 비활성화');
                    }
                });
            }

            // Growth Profile 초기화
            if (typeCode === 'growth_profile') {
                if (this.isEdit && this.module?.settings) {
                    // 편집 모드: 기존 설정에서 복원
                    if (this.gpModule.initFromSettings) {
                        this.gpModule.initFromSettings(this.module.settings);
                    }
                } else if (!this.isEdit) {
                    // 생성 모드: 기본 프리셋(balanced) 자동 로드
                    if (this.gpModule.loadPreset) {
                        this.gpModule.loadPreset('balanced');
                    }
                }
            }

            // 대량 수집(bulk_collect) 초기화 (Phase D)
            if (typeCode === 'bulk_collect') {
                if (this.isEdit && this.module?.settings && this.bcModule?.initFromSettings) {
                    // 편집 모드: 기존 settings 에서 복원
                    this.bcModule.initFromSettings(this.module.settings);
                }
                // 생성 모드는 createBulkCollectState() 의 기본값 사용
            }

            // 프롬프트 모듈인 경우 초기화
            if (typeCode === 'prompt') {
                console.log('프롬프트 모듈 감지 - 카테고리 로드 시작');
                this.loadCategories();
                // 애드센스 승인 전용 프리셋 목록(빌더 목록에는 없다)
                this.loadApprovalPresets();
                // used-blog-categories 는 아래 경로에서 자동 호출되므로
                // 여기서는 fire-and-forget 호출을 하지 않는다 (중복 방지):
                //   - 편집 모드: initPromptModuleFromData → initPromptModuleLinkingFromData
                //   - 신규 모드: onCategoryChange / _loadBlogsForBlogMode 등 사용자 액션
                // 편집 모드일 경우 기존 데이터 로드
                if (this.isEdit) {
                    this.initPromptModuleFromData();
                }
            }

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
            if (this.formData.type_code === 'collect' || this.formData.type_code === 'data' || this.formData.type_code === 'generate') {
                // 데이터 모듈: module.settings.schedule.schedule_matrix에서 먼저 로드 (우선순위 높음)
                // ★ this.module.settings를 사용해야 함 (this.formData.settings가 아님)
                const moduleSettings = this.module?.settings || {};
                if (this.formData.type_code === 'data' && this.isEdit && moduleSettings?.schedule?.schedule_matrix) {
                    this.schedule = JSON.parse(JSON.stringify(moduleSettings.schedule.schedule_matrix));
                    console.log('[initializeSchedule] 데이터 모듈 schedule_matrix 로드됨:', this.schedule?.length, 'x', this.schedule?.[0]?.length);
                } else if (this.formData.type_code === 'generate' && this.isEdit && this.module?.schedule_matrix) {
                    this.schedule = JSON.parse(JSON.stringify(this.module.schedule_matrix));
                    console.log('[initializeSchedule] 생성 모듈 schedule_matrix 로드됨');
                } else if (this.isEdit && this.module?.schedule_matrix) {
                    // 수집 모듈: 루트 레벨 schedule_matrix에서 로드
                    this.schedule = JSON.parse(JSON.stringify(this.module.schedule_matrix));
                } else {
                    // 기본 스케줄 설정
                    if (this.formData.type_code === 'collect' || this.formData.type_code === 'data') {
                        // 수집/데이터 모듈: 기본 24시간 활성
                        this.schedule = Array(7).fill().map(() => Array(24).fill(true));
                    } else if (this.formData.type_code === 'generate') {
                        // 생성 모듈: 기본 평일 9-21시
                        this.schedule = Array(7).fill().map((_, dayIdx) =>
                            Array(24).fill().map((_, hour) =>
                                dayIdx < 5 && hour >= 9 && hour <= 21
                            )
                        );
                    } else {
                        // 기본: 평일 9-21시
                        this.schedule = Array(7).fill().map((_, dayIdx) =>
                            Array(24).fill().map((_, hour) =>
                                dayIdx < 5 && hour >= 9 && hour <= 21
                            )
                        );
                    }
                }
                this.updateActiveHoursCount();
            } else {
                this.schedule = Array(7).fill().map(() => Array(24).fill(false));
            }
        },

        // 설정 JSON 초기화
        initializeSettings() {
            try {
                const settings = this.formData.settings || {};
                this.settingsJson = JSON.stringify(settings, null, 2);
                if (this.settingsJson === '{}' && !this.isEdit) {
                    this.settingsJson = '';
                }
            } catch (e) {
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
                // in-flight used-blog-categories 가 있으면 먼저 끝나길 기다린다.
                // (느린 used-blog-categories 와 submitForm 이 동시에 동일 DB
                //  connection pool 을 다투면 응답이 빈 본문으로 끊겨
                //  "Unexpected end of JSON input" SyntaxError 발생 회귀 방지)
                const inflight =
                    this.promptModule?.linking?._usedMappingsInflight;
                if (inflight) {
                    try { await inflight; } catch (_) { /* 매핑 로드 실패는 저장 차단 사유가 아님 */ }
                }

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

                // 서버 응답 본문이 비어있거나 JSON 이 아닐 수 있어 안전 파싱
                // (다른 long-running 요청과 충돌해 connection 이 빈 응답으로
                // 끊기면 response.json() 이 "Unexpected end of JSON input"
                // SyntaxError 를 던지던 회귀 방지)
                const rawText = await response.text();
                let result = {};
                if (rawText) {
                    try {
                        result = JSON.parse(rawText);
                    } catch (parseErr) {
                        console.warn('[submitForm] JSON 파싱 실패:', parseErr);
                        result = {
                            detail:
                                `서버 응답을 해석할 수 없습니다 ` +
                                `(HTTP ${response.status}). ` +
                                `잠시 후 다시 시도해주세요.`,
                        };
                    }
                }

                if (!response.ok) {
                    throw new Error(result.detail || '요청 처리 중 오류가 발생했습니다');
                }

                if (!rawText) {
                    // 200 OK 인데 본문 빈 경우: 명확한 에러 대신 재시도 안내
                    throw new Error(
                        '서버 응답이 비어있습니다. 잠시 후 다시 시도해주세요.'
                    );
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

            // 수집 모듈 검증
            if (this.formData.type_code === 'collect') {
                // 필수 API 검증 (네이버 광고 API 필수)
                if (!this.apiStatus.naver_ads) {
                    this.showError('수집 모듈 저장을 위해 네이버 광고 API가 필요합니다.\n설정 메뉴에서 API 키를 등록해주세요.');
                    return false;
                }

                // 스케줄 모드별 검증
                if (this.formData.collect_schedule_mode === 'fixed_time') {
                    if (!this.formData.collect_fixed_times || this.formData.collect_fixed_times.length === 0) {
                        this.showError('최소 1개 이상의 수집 시간을 설정해주세요');
                        return false;
                    }
                } else if (this.formData.collect_schedule_mode === 'interval') {
                    if (!this.formData.collect_interval_hours || this.formData.collect_interval_hours < 1) {
                        this.showError('수집 간격은 1시간 이상이어야 합니다');
                        return false;
                    }
                }

                // 수집 유형 검증 (일반 수집 활성화 필수)
                // Phase E: 대량 수집은 별도 모듈로 분리되어 일반 수집만 필수 체크
                if (!this.formData.enable_normal_collect) {
                    this.showError('일반 수집을 활성화해 주세요');
                    return false;
                }

                // 일반 수집 수량 설정 검증 (일반 수집 선택 시에만)
                if (this.formData.enable_normal_collect) {
                    if (!this.formData.keyword_collect_limit || this.formData.keyword_collect_limit < 10) {
                        this.showError('키워드 수집 수량은 10개 이상이어야 합니다');
                        return false;
                    }
                    if (this.formData.keyword_collect_limit > 1000) {
                        this.showError('키워드 수집 수량은 1000개를 초과할 수 없습니다');
                        return false;
                    }
                    if (!this.formData.title_collect_limit || this.formData.title_collect_limit < 10) {
                        this.showError('제목 수집 수량은 10개 이상이어야 합니다');
                        return false;
                    }
                    if (this.formData.title_collect_limit > 1000) {
                        this.showError('제목 수집 수량은 1000개를 초과할 수 없습니다');
                        return false;
                    }
                }

                // 대량 수집 딜레이 검증 (대량 수집 선택 시에만)
                if (this.formData.enable_bulk_collect) {
                    if (!this.formData.bulk_collect_delay || this.formData.bulk_collect_delay < 0.1) {
                        this.showError('대량 수집 사이트 간 딜레이는 최소 0.1초 이상이어야 합니다');
                        return false;
                    }
                }

                if (this.activeHoursCount === 0) {
                    this.showError('최소 1시간 이상의 활성 스케줄을 설정해주세요');
                    return false;
                }
            }

            // 데이터 모듈 검증
            if (this.formData.type_code === 'data') {
                // 실행 방식 선택 검증
                if (!this.formData.execution_mode) {
                    this.showError('실행 방식을 선택해주세요');
                    return false;
                }

                // 실행 조건 검증 (전체 선택이 아닌 경우에만)
                if (!this.formData.max_titles_unlimited) {
                    if (!this.formData.max_titles_per_run || this.formData.max_titles_per_run < 1) {
                        this.showError('최대 이동 개수는 1개 이상이어야 합니다');
                        return false;
                    }
                    if (this.formData.max_titles_per_run > 10000) {
                        this.showError('최대 이동 개수는 10000개를 초과할 수 없습니다');
                        return false;
                    }
                }
                if (!this.formData.min_titles_required || this.formData.min_titles_required < 1) {
                    this.showError('최소 제목 수 조건은 1개 이상이어야 합니다');
                    return false;
                }

                // 수집 모듈 연동 모드 검증
                if (this.formData.execution_mode === 'collection_link') {
                    if (this.formData.collection_link_delay < 0 || this.formData.collection_link_delay > 300) {
                        this.showError('대기 시간은 0~300초 범위여야 합니다');
                        return false;
                    }
                }

                // 스케줄 모드 검증
                if (this.formData.execution_mode === 'schedule') {
                    if (this.formData.data_schedule_mode === 'fixed_time') {
                        if (!this.formData.data_fixed_times || this.formData.data_fixed_times.length === 0) {
                            this.showError('최소 1개 이상의 데이터 이동 시간을 설정해주세요');
                            return false;
                        }
                    } else if (this.formData.data_schedule_mode === 'interval') {
                        if (!this.formData.data_interval_hours || this.formData.data_interval_hours < 1) {
                            this.showError('데이터 이동 간격은 1시간 이상이어야 합니다');
                            return false;
                        }
                    }
                }

                // 유사도 임계값 검증 (자동 그룹화 활성화 시)
                if (this.formData.auto_group) {
                    if (this.formData.similarity_threshold < 50 || this.formData.similarity_threshold > 100) {
                        this.showError('유사도 임계값은 50~100% 범위여야 합니다');
                        return false;
                    }
                }
            }

            // 생성 모듈 검증
            if (this.formData.type_code === 'generate') {
                // 내부링크 검증
                if (this.formData.il_enabled) {
                    if (this.formData.il_intro_count < 1 || this.formData.il_intro_count > 5) {
                        this.showError('서론 뒤 링크 수는 1~5 범위여야 합니다');
                        return false;
                    }
                    if (!['button', 'normal'].includes(this.formData.il_intro_link_type)) {
                        this.showError('서론 링크 타입을 선택해주세요');
                        return false;
                    }
                    if (this.formData.il_conclusion_count < 1 || this.formData.il_conclusion_count > 10) {
                        this.showError('결론 뒤 링크 수는 1~10 범위여야 합니다');
                        return false;
                    }
                    if (!['number', 'dash', 'none'].includes(this.formData.il_conclusion_list_style)) {
                        this.showError('결론 리스트 스타일을 선택해주세요');
                        return false;
                    }
                    if (this.formData.il_similarity_threshold < 50 || this.formData.il_similarity_threshold > 100) {
                        this.showError('유사도 임계값은 50~100% 범위여야 합니다');
                        return false;
                    }
                }
            }

            // 프롬프트 모듈 검증
            if (this.formData.type_code === 'prompt') {
                if (!this.validatePromptModule()) {
                    return false;
                }
            }

            // Growth Profile 검증 (gpModule이 초기화되었으면 validate, 아니면 formData.settings 체크)
            if (this.formData.type_code === 'growth_profile') {
                const hasGpStages = this.gpModule?.stages?.length > 0;
                if (hasGpStages) {
                    if (this.gpModule.validate && !this.gpModule.validate()) {
                        this.showError(this.gpModule.validationError || 'Growth Profile 설정 오류');
                        return false;
                    }
                } else if (!this.formData.settings?.stages?.length) {
                    this.showError('프리셋을 선택해주세요');
                    return false;
                }
            }

            // 대량 수집(bulk_collect) 검증 (Phase D)
            if (this.formData.type_code === 'bulk_collect') {
                if (this.bcModule?.validate && !this.bcModule.validate()) {
                    this.showError(this.bcModule.validationError || '대량 수집 설정 오류');
                    return false;
                }
            }

            // 기타 타입 설정 JSON 검증
            if (this.formData.type_code !== 'collect' && this.formData.type_code !== 'data' && this.formData.type_code !== 'generate' && this.formData.type_code !== 'prompt' && this.formData.type_code !== 'growth_profile' && this.formData.type_code !== 'bulk_collect' && this.settingsJson) {
                try {
                    JSON.parse(this.settingsJson);
                } catch (e) {
                    this.showError('설정 JSON 형식이 올바르지 않습니다');
                    return false;
                }
            }

            return true;
        },

        // ── 키워드 모듈 테스트 ───────────────────────────
        // 저장된 값을 **항상 옵션에 포함**한다.
        // 모델 목록은 비동기로 오는데, 그 전에 select 에 매칭되는 option 이
        // 없으면 브라우저가 value 를 '' 로 만들고 x-model 이 그 빈 값을
        // formData 에 되써 버린다. 그래서 폼을 다시 열면 설정이 사라진
        // 것처럼 보이고, 그대로 저장하면 실제로 지워졌다.
        kwProviders() {
            const set = new Set((this.kwTest.models || []).map(m => m.provider));
            const saved = this.formData?.keyword?.ai_provider;
            if (saved) set.add(saved);
            return Array.from(set).sort();
        },

        kwModels(provider) {
            if (!provider) return [];
            const list = (this.kwTest.models || [])
                .filter(m => m.provider === provider)
                .map(m => m.model_id);
            const saved = this.formData?.keyword?.ai_model;
            if (saved && !list.includes(saved)) list.unshift(saved);
            return list;
        },

        async loadKeywordModels() {
            if (this.kwTest.models.length) return;
            try {
                const r = await fetch('/api/v1/ai-models?capability=text',
                    { credentials: 'include' });
                if (!r.ok) return;
                const d = await r.json();
                this.kwTest.models = (d.models || d.items || d || [])
                    .filter(m => m && m.provider && m.model_id);
            } catch (e) { /* 목록을 못 받아도 직접 저장은 가능하다 */ }
        },

        async runKeywordTest() {
            // 저장하지 않은 현재 화면 값 그대로 돌린다. 저장 후 확인하면
            // 실패한 설정이 이미 남는다.
            //
            // 한 회차는 80초를 넘기기도 하는데 프록시가 60초에서 응답을
            // 끊는다. 그래서 요청을 붙잡지 않고 토큰을 받아 폴링한다.
            this.kwTest.busy = true;
            this.kwTest.error = '';
            this.kwTest.result = null;
            this.kwTest.elapsed = 0;
            try {
                const payload = this.prepareRequestData();
                const started = await this.kwPost('/api/v1/keyword-lab/run', {
                    settings_override: payload.settings || {},
                    force: true,
                    background: true,
                });
                if (!started.task_id) {
                    this.kwTest.result = started;
                    return;
                }
                this.kwTest.result = await this.kwPoll(started.task_id);
            } catch (e) {
                this.kwTest.error = e.message;
            } finally {
                this.kwTest.busy = false;
            }
        },

        async kwPost(url, body) {
            const r = await fetch(url, {
                method: 'POST', credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const text = await r.text();
            if (!r.ok) {
                let detail = `실행 실패 (HTTP ${r.status})`;
                try { detail = JSON.parse(text).detail || detail; } catch (e) {}
                throw new Error(detail);
            }
            // 빈 본문이면 JSON.parse 가 "Unexpected end of JSON input" 을
            // 던진다. 무엇이 잘못됐는지 알 수 있는 말로 바꾼다.
            if (!text) throw new Error('서버가 빈 응답을 돌려줬습니다 (연결이 끊겼을 수 있습니다)');
            return JSON.parse(text);
        },

        async kwPoll(taskId, maxSeconds = 900) {
            const step = 2000;
            for (let waited = 0; waited < maxSeconds * 1000; waited += step) {
                await new Promise(res => setTimeout(res, step));
                this.kwTest.elapsed = Math.round(waited / 1000);
                let row;
                try {
                    const r = await fetch(`/api/v1/keyword-lab/run/${taskId}`,
                        { credentials: 'include' });
                    const text = await r.text();
                    row = text ? JSON.parse(text) : { status: 'running' };
                } catch (e) {
                    continue;   // 일시적 실패는 계속 기다린다
                }
                if (row.status === 'done') return row.result;
                if (row.status === 'failed') throw new Error(row.error || '실행 실패');
            }
            throw new Error('시간이 너무 오래 걸립니다. 동작 로그에서 결과를 확인하세요');
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

            if (this.formData.type_code === 'collect') {
                // 수집 모듈 데이터
                data.schedule_matrix = this.schedule;
                data.settings = {
                    schedule_mode: this.formData.collect_schedule_mode,
                    fixed_times: this.formData.collect_fixed_times,
                    interval_hours: this.formData.collect_interval_hours,
                    collect_type: this.formData.collect_type,
                    // 키워드 수집 소스
                    source_google_trends: this.formData.source_google_trends,
                    source_naver_datalab: this.formData.source_naver_datalab,
                    source_naver_ads: this.formData.source_naver_ads,
                    source_google_planner: this.formData.source_google_planner,
                    // 제목 수집 소스 (뉴스/웹문서)
                    source_naver_news: this.formData.source_naver_news,
                    source_google_news: this.formData.source_google_news,
                    source_naver_webdoc: this.formData.source_naver_webdoc,
                    // 추가 옵션
                    enable_related_search: this.formData.enable_related_search,
                    enable_title_extraction: this.formData.enable_title_extraction,
                    // 키워드 추출 옵션
                    enable_keyword_extraction: this.formData.enable_keyword_extraction,
                    keyword_extraction_method: this.formData.keyword_extraction_method,
                    keyword_extraction_title_limit: this.formData.keyword_extraction_title_limit,
                    keyword_extraction_limit: this.formData.keyword_extraction_limit,
                    // 수집 유형 선택 (일반/대량)
                    enable_normal_collect: this.formData.enable_normal_collect,
                    // DEPRECATED (Phase E): 기존 collect 모듈 호환용 — 신규 모듈은 bulk_collect 타입 사용
                    enable_bulk_collect: this.formData.enable_bulk_collect,
                    // 일반 수집 수량 설정
                    keyword_collect_limit: this.formData.keyword_collect_limit,
                    title_collect_limit: this.formData.title_collect_limit,
                    // 대량 수집 설정
                    // DEPRECATED (Phase E): 기존 collect 모듈 호환용 — 신규 모듈은 bulk_collect 타입 사용
                    bulk_collect_delay: this.formData.bulk_collect_delay,
                    bulk_urls_per_cycle: this.formData.bulk_urls_per_cycle
                };
            } else if (this.formData.type_code === 'data') {
                // 데이터 모듈 설정
                const categoryFilter = this.formData.category_filter?.trim();
                const categories = categoryFilter
                    ? categoryFilter.split(',').map(c => c.trim()).filter(c => c)
                    : [];

                data.settings = {
                    // 실행 방식 (상호 배타적)
                    execution_mode: this.formData.execution_mode,
                    // 수집 모듈 연동 설정 (연동 모드일 때만 사용)
                    collection_link: {
                        enabled: this.formData.execution_mode === 'collection_link',
                        target_modules: ['same_flow'],  // 항상 동일 플로우
                        delay_seconds: this.formData.collection_link_delay
                    },
                    // 데이터 이동 스케줄 설정 (스케줄 모드일 때만 사용)
                    schedule: {
                        enabled: this.formData.execution_mode === 'schedule',
                        mode: this.formData.data_schedule_mode,
                        fixed_times: this.formData.data_fixed_times,
                        interval_hours: this.formData.data_interval_hours,
                        // 활성 시간대 매트릭스 저장
                        schedule_matrix: this.schedule
                    },
                    execution: {
                        max_titles_per_run: this.formData.max_titles_unlimited ? -1 : this.formData.max_titles_per_run,
                        max_titles_unlimited: this.formData.max_titles_unlimited,
                        min_titles_required: this.formData.min_titles_required
                    },
                    filter: {
                        categories: categories,
                        duplicate_handling: this.formData.duplicate_handling
                    },
                    auto_group: this.formData.auto_group,
                    similarity_threshold: this.formData.similarity_threshold
                };
            } else if (this.formData.type_code === 'generate') {
                // 생성 모듈 설정
                data.settings = {
                    internal_links: {
                        enabled: this.formData.il_enabled,
                        intro_count: this.formData.il_intro_count,
                        intro_link_type: this.formData.il_intro_link_type,
                        conclusion_count: this.formData.il_conclusion_count,
                        conclusion_list_style: this.formData.il_conclusion_list_style,
                        similarity_threshold: this.formData.il_similarity_threshold
                    },
                    substitution: {
                        text_replace_enabled: this.formData.text_replace_enabled
                    }
                };
            } else if (this.formData.type_code === 'prompt') {
                // 프롬프트 모듈 설정
                data.settings = this.preparePromptModuleData();
            } else if (this.formData.type_code === 'growth_profile') {
                // Growth Profile 설정 (gpModule 상태 우선, 인라인 폼 formData.settings 폴백)
                const gpSettings = this.gpModule?.toSettings ? this.gpModule.toSettings() : null;
                if (gpSettings && gpSettings.stages && gpSettings.stages.length > 0) {
                    data.settings = gpSettings;
                } else {
                    data.settings = this.formData.settings || {};
                }
            } else if (this.formData.type_code === 'bulk_collect') {
                // 대량 수집(bulk_collect) 설정 직렬화 (Phase D)
                data.settings = this.bcModule?.toSettings
                    ? this.bcModule.toSettings()
                    : (this.formData.settings || {});
            } else if (this.formData.type_code === 'keyword') {
                // data.settings 에 직접 담는다. 예전에는 선언조차 없는 지역
                // 변수 settings 에 넣어 저장이 ReferenceError 로 죽었다.
                const k = this.formData.keyword || {};
                const split = (t) => (t || '').split(',')
                    .map(x => x.trim()).filter(Boolean);
                // 검색광고는 항상 포함한다 — 검색량을 아는 유일한 소스다
                const sources = ['naver_ads'];
                [['src_naver_suggest', 'naver_suggest'],
                 ['src_google_suggest', 'google_suggest'],
                 ['src_gsc', 'gsc'],
                 ['src_google_planner', 'google_planner'],
                 ['src_google_trends', 'google_trends']].forEach(([flag, code]) => {
                    if (k[flag]) sources.push(code);
                });
                data.settings = {
                    keyword: {
                        enabled: true,
                        seeds: split(k.seeds_text),
                        modifiers: split(k.modifiers_text),
                        use_blog_categories: !!k.use_blog_categories,
                        sources: sources,
                        enrich_limit: k.enrich_limit,
                        recurse_adopted: !!k.recurse_adopted,
                        min_volume: k.min_volume,
                        max_volume: k.max_volume,
                        pub_window_days: k.pub_window_days,
                        min_saturation: k.min_saturation,
                        seed_limit: k.seed_limit,
                        measure_limit: k.measure_limit,
                        make_titles: !!k.make_titles,
                        dry_run: !!k.dry_run,
                        ai_provider: k.ai_provider || null,
                        ai_model: k.ai_model || null,
                        titles_per_keyword: k.titles_per_keyword,
                        cluster_enabled: !!k.cluster_enabled,
                        cluster_threshold: k.cluster_threshold,
                        cluster_min_size: k.cluster_min_size,
                        cluster_max_size: k.cluster_max_size,
                        titles_per_cluster: k.titles_per_cluster,
                        min_inventory: k.min_inventory,
                    },
                    // 주기는 bulk_collect 와 같은 자리에 둔다(스케줄러가 그 경로를 본다)
                    schedule: { interval_minutes: k.interval_minutes },
                };
            } else if (this.formData.type_code === 'contact_form') {
                // 애드센스 필수구성 모듈: 문의폼(템플릿/디자인) + 필수페이지(프리셋/편집본)
                // 프리셋 기본과 다른 페이지만 override로 저장(프리셋 변경이 자동 반영되도록).
                // 페이지 생성 토글과 무관하게 저장한다 — 토글을 껐다 켜도 편집본이 남아야 한다.
                const pagesOverrides = {};
                ['privacy', 'terms', 'about', 'contact'].forEach(pt => {
                    if (this.isPageEdited(pt)) {
                        pagesOverrides[pt] = this.formData.pages_body[pt];
                    }
                });
                data.settings = {
                    template_code: this.formData.contact_template_code || 'basic',
                    design_code: this.formData.contact_design_code || 'default',
                    generate_pages: !!this.formData.generate_pages,
                    pages_preset_code: this.formData.pages_preset_code || 'standard',
                    pages_overrides: pagesOverrides,
                };
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

        // 수집 시간 추가 (수집 모듈용)
        addFixedTime() {
            if (!this.newFixedTime) return;

            // 중복 체크
            if (this.formData.collect_fixed_times.includes(this.newFixedTime)) {
                this.showError('이미 등록된 시간입니다');
                return;
            }

            // 시간 추가 및 정렬
            this.formData.collect_fixed_times.push(this.newFixedTime);
            this.formData.collect_fixed_times.sort();
            this.newFixedTime = '';
        },

        // 수집 시간 삭제 (수집 모듈용)
        removeFixedTime(time) {
            const index = this.formData.collect_fixed_times.indexOf(time);
            if (index > -1) {
                this.formData.collect_fixed_times.splice(index, 1);
            }
        },

        // 데이터 이동 시간 추가 (데이터 모듈용)
        addDataFixedTime() {
            if (!this.newDataFixedTime) return;

            // 중복 체크
            if (this.formData.data_fixed_times.includes(this.newDataFixedTime)) {
                this.showError('이미 등록된 시간입니다');
                return;
            }

            // 시간 추가 및 정렬
            this.formData.data_fixed_times.push(this.newDataFixedTime);
            this.formData.data_fixed_times.sort();
            this.newDataFixedTime = '';
        },

        // 데이터 이동 시간 삭제 (데이터 모듈용)
        removeDataFixedTime(time) {
            const index = this.formData.data_fixed_times.indexOf(time);
            if (index > -1) {
                this.formData.data_fixed_times.splice(index, 1);
            }
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
        },

        // 문의폼 템플릿 목록 로드 (contact_form 모듈용)
        async loadContactFormTemplates() {
            try {
                const r = await fetch('/api/v1/settings/contact-form-templates', { credentials: 'include' });
                if (r.ok) {
                    const d = await r.json();
                    this.contactFormTemplates = d.templates || [];
                }
            } catch (e) { console.warn('[contact_form] 템플릿 로드 실패', e); }
        },

        // 문의폼 디자인 프리셋 목록 로드 (contact_form 모듈용)
        async loadContactFormDesigns() {
            try {
                const r = await fetch('/api/v1/settings/contact-form-designs', { credentials: 'include' });
                if (r.ok) {
                    const d = await r.json();
                    this.contactFormDesigns = d.designs || [];
                }
            } catch (e) { console.warn('[contact_form] 디자인 로드 실패', e); }
        },

        // 필수페이지 문체 프리셋 목록 로드 + 편집창 초기화
        async loadRequiredPagePresets() {
            try {
                const r = await fetch('/api/v1/settings/required-page-presets', { credentials: 'include' });
                if (r.ok) {
                    const d = await r.json();
                    this.requiredPagePresets = d.presets || [];
                }
            } catch (e) { console.warn('[contact_form] 필수페이지 프리셋 로드 실패', e); }
            this._initPagesBody();
        },

        // 필수페이지 편집창 초기값: 저장된 편집본(override) 우선, 없으면 선택 프리셋 기본
        _initPagesBody() {
            const ov = this.formData._pages_overrides_init || {};
            ['privacy', 'terms', 'about', 'contact'].forEach(pt => {
                this.formData.pages_body[pt] = ov[pt] || this._presetDefaultBody(this.formData.pages_preset_code, pt);
            });
            this._pagesPresetPrev = this.formData.pages_preset_code;
        },

        // 특정 프리셋/페이지의 기본 본문
        _presetDefaultBody(presetCode, pageType) {
            const p = this.requiredPagePresets.find(x => x.code === presetCode);
            return (p && p.pages && p.pages[pageType] && p.pages[pageType].body) || '';
        },

        // 프리셋 변경: 사용자가 수정하지 않은 페이지만 새 프리셋 기본값으로 교체
        onPagesPresetChange() {
            const prev = this._pagesPresetPrev;
            const next = this.formData.pages_preset_code;
            ['privacy', 'terms', 'about', 'contact'].forEach(pt => {
                const prevDefault = this._presetDefaultBody(prev, pt);
                if ((this.formData.pages_body[pt] || '') === prevDefault) {
                    this.formData.pages_body[pt] = this._presetDefaultBody(next, pt);
                }
            });
            this._pagesPresetPrev = next;
        },

        // 특정 페이지가 프리셋 기본값과 다른지(직접 편집됨)
        isPageEdited(pageType) {
            return (this.formData.pages_body[pageType] || '')
                !== this._presetDefaultBody(this.formData.pages_preset_code, pageType);
        },

        // 특정 페이지를 현재 프리셋 기본값으로 되돌림
        resetPageBody(pageType) {
            this.formData.pages_body[pageType] =
                this._presetDefaultBody(this.formData.pages_preset_code, pageType);
        },

        // 페이지 타입 라벨
        pageTypeLabel(pageType) {
            return ({ privacy: '개인정보처리방침', terms: '이용약관', about: '소개', contact: '문의' })[pageType] || pageType;
        },

        // API 상태 로드 (수집 모듈용)
        async loadApiStatus() {
            console.log('loadApiStatus 호출됨');
            this.apiStatusLoading = true;
            try {
                const response = await fetch('/api/v1/settings/api-status', {
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    console.log('API 상태 응답:', data);
                    this.apiStatus = {
                        naver_ads: data.naver_ads || false,
                        naver_datalab: data.naver_datalab || false,
                        google_trends: true,  // 구글 트렌드는 항상 사용 가능
                        google_planner: data.google_planner || false,
                        naver_news: data.naver_news || false,  // 네이버 API (client_id)
                        google_news: true,  // 구글 뉴스 RSS는 항상 사용 가능
                        naver_webdoc: data.naver_news || false  // 네이버 웹문서 (client_id 공유)
                    };
                    console.log('apiStatus 업데이트됨:', this.apiStatus);

                    // API가 비활성화된 소스는 체크 해제
                    this.syncSourcesWithApiStatus();
                }
            } catch (error) {
                console.error('API 상태 로드 실패:', error);
            } finally {
                this.apiStatusLoading = false;
                console.log('apiStatusLoading 완료, apiStatus:', this.apiStatus);
            }
        },

        // API 상태에 따라 소스 선택 동기화
        syncSourcesWithApiStatus() {
            // API가 비활성화된 소스는 선택 해제
            if (!this.apiStatus.naver_ads) {
                this.formData.source_naver_ads = false;
            }
            if (!this.apiStatus.naver_datalab) {
                this.formData.source_naver_datalab = false;
            }
            if (!this.apiStatus.google_planner) {
                this.formData.source_google_planner = false;
            }
            if (!this.apiStatus.naver_news) {
                this.formData.source_naver_news = false;
            }
            if (!this.apiStatus.naver_webdoc) {
                this.formData.source_naver_webdoc = false;
            }
            // 구글 트렌드와 구글 뉴스 RSS는 API 키 불필요 - 동기화하지 않음
        },

        // 소스 체크박스 클릭 핸들러
        toggleSource(source) {
            // API가 활성화되어 있을 때만 토글 가능
            if (source === 'naver_ads' && this.apiStatus.naver_ads) {
                this.formData.source_naver_ads = !this.formData.source_naver_ads;
            } else if (source === 'naver_datalab' && this.apiStatus.naver_datalab) {
                this.formData.source_naver_datalab = !this.formData.source_naver_datalab;
            } else if (source === 'google_trends') {
                this.formData.source_google_trends = !this.formData.source_google_trends;
            } else if (source === 'google_planner' && this.apiStatus.google_planner) {
                this.formData.source_google_planner = !this.formData.source_google_planner;
            } else if (source === 'naver_news' && this.apiStatus.naver_news) {
                this.formData.source_naver_news = !this.formData.source_naver_news;
            } else if (source === 'google_news') {
                // 구글 뉴스 RSS는 API 키 불필요 - 항상 토글 가능
                this.formData.source_google_news = !this.formData.source_google_news;
            } else if (source === 'naver_webdoc' && this.apiStatus.naver_webdoc) {
                this.formData.source_naver_webdoc = !this.formData.source_naver_webdoc;
            }
        },

        // 소스가 활성화 가능한지 확인
        isSourceEnabled(source) {
            if (source === 'naver_ads') return this.apiStatus.naver_ads;
            if (source === 'naver_datalab') return this.apiStatus.naver_datalab;
            if (source === 'google_trends') return true;  // 항상 사용 가능
            if (source === 'google_planner') return this.apiStatus.google_planner;
            if (source === 'naver_news') return this.apiStatus.naver_news;
            if (source === 'google_news') return true;  // 항상 사용 가능
            if (source === 'naver_webdoc') return this.apiStatus.naver_webdoc;
            return false;
        },

        // 필수 API 설정 여부 확인 (네이버 광고 API 필수)
        hasRequiredAPI() {
            return this.apiStatus.naver_ads === true;
        },

        // =========================================
        // 프롬프트 모듈 메서드 (prompt-form.js에서 믹스인)
        // =========================================
        // 아래 메서드들은 prompt-form.js가 로드되면 자동으로 추가됨
        // loadCategories, initPromptModuleFromData, toggleTopicExpand,
        // isTopicSelected, toggleTopicSelection, isSubtopicSelected,
        // toggleSubtopicSelection, onCategoryChange, getCategoryDisplayName,
        // removeCategory, loadBlogsByCategories, toggleTitleStyle,
        // toggleBlogSelection, selectAllMatchedBlogs, removeBlog,
        // getBlogName, validatePromptModule, preparePromptModuleData
        ...(window.promptModuleMethods || {}),
        ...(window.promptModuleLinkingMethods || {}),
        ...(window.promptTestMethods || {})
    };
}

// 전역 함수로 노출
window.moduleFormApp = moduleFormApp;