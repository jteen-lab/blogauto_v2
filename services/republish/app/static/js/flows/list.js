/**
 * 플로우 목록 페이지 JavaScript
 * Alpine.js 기반 상태 관리 및 API 통신
 */

function flowListApp() {
    return {
        // 상태 데이터
        loading: false,
        flows: [],
        modules: [],
        blogs: [],

        // 메시지 상태
        message: '',
        messageType: 'info',

        // 선택 상태
        selectedFlowId: null,
        selectedAddType: null,
        selectedItems: [],
        availableItems: [],

        // 초기화
        async init() {
            this.loading = true;
            try {
                await Promise.all([
                    this.loadFlows(),
                    this.loadModules(),
                    this.loadBlogs()
                ]);
            } catch (error) {
                this.showError('데이터를 불러오는 중 오류가 발생했습니다');
                console.error('초기화 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 플로우 목록 로드
        async loadFlows() {
            const response = await fetch('/api/v1/flows', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('플로우 목록 조회 실패');
            }

            const data = await response.json();
            this.flows = data.flows || [];
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
        },

        // 블로그 목록 로드
        async loadBlogs() {
            const response = await fetch('/api/v1/blogs', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('블로그 목록 조회 실패');
            }

            const data = await response.json();
            this.blogs = data.blogs || [];
        },

        // 플로우 생성 폼 표시
        showFlowForm(flowId = null) {
            // 폼 제목 설정
            const titleElement = document.getElementById('flowFormTitle');
            if (titleElement) {
                titleElement.textContent = flowId ? '플로우 수정' : '플로우 생성';
            }

            // 하단 시트 표시
            showBottomSheet('flowForm');

            // 폼 데이터 초기화
            if (window.flowFormApp && flowId) {
                window.flowFormApp.loadFlowData(flowId);
            }
        },

        // 플로우 편집
        editFlow(flowId) {
            this.showFlowForm(flowId);
        },

        // 플로우 복사
        async copyFlow(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            const copyName = `${flow.name} 사본`;

            try {
                const response = await fetch('/api/v1/flows', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        name: copyName,
                        description: flow.description ? `${flow.description} (복사됨)` : '복사된 플로우',
                        is_active: false
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 복사 실패');
                }

                // 목록 새로고침
                await this.loadFlows();
                this.showSuccess('플로우가 복사되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 복사 오류:', error);
            }
        },

        // 플로우 삭제
        async deleteFlow(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            if (!confirm(`'${flow.name}' 플로우를 정말 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 삭제 실패');
                }

                // 목록에서 제거
                this.flows = this.flows.filter(f => f.id !== flowId);
                this.showSuccess('플로우가 삭제되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 삭제 오류:', error);
            }
        },

        // 플로우 활성화/비활성화 토글
        async toggleFlowStatus(flowId) {
            const flow = this.flows.find(f => f.id === flowId);
            if (!flow) return;

            const newStatus = !flow.is_active;
            const action = newStatus ? '시작' : '중지';

            if (!confirm(`'${flow.name}' 플로우를 ${action}하시겠습니까?`)) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        is_active: newStatus
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '플로우 상태 변경 실패');
                }

                // 상태 업데이트
                flow.is_active = newStatus;
                this.showSuccess(`플로우가 ${action}되었습니다`);

            } catch (error) {
                this.showError(error.message);
                console.error('플로우 상태 변경 오류:', error);
            }
        },

        // 추가 선택기 표시
        showAddSelector(flowId) {
            this.selectedFlowId = flowId;
            showSelectionPopup('addSelector');
        },

        // 추가 타입 선택
        selectAddType(type) {
            this.selectedAddType = type;
            closeSelectionPopup('addSelector');

            // 아이템 선택기 표시
            this.showItemSelector();
        },

        // 아이템 선택기 표시
        showItemSelector() {
            const titleElement = document.getElementById('itemSelectorTitle');
            const contentElement = document.getElementById('itemSelectorContent');

            if (this.selectedAddType === 'module') {
                titleElement.textContent = '모듈 선택';
                this.availableItems = this.getAvailableModules();
                contentElement.innerHTML = this.renderModuleSelector();
            } else if (this.selectedAddType === 'blog') {
                titleElement.textContent = '블로그 선택';
                this.availableItems = this.getAvailableBlogs();
                contentElement.innerHTML = this.renderBlogSelector();
            }

            this.selectedItems = [];
            this.updateAddButtonText();

            showBottomSheet('itemSelector');
        },

        // 사용 가능한 모듈 목록 (현재 플로우에 포함되지 않은 것들)
        getAvailableModules() {
            const flow = this.flows.find(f => f.id === this.selectedFlowId);
            if (!flow) return this.modules;

            const usedModuleIds = this.getFlowModules(flow).map(fm => fm.module.id);
            return this.modules.filter(m => !usedModuleIds.includes(m.id));
        },

        // 사용 가능한 블로그 목록 (현재 플로우에 포함되지 않은 것들)
        getAvailableBlogs() {
            const flow = this.flows.find(f => f.id === this.selectedFlowId);
            if (!flow) return this.blogs;

            const usedBlogIds = this.getFlowBlogs(flow).map(fb => fb.blog.id);
            return this.blogs.filter(b => !usedBlogIds.includes(b.id));
        },

        // 모듈 선택기 렌더링
        renderModuleSelector() {
            return this.availableItems.map(module => `
                <label class="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input type="checkbox"
                           value="${module.id}"
                           onchange="window.flowListApp?.toggleItemSelection(${module.id})"
                           class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2">
                    <div class="flex items-center gap-2 flex-1">
                        <span class="text-lg">${this.getModuleIcon(module.module_type.code)}</span>
                        <div>
                            <span class="text-sm font-medium text-gray-900">${module.name}</span>
                            <span class="text-xs text-gray-500 ml-2">${this.getModuleTypeLabel(module.module_type.code)}</span>
                        </div>
                    </div>
                </label>
            `).join('') || '<div class="text-center py-8 text-gray-500">추가할 수 있는 모듈이 없습니다</div>';
        },

        // 블로그 선택기 렌더링
        renderBlogSelector() {
            return this.availableItems.map(blog => `
                <label class="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input type="checkbox"
                           value="${blog.id}"
                           onchange="window.flowListApp?.toggleItemSelection(${blog.id})"
                           class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2">
                    <div class="flex items-center gap-2 flex-1">
                        <span class="text-lg">${this.getBlogIcon(blog.platform)}</span>
                        <div>
                            <span class="text-sm font-medium text-gray-900">${blog.name}</span>
                            <span class="text-xs text-gray-500 ml-2">${this.getBlogPlatformLabel(blog.platform)}</span>
                        </div>
                    </div>
                </label>
            `).join('') || '<div class="text-center py-8 text-gray-500">추가할 수 있는 블로그가 없습니다</div>';
        },

        // 아이템 선택 토글
        toggleItemSelection(itemId) {
            const index = this.selectedItems.indexOf(itemId);
            if (index === -1) {
                this.selectedItems.push(itemId);
            } else {
                this.selectedItems.splice(index, 1);
            }
            this.updateAddButtonText();
        },

        // 추가 버튼 텍스트 업데이트
        updateAddButtonText() {
            const buttonTextElement = document.getElementById('addButtonText');
            const addButton = document.getElementById('addSelectedItems');

            if (buttonTextElement) {
                buttonTextElement.textContent = `추가 (${this.selectedItems.length})`;
            }

            if (addButton) {
                addButton.disabled = this.selectedItems.length === 0;
            }
        },

        // 선택된 아이템들 추가
        async addSelectedItems() {
            if (this.selectedItems.length === 0) return;

            try {
                const endpoint = this.selectedAddType === 'module' ? 'modules' : 'blogs';
                const response = await fetch(`/api/v1/flows/${this.selectedFlowId}/${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        item_ids: this.selectedItems
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '아이템 추가 실패');
                }

                const result = await response.json();

                // 플로우 데이터 새로고침
                await this.loadFlows();

                // 결과 표시
                if (result.failed_items && result.failed_items.length > 0) {
                    this.showAddResult(result);
                } else {
                    const itemTypeName = this.selectedAddType === 'module' ? '모듈' : '블로그';
                    this.showSuccess(`${this.selectedItems.length}개 ${itemTypeName}이 추가되었습니다`);
                }

                closeBottomSheet('itemSelector');

            } catch (error) {
                this.showError(error.message);
                console.error('아이템 추가 오류:', error);
            }
        },

        // 추가 결과 표시 (성공/실패 혼합)
        showAddResult(result) {
            const successCount = result.success_count || 0;
            const failedItems = result.failed_items || [];

            let message = '';
            if (successCount > 0) {
                message += `✅ 성공: ${successCount}개\n`;
            }
            if (failedItems.length > 0) {
                message += `❌ 실패: ${failedItems.length}개\n`;
                failedItems.forEach(item => {
                    message += `  - ${item.name}: ${item.reason}\n`;
                });
            }

            alert(message);
        },

        // 플로우에서 모듈 제거
        async removeModuleFromFlow(flowId, flowModuleId) {
            if (!confirm('이 모듈을 플로우에서 제거하시겠습니까?')) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}/modules/${flowModuleId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '모듈 제거 실패');
                }

                // 플로우 데이터 새로고침
                await this.loadFlows();
                this.showSuccess('모듈이 제거되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('모듈 제거 오류:', error);
            }
        },

        // 플로우에서 블로그 제거
        async removeBlogFromFlow(flowId, flowBlogId) {
            if (!confirm('이 블로그를 플로우에서 제거하시겠습니까?')) {
                return;
            }

            try {
                const response = await fetch(`/api/v1/flows/${flowId}/blogs/${flowBlogId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '블로그 제거 실패');
                }

                // 플로우 데이터 새로고침
                await this.loadFlows();
                this.showSuccess('블로그가 제거되었습니다');

            } catch (error) {
                this.showError(error.message);
                console.error('블로그 제거 오류:', error);
            }
        },

        // 플로우의 모듈 목록 반환
        getFlowModules(flow) {
            return flow.module_links || flow.flow_modules || [];
        },

        // 플로우의 블로그 목록 반환
        getFlowBlogs(flow) {
            return flow.blog_links || flow.flow_blogs || [];
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

        // 모듈 타입 레이블 반환
        getModuleTypeLabel(typeCode) {
            const labels = {
                republish: '재발행',
                publish: '발행',
                generate: '생성',
                prompt: '프롬프트'
            };
            return labels[typeCode] || typeCode;
        },

        // 블로그 아이콘 반환
        getBlogIcon(platform) {
            const icons = {
                blogger: '📙',
                wordpress: '🌐'
            };
            return icons[platform] || '📝';
        },

        // 블로그 플랫폼 레이블 반환
        getBlogPlatformLabel(platform) {
            const labels = {
                blogger: 'Blogger',
                wordpress: 'WordPress'
            };
            return labels[platform] || platform;
        },

        // 성공 메시지 표시
        showSuccess(message) {
            this.showMessage('success', message);
        },

        // 오류 메시지 표시
        showError(message) {
            this.showMessage('error', message);
        },

        // 메시지 표시 (토스트)
        showMessage(type, text) {
            // 이미 메시지가 있다면 제거
            const existingToast = document.querySelector('.message-toast');
            if (existingToast) {
                existingToast.remove();
            }

            // 새 토스트 생성
            const toast = document.createElement('div');
            toast.className = 'message-toast fixed top-4 right-4 z-60 max-w-sm';

            const bgColor = type === 'success' ? 'bg-green-50' : type === 'error' ? 'bg-red-50' : 'bg-blue-50';
            const borderColor = type === 'success' ? 'border-green-400' : type === 'error' ? 'border-red-400' : 'border-blue-400';
            const textColor = type === 'success' ? 'text-green-800' : type === 'error' ? 'text-red-800' : 'text-blue-800';
            const iconColor = type === 'success' ? 'text-green-400' : type === 'error' ? 'text-red-400' : 'text-blue-400';

            const icon = type === 'success' ?
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>' :
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>';

            toast.innerHTML = `
                <div class="bg-white rounded-lg shadow-lg border-l-4 ${borderColor} ${bgColor} p-4">
                    <div class="flex items-start">
                        <div class="flex-shrink-0">
                            <svg class="w-5 h-5 ${iconColor}" fill="currentColor" viewBox="0 0 20 20">
                                ${icon}
                            </svg>
                        </div>
                        <div class="ml-3 flex-1">
                            <p class="text-sm font-medium ${textColor}">${text}</p>
                        </div>
                        <button onclick="this.closest('.message-toast').remove()" class="ml-4 text-gray-400 hover:text-gray-600">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(toast);

            // 자동 제거 (성공 메시지만)
            if (type === 'success') {
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.remove();
                    }
                }, 3000);
            }
        }
    };
}

function flowCardState() {
    return {
        expanded: false,
        needsExpand: false,
        initCard(el) {
            setTimeout(() => {
                const content = el.querySelector('.flow-content-area');
                if (content) {
                    this.needsExpand = content.scrollHeight > 128;
                }
            }, 150);
        }
    };
}

// 전역 참조 설정
document.addEventListener('DOMContentLoaded', function() {
    const flowList = document.querySelector('[x-data*="flowListApp"]');
    if (flowList) {
        window.flowListApp = flowList._x_dataStack[0];
    }
});

// 추가 타입 선택 (전역 함수)
function selectAddType(type) {
    if (window.flowListApp) {
        window.flowListApp.selectAddType(type);
    }
}

// 선택된 아이템 추가 (전역 함수)
function addSelectedItems() {
    if (window.flowListApp) {
        window.flowListApp.addSelectedItems();
    }
}