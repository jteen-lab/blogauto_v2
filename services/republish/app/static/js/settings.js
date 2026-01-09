/**
 * 설정 하단 시트 JavaScript
 *
 * Features:
 * - 설정 조회/저장
 * - 탭 네비게이션
 * - API 키 마스킹 표시
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

        // 설정 데이터
        settings: {
            has_openai_key: false,
            has_claude_key: false,
            blogger_hourly_limit: 2
        },

        // 폼 데이터
        form: {
            openai_api_key: '',
            claude_api_key: '',
            blogger_hourly_limit: 2
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
                        blogger_hourly_limit: data.blogger_hourly_limit || 2
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
                        // 마스킹된 키 값 업데이트
                        this.form.openai_api_key = result.data.openai_api_key || '';
                        this.form.claude_api_key = result.data.claude_api_key || '';
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
