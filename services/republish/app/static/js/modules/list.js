/**
 * 모듈 목록 페이지 JavaScript
 * Alpine.js 기반 상태 관리 및 API 통신
 */

function moduleListApp() {
    return {
        // 상태 데이터
        loading: false,
        modules: [],
        moduleTypes: [],

        // 초기화
        async init() {
            this.loading = true;
            try {
                await Promise.all([
                    this.loadModuleTypes(),
                    this.loadModules()
                ]);
            } catch (error) {
                this.showError('데이터를 불러오는 중 오류가 발생했습니다');
                console.error('초기화 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 모듈 타입 목록 로드
        async loadModuleTypes() {
            const response = await fetch('/api/v1/module-types', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('모듈 타입 목록 조회 실패');
            }

            this.moduleTypes = await response.json();
        },

        // 모듈 목록 로드
        async loadModules() {
            const response = await fetch('/api/v1/modules', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('모듈 목록 조회 실패');
            }

            const data = await response.json();
            this.modules = data.modules || [];

            // 로딩 완료 후 동적 레이아웃 적용
            setTimeout(() => {
                this.applyDynamicLayout();
            }, 100);
        },

        // 타입별 모듈 목록 반환
        getModulesByType(typeCode) {
            return this.modules.filter(module => module.module_type.code === typeCode);
        },

        // 타입별 모듈 개수 계산
        getModuleCountByType(typeCode) {
            return this.modules.filter(module => module.module_type.code === typeCode).length;
        },

        // 동적 섹션 레이아웃 적용
        applyDynamicLayout() {
            const moduleTypes = ['prompt', 'generate', 'publish', 'republish'];
            const visibleSections = moduleTypes.filter(type => this.getModulesByType(type).length > 0);
            const sectionCount = visibleSections.length;

            console.log(`[applyDynamicLayout] 표시할 섹션 수: ${sectionCount}`);

            // 데스크탑 섹션 컨테이너 찾기
            const desktopSections = document.querySelector('.desktop-sections');
            if (!desktopSections) return;

            // 기존 클래스 제거
            desktopSections.classList.remove('sections-1', 'sections-2', 'sections-3', 'sections-4');

            // 섹션 수에 따른 클래스 추가
            desktopSections.classList.add(`sections-${sectionCount}`);

            // 각 섹션의 모듈 그리드에도 클래스 적용
            visibleSections.forEach(type => {
                const moduleGrid = document.querySelector(`[x-show*="getModulesByType('${type}')"] .module-grid`);
                if (moduleGrid) {
                    moduleGrid.classList.remove('grid-1', 'grid-2', 'grid-3', 'grid-4');
                    moduleGrid.classList.add(`grid-${sectionCount}`);
                }
            });
        },

        // 모듈 아이콘 반환
        getModuleIcon(typeCode) {
            const icons = {
                republish: '🔄',
                publish: '📤',
                generate: '✨',
                prompt: '📝'
            };
            return icons[typeCode] || '📦';
        },

        // 모듈 타입 이름 반환
        getModuleTypeName(typeCode) {
            const type = this.moduleTypes.find(t => t.code === typeCode);
            if (type) return type.name;

            // 폴백 이름
            const fallbackNames = {
                'prompt': '프롬프트',
                'generate': '생성',
                'publish': '발행',
                'republish': '재발행'
            };
            return fallbackNames[typeCode] || typeCode;
        },


        // 전체 폼 템플릿
        getFullFormTemplate() {
            return `
                <form @submit.prevent="submitForm()">
                    <!-- 기본 정보 -->
                    <div class="space-y-6">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                모듈 이름 <span class="text-red-500">*</span>
                            </label>
                            <input type="text"
                                   x-model="formData.name"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                   placeholder="예: 재발행 모듈 A"
                                   required>
                            <p class="mt-1 text-xs text-gray-500">모듈을 구분할 수 있는 이름을 입력하세요</p>
                        </div>

                        <!-- 재발행 모듈 전용 설정 -->
                        <div x-show="formData.type_code === 'republish'">
                            <!-- 재발행 간격 설정 -->
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">
                                    재발행 간격 (분) <span class="text-red-500">*</span>
                                </label>
                                <input type="number"
                                       x-model.number="formData.manual_interval_minutes"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                       min="15"
                                       placeholder="25"
                                       required>
                                <div class="mt-1 flex items-center gap-2 text-xs text-blue-600">
                                    <span>최소 15분 이상 설정해주세요. 권장: 25-60분</span>
                                </div>
                            </div>
                        </div>

                        <!-- 다른 모듈 타입 -->
                        <div x-show="formData.type_code !== 'republish'">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">설정 정보 (JSON)</label>
                                <textarea x-model="settingsJson"
                                          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                                          rows="4"
                                          placeholder='{"key": "value"}'>
                                </textarea>
                                <p class="mt-1 text-xs text-gray-500">모듈별 설정을 JSON 형태로 입력하세요</p>
                            </div>
                        </div>

                        <!-- 설명 -->
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">설명 (선택)</label>
                            <textarea x-model="formData.description"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                      rows="3"
                                      placeholder="모듈에 대한 설명을 입력하세요...">
                            </textarea>
                        </div>

                        <!-- 활성화 상태 -->
                        <div class="flex items-center justify-between">
                            <div>
                                <span class="text-sm font-medium text-gray-700">모듈 활성화</span>
                                <p class="text-xs text-gray-500">생성 후 바로 동작하려면 활성화하세요</p>
                            </div>
                            <button type="button"
                                    @click="formData.is_active = !formData.is_active"
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                                    :class="formData.is_active ? 'bg-blue-600' : 'bg-gray-200'">
                                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                                      :class="formData.is_active ? 'translate-x-5' : 'translate-x-0'">
                                </span>
                            </button>
                        </div>
                    </div>

                    <!-- 폼 액션 -->
                    <div class="flex gap-3 pt-6 border-t border-gray-200 mt-8">
                        <button type="button"
                                @click="closeForm()"
                                class="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500">
                            취소
                        </button>
                        <button type="submit"
                                :disabled="loading"
                                class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed">
                            <span x-show="!loading">
                                <span x-text="isEdit ? '수정' : '생성'"></span>
                            </span>
                            <span x-show="loading" class="flex items-center justify-center">
                                <svg class="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                처리중...
                            </span>
                        </button>
                    </div>
                </form>
            `;
        },

        // 상태별 CSS 클래스 반환
        getStatusClass(isActive) {
            return isActive
                ? 'bg-green-100 text-green-800 border-green-200'
                : 'bg-gray-100 text-gray-600 border-gray-200';
        },

        // 스케줄 여부 확인
        hasSchedule(module) {
            return module.schedule_matrix &&
                   JSON.stringify(module.schedule_matrix) !== JSON.stringify(this.getEmptySchedule());
        },

        // 빈 스케줄 생성
        getEmptySchedule() {
            return Array(7).fill().map(() => Array(24).fill(false));
        },

        // 시간 경과 포맷
        formatTimeAgo(timestamp) {
            if (!timestamp) return '';

            const now = new Date();
            const time = new Date(timestamp);
            const diffInMs = now - time;
            const diffInMins = Math.floor(diffInMs / 60000);
            const diffInHours = Math.floor(diffInMins / 60);
            const diffInDays = Math.floor(diffInHours / 24);

            if (diffInDays > 0) {
                return `${diffInDays}일 전`;
            } else if (diffInHours > 0) {
                return `${diffInHours}시간 전`;
            } else if (diffInMins > 0) {
                return `${diffInMins}분 전`;
            } else {
                return '방금 전';
            }
        },

        // 모듈 타입 선택 팝업 표시
        async showModuleTypeSelector() {
            try {
                console.log('모듈 타입 선택 팝업 열기 시도...');
                // 팝업 표시 (옵션은 템플릿에 하드코딩되어 있음)
                if (typeof window.openSelectionPopup === 'function') {
                    window.openSelectionPopup('moduleTypeSelector');
                    console.log('모듈 타입 선택 팝업 열기 완료');
                } else {
                    console.error('openSelectionPopup 함수가 정의되지 않았습니다');
                    this.showError('모듈 타입 선택 팝업을 열 수 없습니다. 페이지를 새로고침해주세요.');
                }
            } catch (error) {
                console.error('모듈 타입 선택 팝업 오류:', error);
                this.showError('모듈 타입 선택 팝업을 열 수 없습니다.');
            }
        },

        // 모듈 생성
        async createModule(typeCode) {
            try {
                console.log(`모듈 생성 시작: ${typeCode}`);

                const selectedType = this.moduleTypes.find(t => t.code === typeCode) || {
                    code: typeCode,
                    name: this.getModuleTypeName(typeCode),
                    description: ''
                };

                console.log('선택된 모듈 타입:', selectedType);

                // 바텀시트 제목 업데이트
                const title = document.getElementById('moduleFormTitle');
                if (title) {
                    title.textContent = `${selectedType.name} 생성`;
                } else {
                    console.warn('모듈 폼 제목 엘리먼트를 찾을 수 없습니다');
                }

                // 폼 내용 로드
                console.log('폼 내용 로드 시작...');
                const formContent = await this.loadModuleForm(null, selectedType);
                const contentArea = document.getElementById('moduleFormContent');
                if (contentArea) {
                    contentArea.innerHTML = formContent;
                    console.log('폼 내용 로드 완료');

                    // Alpine.js 다시 초기화 (동적 컨텐츠를 위해)
                    setTimeout(() => {
                        if (typeof Alpine !== 'undefined') {
                            console.log('Alpine.js 객체:', Alpine);
                            if (Alpine.initTree) {
                                Alpine.initTree(contentArea);
                                console.log('Alpine.js initTree 완료');
                            } else if (Alpine.start) {
                                // Alpine.js v3에서는 start() 메소드 사용
                                console.log('Alpine.js 다시 시작 시도...');
                            } else {
                                console.log('Alpine.js 버전이 다름. 수동 초기화 필요');
                            }
                        } else {
                            console.warn('Alpine.js가 로드되지 않았습니다');
                        }
                    }, 50);
                } else {
                    console.warn('모듈 폼 컨텐츠 엘리먼트를 찾을 수 없습니다');
                }

                // 바텀시트 표시
                console.log('바텀시트 열기 시도...');
                if (typeof window.openBottomSheet === 'function') {
                    window.openBottomSheet('moduleForm');
                    console.log('바텀시트 열기 완료');
                } else {
                    console.error('openBottomSheet 함수가 정의되지 않았습니다');
                    this.showError('모듈 폼을 열 수 없습니다. 페이지를 새로고침해주세요.');
                }

            } catch (error) {
                console.error('모듈 생성 전체 오류:', error);
                this.showError('모듈 생성 폼을 불러오는 중 오류가 발생했습니다: ' + error.message);
            }
        },

        // 모듈 수정
        async editModule(moduleId) {
            try {
                const module = this.modules.find(m => m.id === moduleId);
                if (!module) {
                    this.showError('모듈을 찾을 수 없습니다');
                    return;
                }

                const moduleType = this.moduleTypes.find(t => t.code === module.module_type.code) || {
                    code: module.module_type.code,
                    name: this.getModuleTypeName(module.module_type.code),
                    description: ''
                };

                // 바텀시트 제목 업데이트
                const title = document.getElementById('moduleFormTitle');
                if (title) {
                    title.textContent = `${module.name} 수정`;
                }

                // 폼 내용 로드
                const formContent = await this.loadModuleForm(module, moduleType);
                const contentArea = document.getElementById('moduleFormContent');
                if (contentArea) {
                    contentArea.innerHTML = formContent;
                }

                // 바텀시트 표시
                openBottomSheet('moduleForm');

            } catch (error) {
                this.showError('모듈 수정 폼을 불러오는 중 오류가 발생했습니다');
                console.error('모듈 수정 오류:', error);
            }
        },

        // 모듈 복사
        async copyModule(moduleId) {
            if (!confirm('이 모듈을 복사하시겠습니까?')) return;

            try {
                const response = await fetch(`/api/v1/modules/${moduleId}/copy`, {
                    method: 'POST',
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('모듈 복사 실패');
                }

                this.showSuccess('모듈이 복사되었습니다');
                await this.loadModules();

            } catch (error) {
                this.showError('모듈 복사 중 오류가 발생했습니다');
                console.error('모듈 복사 오류:', error);
            }
        },

        // 모듈 삭제
        async deleteModule(moduleId) {
            const module = this.modules.find(m => m.id === moduleId);
            if (!module) return;

            if (!confirm(`'${module.name}' 모듈을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;

            try {
                const response = await fetch(`/api/v1/modules/${moduleId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error('모듈 삭제 실패');
                }

                this.showSuccess('모듈이 삭제되었습니다');

                // 리스트에서 제거
                this.modules = this.modules.filter(m => m.id !== moduleId);

                // 카드 애니메이션 제거
                const card = document.querySelector(`[data-module-id="${moduleId}"]`);
                if (card) {
                    card.style.transition = 'all 0.3s ease-out';
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';

                    setTimeout(() => {
                        if (card.parentNode) {
                            card.parentNode.removeChild(card);
                        }
                    }, 300);
                }

            } catch (error) {
                this.showError('모듈 삭제 중 오류가 발생했습니다');
                console.error('모듈 삭제 오류:', error);
            }
        },


        // 모듈 폼 로드 (HTML 템플릿)
        async loadModuleForm(module, moduleType) {
            // 기본 폼 HTML 반환
            return this.getDefaultFormHTML(module, moduleType);
        },


        // 기본 폼 HTML 생성
        getDefaultFormHTML(module, moduleType) {
            // 전역 변수를 통한 데이터 전달 (더 안전한 방법)
            const moduleId = 'moduleData_' + Date.now();
            const typeId = 'typeData_' + Date.now();

            // 전역 변수에 데이터 저장
            window[moduleId] = module;
            window[typeId] = moduleType;

            return `
                <div x-data="moduleFormApp(window.${moduleId}, window.${typeId})" x-init="init(); delete window.${moduleId}; delete window.${typeId};">
                    ${this.getFullFormTemplate()}
                </div>
            `;
        },

        // 알림 메시지 표시
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

// 선택 팝업 이벤트 리스너
document.addEventListener('selectionPopup:select', async (e) => {
    if (e.detail.popupId === 'moduleTypeSelector') {
        const app = window.moduleListAppInstance;
        if (app) {
            await app.createModule(e.detail.action);
        }
    }
});

// 팝업 관련 함수들 (selection_popup 컴포넌트와 호환)
window.openSelectionPopup = function(popupId) {
    const popup = document.getElementById(popupId);
    const backdrop = document.getElementById(popupId + '-backdrop');

    if (!popup) return;

    // 백드롭과 팝업 표시
    if (backdrop) {
        backdrop.classList.remove('hidden');
        setTimeout(() => {
            backdrop.style.opacity = '1';
        }, 10);
    }

    popup.classList.remove('hidden');

    // 팝업 애니메이션
    const content = popup.querySelector('div > div');
    if (content) {
        setTimeout(() => {
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }, 10);
    }

    // 스크롤 방지
    document.body.style.overflow = 'hidden';
};

window.closeSelectionPopup = function(popupId) {
    const popup = document.getElementById(popupId);
    const backdrop = document.getElementById(popupId + '-backdrop');
    const content = popup ? popup.querySelector('div > div') : null;

    // 팝업 애니메이션
    if (content) {
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
    }

    // 백드롭 숨기기
    if (backdrop) {
        backdrop.style.opacity = '0';
    }

    setTimeout(() => {
        if (popup) popup.classList.add('hidden');
        if (backdrop) backdrop.classList.add('hidden');
    }, 200);

    // 스크롤 복원
    document.body.style.overflow = '';
};

window.selectOption = function(popupId, action, text) {
    // 커스텀 이벤트 발생
    const event = new CustomEvent('selectionPopup:select', {
        detail: {
            popupId: popupId,
            action: action,
            text: text
        }
    });
    document.dispatchEvent(event);

    // 팝업 닫기
    closeSelectionPopup(popupId);
};

// 전역 인스턴스 저장
document.addEventListener('DOMContentLoaded', () => {
    // Alpine.js가 초기화된 후에 인스턴스를 저장
    setTimeout(() => {
        const container = document.querySelector('[x-data*="moduleListApp"]');
        if (container && container._x_dataStack) {
            window.moduleListAppInstance = container._x_dataStack[0];
        }
    }, 100);
});

// 유틸리티 함수들
window.editModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.editModule(moduleId);
    }
};

window.copyModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.copyModule(moduleId);
    }
};

window.deleteModule = function(moduleId) {
    if (window.moduleListAppInstance) {
        window.moduleListAppInstance.deleteModule(moduleId);
    }
};


// 바텀시트 관련 함수들 (모듈 로드 전에 정의)
if (typeof window.openBottomSheet === 'undefined') {
    window.openBottomSheet = function(sheetId) {
        const sheet = document.getElementById(sheetId);
        const backdrop = document.getElementById(sheetId + '-backdrop');

        if (!sheet) {
            console.warn(`Bottom sheet '${sheetId}' not found`);
            return;
        }

        // 백드롭 표시
        if (backdrop) {
            backdrop.classList.remove('hidden');
            setTimeout(() => {
                backdrop.style.opacity = '1';
            }, 10);
        }

        // 시트 표시
        sheet.classList.remove('translate-y-full');

        // 스크롤 방지
        document.body.style.overflow = 'hidden';
    };
}

if (typeof window.closeBottomSheet === 'undefined') {
    window.closeBottomSheet = function(sheetId) {
        const sheet = document.getElementById(sheetId);
        const backdrop = document.getElementById(sheetId + '-backdrop');

        // 시트 숨기기
        if (sheet) {
            sheet.classList.add('translate-y-full');
        }

        // 백드롭 숨기기
        if (backdrop) {
            backdrop.style.opacity = '0';
            setTimeout(() => {
                backdrop.classList.add('hidden');
            }, 300);
        }

        // 스크롤 복원
        document.body.style.overflow = '';
    };
}

// ESC 키로 팝업 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (typeof closeSelectionPopup !== 'undefined') {
            closeSelectionPopup('moduleTypeSelector');
        }
        if (typeof closeBottomSheet !== 'undefined') {
            closeBottomSheet('moduleForm');
        }
    }
});