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

    return {
        // 폼 상태
        loading: false,
        isEdit: !!initialModule?.id,
        module: initialModule,
        moduleType: initialType,

        // 프롬프트 모듈 상태
        promptModule: promptModuleState,

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
            enable_bulk_collect: initialModule?.settings?.enable_bulk_collect ?? false,
            // 일반 수집 수량 설정 (키워드/제목 각각)
            keyword_collect_limit: initialModule?.settings?.keyword_collect_limit || 100,
            title_collect_limit: initialModule?.settings?.title_collect_limit || 100,
            // 대량 수집 설정
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
            // 생성 모듈 필드들 (참조자료 수집 설정)
            ref_max_search: initialModule?.settings?.reference?.max_search ?? 30,
            ref_crawl_target: initialModule?.settings?.reference?.crawl_target ?? 10,
            ref_summary_count: initialModule?.settings?.reference?.summary_count ?? 3,
            ref_summary_method: initialModule?.settings?.reference?.summary_method || 'ai',
            ref_ai_provider: initialModule?.settings?.reference?.ai_provider || 'openai',
            ref_ai_model: initialModule?.settings?.reference?.ai_model || 'gpt-4.1-mini',
            ref_summary_style: initialModule?.settings?.reference?.summary_style || 'concise',
            ref_algorithm_type: initialModule?.settings?.reference?.algorithm_type || 'textrank',
            ref_max_length: initialModule?.settings?.reference?.max_length ?? 500
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

            // 프롬프트 모듈인 경우 초기화
            if (typeCode === 'prompt') {
                console.log('프롬프트 모듈 감지 - 카테고리 로드 시작');
                this.loadCategories();
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
            if (this.formData.type_code === 'republish' || this.formData.type_code === 'collect' || this.formData.type_code === 'data') {
                // 데이터 모듈: module.settings.schedule.schedule_matrix에서 먼저 로드 (우선순위 높음)
                // ★ this.module.settings를 사용해야 함 (this.formData.settings가 아님)
                const moduleSettings = this.module?.settings || {};
                if (this.formData.type_code === 'data' && this.isEdit && moduleSettings?.schedule?.schedule_matrix) {
                    this.schedule = JSON.parse(JSON.stringify(moduleSettings.schedule.schedule_matrix));
                    console.log('[initializeSchedule] 데이터 모듈 schedule_matrix 로드됨:', this.schedule?.length, 'x', this.schedule?.[0]?.length);
                } else if (this.isEdit && this.module?.schedule_matrix) {
                    // 재발행/수집 모듈: 루트 레벨 schedule_matrix에서 로드
                    this.schedule = JSON.parse(JSON.stringify(this.module.schedule_matrix));
                } else {
                    // 기본 스케줄 설정
                    if (this.formData.type_code === 'collect' || this.formData.type_code === 'data') {
                        // 수집/데이터 모듈: 기본 24시간 활성
                        this.schedule = Array(7).fill().map(() => Array(24).fill(true));
                    } else {
                        // 재발행 모듈: 기본 평일 9-21시
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

                // 수집 유형 검증 (최소 하나 선택 필수)
                if (!this.formData.enable_normal_collect && !this.formData.enable_bulk_collect) {
                    this.showError('최소 하나의 수집 유형을 선택해주세요 (일반 수집 또는 대량 수집)');
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
                if (this.formData.ref_max_search < 10 || this.formData.ref_max_search > 100) {
                    this.showError('최대 검색 수는 10~100 범위여야 합니다');
                    return false;
                }
                if (this.formData.ref_crawl_target < 3 || this.formData.ref_crawl_target > 30) {
                    this.showError('크롤링 목표는 3~30 범위여야 합니다');
                    return false;
                }
                if (this.formData.ref_summary_count < 1 || this.formData.ref_summary_count > 10) {
                    this.showError('요약 선택 수는 1~10 범위여야 합니다');
                    return false;
                }
                if (this.formData.ref_summary_count > this.formData.ref_crawl_target) {
                    this.showError('요약 선택 수는 크롤링 목표 이하여야 합니다');
                    return false;
                }
                if (this.formData.ref_max_length < 200 || this.formData.ref_max_length > 2000) {
                    this.showError('요약 최대 글자수는 200~2000 범위여야 합니다');
                    return false;
                }
            }

            // 프롬프트 모듈 검증
            if (this.formData.type_code === 'prompt') {
                if (!this.validatePromptModule()) {
                    return false;
                }
            }

            // 기타 타입 설정 JSON 검증
            if (this.formData.type_code !== 'republish' && this.formData.type_code !== 'collect' && this.formData.type_code !== 'data' && this.formData.type_code !== 'generate' && this.settingsJson) {
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
            } else if (this.formData.type_code === 'collect') {
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
                    enable_bulk_collect: this.formData.enable_bulk_collect,
                    // 일반 수집 수량 설정
                    keyword_collect_limit: this.formData.keyword_collect_limit,
                    title_collect_limit: this.formData.title_collect_limit,
                    // 대량 수집 설정
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
                    reference: {
                        max_search: this.formData.ref_max_search,
                        crawl_target: this.formData.ref_crawl_target,
                        summary_count: this.formData.ref_summary_count,
                        summary_method: this.formData.ref_summary_method,
                        ai_provider: this.formData.ref_ai_provider,
                        ai_model: this.formData.ref_ai_model,
                        summary_style: this.formData.ref_summary_style,
                        algorithm_type: this.formData.ref_algorithm_type,
                        max_length: this.formData.ref_max_length
                    }
                };
            } else if (this.formData.type_code === 'prompt') {
                // 프롬프트 모듈 설정
                data.settings = this.preparePromptModuleData();
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
        ...(window.promptModuleMethods || {})
    };
}

// 전역 함수로 노출
window.moduleFormApp = moduleFormApp;