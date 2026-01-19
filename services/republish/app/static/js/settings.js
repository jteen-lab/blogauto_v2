/**
 * 설정 하단 시트 JavaScript
 *
 * Features:
 * - 설정 조회/저장
 * - 탭 네비게이션
 * - API 키 마스킹 표시
 * - 네이버 검색광고 API 연동
 * - 경고 메시지 표시
 * - 하단 시트 애니메이션
 */

// API 기본 경로
const SETTINGS_API_BASE = '/api/v1';

/**
 * 설정 모달 열기 (전역 함수)
 */
function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    const backdrop = document.getElementById('settingsBackdrop');

    if (!modal || !backdrop) return;

    // 백드롭 표시
    backdrop.classList.remove('hidden');
    setTimeout(() => {
        backdrop.style.opacity = '1';
    }, 10);

    // 시트 표시 (하단에서 슬라이드 업)
    modal.classList.remove('translate-y-full');

    // 스크롤 방지
    document.body.style.overflow = 'hidden';

    // Alpine.js 컴포넌트에 이벤트 전달
    const event = new CustomEvent('settings-modal-open');
    modal.dispatchEvent(event);
}

/**
 * 설정 모달 닫기 (전역 함수)
 */
function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    const backdrop = document.getElementById('settingsBackdrop');

    if (!modal || !backdrop) return;

    // 시트 숨기기 (하단으로 슬라이드 다운)
    modal.classList.add('translate-y-full');

    // 백드롭 숨기기
    backdrop.style.opacity = '0';
    setTimeout(() => {
        backdrop.classList.add('hidden');
    }, 300);

    // 스크롤 복원
    document.body.style.overflow = '';
}

/**
 * 설정 앱 Alpine.js 컴포넌트
 */
function settingsApp() {
    return {
        // 상태
        activeTab: 'account',
        loading: false,
        saving: false,
        showOpenaiKey: false,
        showClaudeKey: false,
        showBloggerWarning: false,

        // 네이버 검색광고 API 상태
        showNaverApiKey: false,
        showNaverSecretKey: false,
        testingNaverAds: false,
        naverAdsTestResult: '',
        naverAdsTestSuccess: false,

        // 구글 트렌드 상태
        testingGoogleTrends: false,
        googleTrendsTestResult: '',
        googleTrendsTestSuccess: false,
        googleTrendsConnected: false,
        googleTrendsSample: [],

        // 네이버 검색 API 상태
        showNaverSearchClientId: false,
        showNaverSearchClientSecret: false,
        testingNaverSearch: false,
        naverSearchTestResult: '',
        naverSearchTestSuccess: false,

        // 네이버 데이터랩 상태
        showNaverDatalabClientId: false,
        showNaverDatalabClientSecret: false,
        testingNaverDatalab: false,
        naverDatalabTestResult: '',
        naverDatalabTestSuccess: false,

        // 구글 키워드 플래너 상태
        showGoogleAdsDeveloperToken: false,
        showGoogleAdsClientId: false,
        showGoogleAdsClientSecret: false,
        showGoogleAdsRefreshToken: false,
        testingGooglePlanner: false,
        googlePlannerTestResult: '',
        googlePlannerTestSuccess: false,

        // 설정 데이터
        settings: {
            has_openai_key: false,
            has_claude_key: false,
            has_naver_ads_api: false,
            has_naver_datalab_api: false,
            blogger_hourly_limit: 2
        },

        // 폼 데이터
        form: {
            openai_api_key: '',
            claude_api_key: '',
            blogger_hourly_limit: 2,
            // 네이버 검색광고 API
            naver_ads_api_key: '',
            naver_ads_secret_key: '',
            naver_ads_customer_id: '',
            has_naver_ads_api: false,
            // 네이버 검색 API
            naver_search_client_id: '',
            naver_search_client_secret: '',
            has_naver_search_api: false,
            // 네이버 데이터랩 API
            naver_datalab_client_id: '',
            naver_datalab_client_secret: '',
            has_naver_datalab_api: false,
            // 구글 키워드 플래너 API
            google_ads_developer_token: '',
            google_ads_client_id: '',
            google_ads_client_secret: '',
            google_ads_refresh_token: '',
            google_ads_customer_id: '',
            has_google_keyword_planner_api: false
        },

        /**
         * 초기화
         */
        init() {
            // 모달 열림 이벤트 리스닝
            this.$el.addEventListener('settings-modal-open', () => {
                this.loadSettings();
            });
        },

        /**
         * 설정 로드
         */
        async loadSettings() {
            this.loading = true;

            try {
                const response = await fetch(`${SETTINGS_API_BASE}/settings`, {
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    this.settings = data;

                    // 폼 초기화 - 마스킹된 키 값 표시
                    this.form = {
                        openai_api_key: data.openai_api_key || '',
                        claude_api_key: data.claude_api_key || '',
                        blogger_hourly_limit: data.blogger_hourly_limit || 2,
                        // 네이버 검색광고 API
                        naver_ads_api_key: data.naver_ads_api_key || '',
                        naver_ads_secret_key: data.naver_ads_secret_key || '',
                        naver_ads_customer_id: data.naver_ads_customer_id || '',
                        has_naver_ads_api: data.has_naver_ads_api || false,
                        // 네이버 검색 API
                        naver_search_client_id: data.naver_search_client_id || '',
                        naver_search_client_secret: data.naver_search_client_secret || '',
                        has_naver_search_api: data.has_naver_search_api || false,
                        // 네이버 데이터랩 API
                        naver_datalab_client_id: data.naver_datalab_client_id || '',
                        naver_datalab_client_secret: data.naver_datalab_client_secret || '',
                        has_naver_datalab_api: data.has_naver_datalab_api || false,
                        // 구글 키워드 플래너 API
                        google_ads_developer_token: data.google_ads_developer_token || '',
                        google_ads_client_id: data.google_ads_client_id || '',
                        google_ads_client_secret: data.google_ads_client_secret || '',
                        google_ads_refresh_token: data.google_ads_refresh_token || '',
                        google_ads_customer_id: data.google_ads_customer_id || '',
                        has_google_keyword_planner_api: data.has_google_keyword_planner_api || false
                    };

                    // 경고 메시지 체크
                    this.checkBloggerWarning();
                } else {
                    console.error('설정 로드 실패:', response.status);
                    showErrorMessage('설정을 불러오는데 실패했습니다');
                }
            } catch (error) {
                console.error('설정 로드 에러:', error);
                showErrorMessage('설정을 불러오는데 실패했습니다');
            } finally {
                this.loading = false;
            }
        },

        /**
         * 마스킹된 키인지 확인 (****가 포함되어 있으면 마스킹된 키)
         */
        isMaskedKey(key) {
            return key && key.includes('****');
        },

        /**
         * 설정 저장
         */
        async saveSettings() {
            this.saving = true;

            try {
                const payload = {
                    blogger_hourly_limit: parseInt(this.form.blogger_hourly_limit)
                };

                // API 키는 새로 입력된 경우에만 포함 (마스킹된 값은 제외)
                if (this.form.openai_api_key && !this.isMaskedKey(this.form.openai_api_key)) {
                    payload.openai_api_key = this.form.openai_api_key;
                }
                if (this.form.claude_api_key && !this.isMaskedKey(this.form.claude_api_key)) {
                    payload.claude_api_key = this.form.claude_api_key;
                }

                // 네이버 검색광고 API 키
                if (this.form.naver_ads_api_key && !this.isMaskedKey(this.form.naver_ads_api_key)) {
                    payload.naver_ads_api_key = this.form.naver_ads_api_key;
                }
                if (this.form.naver_ads_secret_key && !this.isMaskedKey(this.form.naver_ads_secret_key)) {
                    payload.naver_ads_secret_key = this.form.naver_ads_secret_key;
                }
                if (this.form.naver_ads_customer_id) {
                    payload.naver_ads_customer_id = this.form.naver_ads_customer_id;
                }

                // 네이버 검색 API 키
                if (this.form.naver_search_client_id && !this.isMaskedKey(this.form.naver_search_client_id)) {
                    payload.naver_search_client_id = this.form.naver_search_client_id;
                }
                if (this.form.naver_search_client_secret && !this.isMaskedKey(this.form.naver_search_client_secret)) {
                    payload.naver_search_client_secret = this.form.naver_search_client_secret;
                }

                // 네이버 데이터랩 API 키
                if (this.form.naver_datalab_client_id && !this.isMaskedKey(this.form.naver_datalab_client_id)) {
                    payload.naver_datalab_client_id = this.form.naver_datalab_client_id;
                }
                if (this.form.naver_datalab_client_secret && !this.isMaskedKey(this.form.naver_datalab_client_secret)) {
                    payload.naver_datalab_client_secret = this.form.naver_datalab_client_secret;
                }

                // 구글 키워드 플래너 API 키
                if (this.form.google_ads_developer_token && !this.isMaskedKey(this.form.google_ads_developer_token)) {
                    payload.google_ads_developer_token = this.form.google_ads_developer_token;
                }
                if (this.form.google_ads_client_id && !this.isMaskedKey(this.form.google_ads_client_id)) {
                    payload.google_ads_client_id = this.form.google_ads_client_id;
                }
                if (this.form.google_ads_client_secret && !this.isMaskedKey(this.form.google_ads_client_secret)) {
                    payload.google_ads_client_secret = this.form.google_ads_client_secret;
                }
                if (this.form.google_ads_refresh_token && !this.isMaskedKey(this.form.google_ads_refresh_token)) {
                    payload.google_ads_refresh_token = this.form.google_ads_refresh_token;
                }
                if (this.form.google_ads_customer_id) {
                    payload.google_ads_customer_id = this.form.google_ads_customer_id;
                }

                const response = await fetch(`${SETTINGS_API_BASE}/settings`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const result = await response.json();
                    showSuccessMessage('설정이 저장되었습니다');

                    // 설정 데이터 업데이트
                    if (result.data) {
                        this.settings.has_openai_key = result.data.has_openai_key;
                        this.settings.has_claude_key = result.data.has_claude_key;
                        this.settings.has_naver_ads_api = result.data.has_naver_ads_api;
                        this.settings.has_naver_datalab_api = result.data.has_naver_datalab_api;
                        // 마스킹된 키 값 업데이트
                        this.form.openai_api_key = result.data.openai_api_key || '';
                        this.form.claude_api_key = result.data.claude_api_key || '';
                        this.form.naver_ads_api_key = result.data.naver_ads_api_key || '';
                        this.form.naver_ads_secret_key = result.data.naver_ads_secret_key || '';
                        this.form.naver_ads_customer_id = result.data.naver_ads_customer_id || '';
                        this.form.has_naver_ads_api = result.data.has_naver_ads_api || false;
                        // 네이버 검색 API
                        this.form.naver_search_client_id = result.data.naver_search_client_id || '';
                        this.form.naver_search_client_secret = result.data.naver_search_client_secret || '';
                        this.form.has_naver_search_api = result.data.has_naver_search_api || false;
                        // 네이버 데이터랩 API
                        this.form.naver_datalab_client_id = result.data.naver_datalab_client_id || '';
                        this.form.naver_datalab_client_secret = result.data.naver_datalab_client_secret || '';
                        this.form.has_naver_datalab_api = result.data.has_naver_datalab_api || false;
                        // 구글 키워드 플래너 API
                        this.settings.has_google_keyword_planner_api = result.data.has_google_keyword_planner_api;
                        this.form.google_ads_developer_token = result.data.google_ads_developer_token || '';
                        this.form.google_ads_client_id = result.data.google_ads_client_id || '';
                        this.form.google_ads_client_secret = result.data.google_ads_client_secret || '';
                        this.form.google_ads_refresh_token = result.data.google_ads_refresh_token || '';
                        this.form.google_ads_customer_id = result.data.google_ads_customer_id || '';
                        this.form.has_google_keyword_planner_api = result.data.has_google_keyword_planner_api || false;
                    }

                    // 모달 닫기
                    this.closeModal();
                } else {
                    const error = await response.json();
                    showErrorMessage(error.detail || '설정 저장에 실패했습니다');
                }
            } catch (error) {
                console.error('설정 저장 에러:', error);
                showErrorMessage('설정 저장에 실패했습니다');
            } finally {
                this.saving = false;
            }
        },

        /**
         * 모달 닫기
         */
        closeModal() {
            closeSettingsModal();

            // 상태 초기화
            this.activeTab = 'account';
            this.showOpenaiKey = false;
            this.showClaudeKey = false;
            this.showNaverApiKey = false;
            this.showNaverSecretKey = false;
            this.showNaverSearchClientId = false;
            this.showNaverSearchClientSecret = false;
            this.naverSearchTestResult = '';
            this.showNaverDatalabClientId = false;
            this.showNaverDatalabClientSecret = false;
            this.naverAdsTestResult = '';
            this.googleTrendsTestResult = '';
            this.googleTrendsSample = [];
            this.naverDatalabTestResult = '';
            // 구글 키워드 플래너 상태 초기화
            this.showGoogleAdsDeveloperToken = false;
            this.showGoogleAdsClientId = false;
            this.showGoogleAdsClientSecret = false;
            this.showGoogleAdsRefreshToken = false;
            this.googlePlannerTestResult = '';
        },

        /**
         * Blogger 발행 제한 경고 체크
         */
        checkBloggerWarning() {
            this.showBloggerWarning = parseInt(this.form.blogger_hourly_limit) >= 3;
        },

        /**
         * 비밀번호 변경 (미구현)
         */
        changePassword() {
            showErrorMessage('비밀번호 변경 기능은 준비 중입니다');
        },

        /**
         * 네이버 검색광고 API 연결 테스트
         */
        async testNaverAdsConnection() {
            this.testingNaverAds = true;
            this.naverAdsTestResult = '';

            try {
                // 먼저 설정을 저장 (새로 입력된 값이 있을 수 있으므로)
                const payload = {};
                if (this.form.naver_ads_api_key && !this.isMaskedKey(this.form.naver_ads_api_key)) {
                    payload.naver_ads_api_key = this.form.naver_ads_api_key;
                }
                if (this.form.naver_ads_secret_key && !this.isMaskedKey(this.form.naver_ads_secret_key)) {
                    payload.naver_ads_secret_key = this.form.naver_ads_secret_key;
                }
                if (this.form.naver_ads_customer_id) {
                    payload.naver_ads_customer_id = this.form.naver_ads_customer_id;
                }

                // 새로 입력된 값이 있으면 먼저 저장
                if (Object.keys(payload).length > 0) {
                    await fetch(`${SETTINGS_API_BASE}/settings`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    });
                }

                // 연결 테스트 API 호출
                const response = await fetch(`${SETTINGS_API_BASE}/naver-ads/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                const result = await response.json();

                if (result.success) {
                    this.naverAdsTestSuccess = true;
                    this.naverAdsTestResult = '연결 성공';
                    this.form.has_naver_ads_api = true;
                } else {
                    this.naverAdsTestSuccess = false;
                    this.naverAdsTestResult = result.error || '연결 실패';
                }
            } catch (error) {
                console.error('네이버 API 테스트 에러:', error);
                this.naverAdsTestSuccess = false;
                this.naverAdsTestResult = '테스트 실패';
            } finally {
                this.testingNaverAds = false;
            }
        },

        /**
         * 네이버 검색 API 연결 테스트
         */
        async testNaverSearchConnection() {
            this.testingNaverSearch = true;
            this.naverSearchTestResult = '';

            try {
                // 먼저 설정을 저장 (새로 입력된 값이 있을 수 있으므로)
                const payload = {};
                if (this.form.naver_search_client_id && !this.isMaskedKey(this.form.naver_search_client_id)) {
                    payload.naver_search_client_id = this.form.naver_search_client_id;
                }
                if (this.form.naver_search_client_secret && !this.isMaskedKey(this.form.naver_search_client_secret)) {
                    payload.naver_search_client_secret = this.form.naver_search_client_secret;
                }

                // 새로 입력된 값이 있으면 먼저 저장
                if (Object.keys(payload).length > 0) {
                    await fetch(`${SETTINGS_API_BASE}/settings`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    });
                }

                // 연결 테스트 API 호출
                const response = await fetch(`${SETTINGS_API_BASE}/naver-search/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                const result = await response.json();

                if (result.success) {
                    this.naverSearchTestSuccess = true;
                    this.naverSearchTestResult = '연결 성공';
                    this.form.has_naver_search_api = true;
                } else {
                    this.naverSearchTestSuccess = false;
                    this.naverSearchTestResult = result.error || '연결 실패';
                }
            } catch (error) {
                console.error('네이버 검색 API 테스트 에러:', error);
                this.naverSearchTestSuccess = false;
                this.naverSearchTestResult = '테스트 실패';
            } finally {
                this.testingNaverSearch = false;
            }
        },

        /**
         * 구글 트렌드 API 연결 테스트
         */
        async testGoogleTrendsConnection() {
            this.testingGoogleTrends = true;
            this.googleTrendsTestResult = '';
            this.googleTrendsSample = [];

            try {
                const response = await fetch(`${SETTINGS_API_BASE}/google-trends/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                const result = await response.json();

                if (result.success) {
                    this.googleTrendsTestSuccess = true;
                    this.googleTrendsTestResult = '연결 성공';
                    this.googleTrendsConnected = true;
                    // 샘플 인기 검색어 표시
                    if (result.sample_trending) {
                        this.googleTrendsSample = result.sample_trending;
                    }
                } else {
                    this.googleTrendsTestSuccess = false;
                    this.googleTrendsTestResult = result.error || '연결 실패';
                }
            } catch (error) {
                console.error('구글 트렌드 테스트 에러:', error);
                this.googleTrendsTestSuccess = false;
                this.googleTrendsTestResult = '테스트 실패';
            } finally {
                this.testingGoogleTrends = false;
            }
        },

        /**
         * 네이버 데이터랩 API 연결 테스트
         */
        async testNaverDatalabConnection() {
            this.testingNaverDatalab = true;
            this.naverDatalabTestResult = '';

            try {
                // 먼저 설정을 저장 (새로 입력된 값이 있을 수 있으므로)
                const payload = {};
                if (this.form.naver_datalab_client_id && !this.isMaskedKey(this.form.naver_datalab_client_id)) {
                    payload.naver_datalab_client_id = this.form.naver_datalab_client_id;
                }
                if (this.form.naver_datalab_client_secret && !this.isMaskedKey(this.form.naver_datalab_client_secret)) {
                    payload.naver_datalab_client_secret = this.form.naver_datalab_client_secret;
                }

                // 새로 입력된 값이 있으면 먼저 저장
                if (Object.keys(payload).length > 0) {
                    await fetch(`${SETTINGS_API_BASE}/settings`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    });
                }

                // 연결 테스트 API 호출
                const response = await fetch(`${SETTINGS_API_BASE}/naver-datalab/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                const result = await response.json();

                if (result.success) {
                    this.naverDatalabTestSuccess = true;
                    this.naverDatalabTestResult = '연결 성공';
                    this.form.has_naver_datalab_api = true;
                } else {
                    this.naverDatalabTestSuccess = false;
                    this.naverDatalabTestResult = result.error || '연결 실패';
                }
            } catch (error) {
                console.error('네이버 데이터랩 테스트 에러:', error);
                this.naverDatalabTestSuccess = false;
                this.naverDatalabTestResult = '테스트 실패';
            } finally {
                this.testingNaverDatalab = false;
            }
        },

        /**
         * 구글 키워드 플래너 API 연결 테스트
         */
        async testGoogleKeywordPlannerConnection() {
            this.testingGooglePlanner = true;
            this.googlePlannerTestResult = '';

            try {
                // 먼저 설정을 저장 (새로 입력된 값이 있을 수 있으므로)
                const payload = {};
                if (this.form.google_ads_developer_token && !this.isMaskedKey(this.form.google_ads_developer_token)) {
                    payload.google_ads_developer_token = this.form.google_ads_developer_token;
                }
                if (this.form.google_ads_client_id && !this.isMaskedKey(this.form.google_ads_client_id)) {
                    payload.google_ads_client_id = this.form.google_ads_client_id;
                }
                if (this.form.google_ads_client_secret && !this.isMaskedKey(this.form.google_ads_client_secret)) {
                    payload.google_ads_client_secret = this.form.google_ads_client_secret;
                }
                if (this.form.google_ads_refresh_token && !this.isMaskedKey(this.form.google_ads_refresh_token)) {
                    payload.google_ads_refresh_token = this.form.google_ads_refresh_token;
                }
                if (this.form.google_ads_customer_id) {
                    payload.google_ads_customer_id = this.form.google_ads_customer_id;
                }

                // 새로 입력된 값이 있으면 먼저 저장
                if (Object.keys(payload).length > 0) {
                    await fetch(`${SETTINGS_API_BASE}/settings`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    });
                }

                // 연결 테스트 API 호출
                const response = await fetch(`${SETTINGS_API_BASE}/google-keyword-planner/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include'
                });

                const result = await response.json();

                if (result.success) {
                    this.googlePlannerTestSuccess = true;
                    this.googlePlannerTestResult = '연결 성공';
                    this.form.has_google_keyword_planner_api = true;
                } else {
                    this.googlePlannerTestSuccess = false;
                    this.googlePlannerTestResult = result.error || '연결 실패';
                }
            } catch (error) {
                console.error('구글 키워드 플래너 테스트 에러:', error);
                this.googlePlannerTestSuccess = false;
                this.googlePlannerTestResult = '테스트 실패';
            } finally {
                this.testingGooglePlanner = false;
            }
        }
    };
}

// ESC 키로 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('settingsModal');
        if (modal && !modal.classList.contains('translate-y-full')) {
            closeSettingsModal();
        }
    }
});
