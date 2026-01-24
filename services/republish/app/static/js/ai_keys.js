/**
 * AI API 키 다계정 관리 JavaScript
 *
 * Features:
 * - 다계정 API 키 CRUD
 * - 우선순위 관리
 * - 상태 표시
 */

// AI 키 관리 믹스인 (settingsApp에서 사용)
const aiKeysMixin = {
    // AI API 키 다계정 관리 상태
    aiKeysLoading: false,
    aiKeys: [],
    showKeyModal: false,
    editingKey: null,
    keyForm: {
        provider: '',
        label: '',
        api_key: '',
        priority: 0
    },
    showKeyFormKey: false,
    savingKey: false,

    /**
     * AI API 키 목록 로드
     */
    async loadAiKeys() {
        this.aiKeysLoading = true;
        try {
            const response = await fetch(`${SETTINGS_API_BASE}/ai-keys`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                this.aiKeys = data.keys || [];
            } else {
                console.error('AI 키 목록 로드 실패:', response.status);
            }
        } catch (error) {
            console.error('AI 키 목록 로드 에러:', error);
        } finally {
            this.aiKeysLoading = false;
        }
    },

    /**
     * 제공자별 키 목록 가져오기
     */
    getKeysByProvider(provider) {
        return this.aiKeys
            .filter(key => key.provider === provider)
            .sort((a, b) => a.priority - b.priority);
    },

    /**
     * 상태 텍스트 변환
     */
    getStatusText(status) {
        const statusMap = {
            'active': '활성',
            'rate_limited': '제한됨',
            'error': '오류',
            'disabled': '비활성'
        };
        return statusMap[status] || status;
    },

    /**
     * 키 추가 모달 열기
     */
    openAddKeyModal(provider) {
        this.editingKey = null;
        this.keyForm = {
            provider: provider,
            label: '',
            api_key: '',
            priority: this.getKeysByProvider(provider).length
        };
        this.showKeyFormKey = false;
        this.showKeyModal = true;
    },

    /**
     * 키 수정
     */
    editKey(key) {
        this.editingKey = key;
        this.keyForm = {
            provider: key.provider,
            label: key.label,
            api_key: '',
            priority: key.priority
        };
        this.showKeyFormKey = false;
        this.showKeyModal = true;
    },

    /**
     * 키 모달 닫기
     */
    closeKeyModal() {
        this.showKeyModal = false;
        this.editingKey = null;
        this.keyForm = {
            provider: '',
            label: '',
            api_key: '',
            priority: 0
        };
    },

    /**
     * 키 저장 (추가/수정)
     */
    async saveKey() {
        this.savingKey = true;
        try {
            const url = this.editingKey
                ? `${SETTINGS_API_BASE}/ai-keys/${this.editingKey.id}`
                : `${SETTINGS_API_BASE}/ai-keys`;
            const method = this.editingKey ? 'PUT' : 'POST';

            const payload = {
                provider: this.keyForm.provider,
                label: this.keyForm.label,
                priority: parseInt(this.keyForm.priority)
            };

            if (this.keyForm.api_key && this.keyForm.api_key.trim()) {
                payload.api_key = this.keyForm.api_key.trim();
            }

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                showSuccessMessage(this.editingKey ? 'API 키가 수정되었습니다' : 'API 키가 추가되었습니다');
                this.closeKeyModal();
                await this.loadAiKeys();
            } else {
                const error = await response.json();
                showErrorMessage(error.detail || '저장에 실패했습니다');
            }
        } catch (error) {
            console.error('키 저장 에러:', error);
            showErrorMessage('저장에 실패했습니다');
        } finally {
            this.savingKey = false;
        }
    },

    /**
     * 키 삭제
     */
    async deleteKey(key) {
        if (!confirm(`"${key.label}" 키를 삭제하시겠습니까?`)) {
            return;
        }

        try {
            const response = await fetch(`${SETTINGS_API_BASE}/ai-keys/${key.id}`, {
                method: 'DELETE',
                credentials: 'include'
            });

            if (response.ok) {
                showSuccessMessage('API 키가 삭제되었습니다');
                await this.loadAiKeys();
            } else {
                const error = await response.json();
                showErrorMessage(error.detail || '삭제에 실패했습니다');
            }
        } catch (error) {
            console.error('키 삭제 에러:', error);
            showErrorMessage('삭제에 실패했습니다');
        }
    }
};

// 전역으로 내보내기
window.aiKeysMixin = aiKeysMixin;
