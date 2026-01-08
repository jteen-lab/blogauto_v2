/**
 * 오토런 페이지 JavaScript
 * Alpine.js 기반 상태 관리 및 API 통신
 */

function autorunApp() {
    return {
        // 상태 데이터
        loading: false,
        autorunFlows: [],
        availableFlows: [],

        // 선택 상태
        selectedIds: [],
        addSelectedIds: [],

        // 계산된 속성
        get activeCount() {
            return this.autorunFlows.filter(f => f.status === 'active').length;
        },

        get pausedCount() {
            return this.autorunFlows.filter(f => f.status === 'paused').length;
        },

        get isAllSelected() {
            return this.autorunFlows.length > 0 &&
                   this.selectedIds.length === this.autorunFlows.length;
        },

        get hasActiveSelected() {
            return this.selectedIds.some(id =>
                this.autorunFlows.find(f => f.id === id)?.status === 'active'
            );
        },

        get hasPausedSelected() {
            return this.selectedIds.some(id =>
                this.autorunFlows.find(f => f.id === id)?.status === 'paused'
            );
        },

        // 초기화
        async init() {
            this.loading = true;
            try {
                await this.loadAutorunFlows();
            } catch (error) {
                showErrorMessage('데이터를 불러오는 중 오류가 발생했습니다');
                console.error('초기화 오류:', error);
            } finally {
                this.loading = false;
            }
        },

        // 오토런 플로우 목록 로드
        async loadAutorunFlows() {
            const response = await fetch('/api/v1/autorun', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('오토런 플로우 조회 실패');
            }

            const data = await response.json();

            // 활성 + 일시정지 플로우 합치기
            this.autorunFlows = [
                ...(data.active_flows || []),
                ...(data.paused_flows || [])
            ];
        },

        // 선택 관련 메서드
        isSelected(id) {
            return this.selectedIds.includes(id);
        },

        toggleSelect(id) {
            const index = this.selectedIds.indexOf(id);
            if (index === -1) {
                this.selectedIds.push(id);
            } else {
                this.selectedIds.splice(index, 1);
            }
        },

        selectAll() {
            if (this.isAllSelected) {
                this.selectedIds = [];
            } else {
                this.selectedIds = this.autorunFlows.map(f => f.id);
            }
        },

        // 개별 플로우 액션
        async pauseFlow(flowId) {
            try {
                const response = await fetch(`/api/v1/autorun/flows/${flowId}/pause`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ action: 'pause' })
                });

                if (!response.ok) {
                    throw new Error('일시정지 실패');
                }

                showSuccessMessage('플로우가 일시정지되었습니다');
                await this.loadAutorunFlows();
            } catch (error) {
                showErrorMessage('일시정지 중 오류가 발생했습니다');
                console.error('일시정지 오류:', error);
            }
        },

        async resumeFlow(flowId) {
            try {
                const response = await fetch(`/api/v1/autorun/flows/${flowId}/resume`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ action: 'resume' })
                });

                if (!response.ok) {
                    throw new Error('재개 실패');
                }

                showSuccessMessage('플로우가 재개되었습니다');
                await this.loadAutorunFlows();
            } catch (error) {
                showErrorMessage('재개 중 오류가 발생했습니다');
                console.error('재개 오류:', error);
            }
        },

        async removeFlow(flowId) {
            const flow = this.autorunFlows.find(f => f.id === flowId);
            if (!flow) return;

            showConfirmDialog(
                '플로우 제외',
                '선택한 플로우를 오토런에서 제외하시겠습니까?',
                [flow.name],
                '제외 시 예약된 스케줄이 해제됩니다.',
                async () => {
                    try {
                        const response = await fetch(`/api/v1/autorun/flows/${flowId}`, {
                            method: 'DELETE',
                            credentials: 'include'
                        });

                        if (!response.ok) {
                            throw new Error('제외 실패');
                        }

                        showSuccessMessage('플로우가 오토런에서 제외되었습니다');
                        await this.loadAutorunFlows();
                    } catch (error) {
                        showErrorMessage('제외 중 오류가 발생했습니다');
                        console.error('제외 오류:', error);
                    }
                }
            );
        },

        // 일괄 액션
        async bulkPause() {
            const activeIds = this.selectedIds.filter(id =>
                this.autorunFlows.find(f => f.id === id)?.status === 'active'
            );

            if (activeIds.length === 0) {
                showErrorMessage('일시정지할 활성 플로우가 없습니다');
                return;
            }

            try {
                const response = await fetch('/api/v1/autorun/bulk-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        flow_ids: activeIds,
                        action: 'pause'
                    })
                });

                if (!response.ok) {
                    throw new Error('일괄 일시정지 실패');
                }

                showSuccessMessage(`${activeIds.length}개 플로우가 일시정지되었습니다`);
                this.selectedIds = [];
                await this.loadAutorunFlows();
            } catch (error) {
                showErrorMessage('일괄 일시정지 중 오류가 발생했습니다');
                console.error('일괄 일시정지 오류:', error);
            }
        },

        async bulkResume() {
            const pausedIds = this.selectedIds.filter(id =>
                this.autorunFlows.find(f => f.id === id)?.status === 'paused'
            );

            if (pausedIds.length === 0) {
                showErrorMessage('재개할 일시정지 플로우가 없습니다');
                return;
            }

            try {
                const response = await fetch('/api/v1/autorun/bulk-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        flow_ids: pausedIds,
                        action: 'resume'
                    })
                });

                if (!response.ok) {
                    throw new Error('일괄 재개 실패');
                }

                showSuccessMessage(`${pausedIds.length}개 플로우가 재개되었습니다`);
                this.selectedIds = [];
                await this.loadAutorunFlows();
            } catch (error) {
                showErrorMessage('일괄 재개 중 오류가 발생했습니다');
                console.error('일괄 재개 오류:', error);
            }
        },

        bulkRemove() {
            if (this.selectedIds.length === 0) return;

            const names = this.selectedIds.map(id =>
                this.autorunFlows.find(f => f.id === id)?.name || ''
            ).filter(Boolean);

            showConfirmDialog(
                '플로우 제외',
                '선택한 플로우를 오토런에서 제외하시겠습니까?',
                names,
                '제외 시 예약된 스케줄이 해제됩니다.',
                async () => {
                    try {
                        // 각 플로우에 대해 DELETE 호출
                        let successCount = 0;
                        for (const flowId of this.selectedIds) {
                            const response = await fetch(`/api/v1/autorun/flows/${flowId}`, {
                                method: 'DELETE',
                                credentials: 'include'
                            });
                            if (response.ok) successCount++;
                        }

                        showSuccessMessage(`${successCount}개 플로우가 제외되었습니다`);
                        this.selectedIds = [];
                        await this.loadAutorunFlows();
                    } catch (error) {
                        showErrorMessage('일괄 제외 중 오류가 발생했습니다');
                        console.error('일괄 제외 오류:', error);
                    }
                }
            );
        },

        // 하단 시트 열기
        openAddSheet() {
            loadAvailableFlows();
            openBottomSheet('addSheet');
        },

        openLogSheet() {
            loadLogs();
            openBottomSheet('logSheet');
        }
    };
}

// 카드 상태 관리
function autorunCardState() {
    return {
        initCard(el) {
            // 슬라이드 초기화
        }
    };
}

// 시간 포맷팅
function formatTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

// 슬라이드 관련 헬퍼 함수들 (flows/list.js와 동일)
function getModuleIcon(code) {
    const icons = {
        'republish': '🔄',
        'generate': '🤖',
        'prompt': '📝',
        'publish': '📤'
    };
    return icons[code] || '📦';
}

function getModuleInfoItems(module) {
    if (!module) return [];
    const items = [];

    if (module.module_type?.name) {
        items.push({ label: '타입', value: module.module_type.name });
    }
    if (module.description) {
        items.push({ label: '설명', value: module.description });
    }

    return items;
}

function needsModuleSlide(module) {
    return getModuleInfoItems(module).length > 2;
}

function getModuleSlideDuration(module) {
    const itemCount = getModuleInfoItems(module).length;
    return Math.max(15, itemCount * 5);
}

function needsBlogSlide(blogCount) {
    return blogCount > 3;
}

function getBlogSlideDuration(blogCount) {
    return Math.max(15, blogCount * 3);
}

function initSlideCheck(el) {
    // 슬라이드 필요 여부 확인
}

function initBlogSlideCheck(el, count) {
    // 블로그 슬라이드 필요 여부 확인
}

function toggleSlideTouch(event, el) {
    // 터치로 슬라이드 일시정지 토글
}

// 하단 시트 관련
function openBottomSheet(id) {
    const backdrop = document.getElementById(`${id}-backdrop`);
    const sheet = document.getElementById(id);

    if (backdrop && sheet) {
        backdrop.classList.remove('hidden');
        setTimeout(() => {
            sheet.classList.remove('translate-y-full');
        }, 10);
    }
}

function closeBottomSheet(id) {
    const backdrop = document.getElementById(`${id}-backdrop`);
    const sheet = document.getElementById(id);

    if (sheet) {
        sheet.classList.add('translate-y-full');
    }
    if (backdrop) {
        setTimeout(() => {
            backdrop.classList.add('hidden');
        }, 300);
    }
}

// 추가 가능한 플로우 로드
async function loadAvailableFlows() {
    const content = document.getElementById('addSheetContent');
    content.innerHTML = '<div class="text-center text-gray-500 py-8">로딩 중...</div>';

    try {
        // 오토런에 추가되지 않은 플로우 조회 (새 API 사용)
        const response = await fetch('/api/v1/autorun/available', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('플로우 조회 실패');
        }

        const flows = await response.json();

        if (flows.length === 0) {
            content.innerHTML = `
                <div class="text-center text-gray-500 py-8">
                    <p>추가할 수 있는 플로우가 없습니다</p>
                    <p class="text-sm mt-2">플로우 관리에서 새 플로우를 만들어주세요</p>
                </div>
            `;
            return;
        }

        // 플로우 목록 렌더링
        content.innerHTML = flows.map(flow => `
            <div class="flex items-center gap-3 p-3 border border-gray-200 rounded-lg mb-2 hover:bg-gray-50">
                <input type="checkbox"
                       class="available-flow-checkbox w-4 h-4 rounded border-gray-300"
                       data-flow-id="${flow.id}"
                       onchange="updateAddButton()">
                <div class="flex-1">
                    <div class="font-medium text-gray-900">${flow.name}</div>
                    <div class="text-xs text-gray-500">
                        모듈 ${flow.module_count || 0}개 · 블로그 ${flow.blog_count || 0}개
                    </div>
                </div>
                <button onclick="addSingleFlow(${flow.id})"
                        class="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-lg">
                    + 추가
                </button>
            </div>
        `).join('');

        // 검색 기능 연결 (디바운스 적용)
        let searchTimeout = null;
        document.getElementById('searchAvailable').oninput = async function(e) {
            const query = e.target.value.trim();

            // 디바운스: 300ms 후 검색 실행
            if (searchTimeout) clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                if (query.length >= 2 || query.length === 0) {
                    await searchAvailableFlows(query);
                }
            }, 300);
        };

    } catch (error) {
        content.innerHTML = `<div class="text-center text-red-500 py-8">오류가 발생했습니다</div>`;
        console.error('플로우 로드 오류:', error);
    }
}

function updateAddButton() {
    const checkboxes = document.querySelectorAll('.available-flow-checkbox:checked');
    const button = document.getElementById('addSelectedFlows');
    const text = document.getElementById('addButtonText');

    button.disabled = checkboxes.length === 0;
    text.textContent = `추가 (${checkboxes.length})`;
}

async function addSelectedFlows() {
    const checkboxes = document.querySelectorAll('.available-flow-checkbox:checked');
    const flowIds = Array.from(checkboxes).map(cb => parseInt(cb.dataset.flowId));

    if (flowIds.length === 0) return;

    try {
        // 다중 추가 API 사용
        const response = await fetch('/api/v1/autorun/flows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(flowIds)
        });

        if (!response.ok) {
            throw new Error('플로우 추가 실패');
        }

        const result = await response.json();
        showSuccessMessage(result.message || `${flowIds.length}개 플로우가 추가되었습니다`);
        closeBottomSheet('addSheet');

        // Alpine.js 컴포넌트의 데이터 새로고침
        const app = document.querySelector('[x-data="autorunApp()"]');
        if (app && app.__x) {
            await app.__x.$data.loadAutorunFlows();
        } else {
            location.reload();
        }

    } catch (error) {
        showErrorMessage('플로우 추가 중 오류가 발생했습니다');
        console.error('플로우 추가 오류:', error);
    }
}

async function addSingleFlow(flowId) {
    try {
        // 단일 플로우도 다중 추가 API 사용
        const response = await fetch('/api/v1/autorun/flows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify([flowId])
        });

        if (!response.ok) {
            throw new Error('플로우 추가 실패');
        }

        showSuccessMessage('플로우가 추가되었습니다');
        closeBottomSheet('addSheet');

        // 새로고침
        const app = document.querySelector('[x-data="autorunApp()"]');
        if (app && app.__x) {
            await app.__x.$data.loadAutorunFlows();
        } else {
            location.reload();
        }

    } catch (error) {
        showErrorMessage('플로우 추가 중 오류가 발생했습니다');
        console.error('플로우 추가 오류:', error);
    }
}

// 검색 기능 (서버 API 사용)
async function searchAvailableFlows(query) {
    const content = document.getElementById('addSheetContent');

    try {
        const url = query
            ? `/api/v1/autorun/available?search=${encodeURIComponent(query)}`
            : '/api/v1/autorun/available';

        const response = await fetch(url, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('플로우 검색 실패');
        }

        const flows = await response.json();

        if (flows.length === 0) {
            content.innerHTML = `
                <div class="text-center text-gray-500 py-8">
                    ${query ? `"${query}"에 대한 검색 결과가 없습니다` : '추가할 수 있는 플로우가 없습니다'}
                </div>
            `;
            return;
        }

        // 플로우 목록 렌더링
        content.innerHTML = flows.map(flow => `
            <div class="flex items-center gap-3 p-3 border border-gray-200 rounded-lg mb-2 hover:bg-gray-50">
                <input type="checkbox"
                       class="available-flow-checkbox w-4 h-4 rounded border-gray-300"
                       data-flow-id="${flow.id}"
                       onchange="updateAddButton()">
                <div class="flex-1">
                    <div class="font-medium text-gray-900">${flow.name}</div>
                    <div class="text-xs text-gray-500">
                        모듈 ${flow.module_count || 0}개 · 블로그 ${flow.blog_count || 0}개
                    </div>
                </div>
                <button onclick="addSingleFlow(${flow.id})"
                        class="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-lg">
                    + 추가
                </button>
            </div>
        `).join('');

        updateAddButton();

    } catch (error) {
        console.error('플로우 검색 오류:', error);
    }
}

// 로그 관련
let logsData = { logs: [], total: 0, offset: 0 };

async function loadLogs(append = false) {
    const content = document.getElementById('logSheetContent');

    if (!append) {
        content.innerHTML = '<div class="text-center text-gray-500 py-8"><div class="loading mx-auto mb-2"></div>로딩 중...</div>';
        logsData.offset = 0;
    }

    try {
        const response = await fetch(`/api/v1/autorun/logs?limit=30&offset=${logsData.offset}`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('로그 조회 실패');
        }

        const data = await response.json();

        if (append) {
            logsData.logs = [...logsData.logs, ...data.logs];
        } else {
            logsData.logs = data.logs;
        }
        logsData.total = data.total;
        logsData.offset += data.logs.length;

        renderLogs();

    } catch (error) {
        content.innerHTML = `<div class="text-center text-red-500 py-8">로그를 불러오는 중 오류가 발생했습니다</div>`;
        console.error('로그 로드 오류:', error);
    }
}

function renderLogs() {
    const content = document.getElementById('logSheetContent');

    if (logsData.logs.length === 0) {
        content.innerHTML = `
            <div class="text-center text-gray-500 py-8">
                <div class="text-4xl mb-2">📋</div>
                <p>아직 기록된 로그가 없습니다</p>
                <p class="text-sm mt-1">플로우를 실행하면 여기에 기록됩니다</p>
            </div>
        `;
        return;
    }

    const logsHtml = logsData.logs.map(log => `
        <div class="flex items-start gap-3 p-3 border-b border-gray-100 last:border-b-0">
            <div class="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full ${getLogStatusBg(log.status)}">
                <span class="text-sm">${getLogActionIcon(log.action)}</span>
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                    <span class="font-medium text-gray-900 truncate">${log.flow_name || '알 수 없는 플로우'}</span>
                    <span class="text-xs px-1.5 py-0.5 rounded ${getLogStatusClass(log.status)}">${log.status_display}</span>
                </div>
                <div class="text-sm text-gray-600">${log.action_display}</div>
                ${log.message ? `<div class="text-xs text-gray-500 mt-1">${log.message}</div>` : ''}
                ${log.posts_processed ? `
                    <div class="text-xs text-gray-500 mt-1">
                        처리: ${log.posts_processed}개 (성공: ${log.posts_success}, 실패: ${log.posts_failed})
                        ${log.formatted_duration !== '-' ? ` · ${log.formatted_duration}` : ''}
                    </div>
                ` : ''}
            </div>
            <div class="text-xs text-gray-400 whitespace-nowrap">
                ${formatLogTime(log.created_at)}
            </div>
        </div>
    `).join('');

    const hasMore = logsData.offset < logsData.total;

    content.innerHTML = `
        <div class="divide-y divide-gray-100">
            ${logsHtml}
        </div>
        ${hasMore ? `
            <div class="text-center py-4">
                <button onclick="loadMoreLogs()"
                        class="text-sm text-blue-600 hover:text-blue-800 font-medium">
                    더 보기 (${logsData.total - logsData.offset}개 남음)
                </button>
            </div>
        ` : ''}
    `;
}

function loadMoreLogs() {
    loadLogs(true);
}

function refreshLogs() {
    loadLogs(false);
}

function getLogActionIcon(action) {
    const icons = {
        'started': '🚀',
        'completed': '✅',
        'failed': '❌',
        'paused': '⏸️',
        'resumed': '▶️',
        'stopped': '⏹️',
        'added': '➕',
        'removed': '➖'
    };
    return icons[action] || '📋';
}

function getLogStatusBg(status) {
    const bgs = {
        'success': 'bg-green-100',
        'failed': 'bg-red-100',
        'warning': 'bg-yellow-100'
    };
    return bgs[status] || 'bg-gray-100';
}

function getLogStatusClass(status) {
    const classes = {
        'success': 'bg-green-100 text-green-700',
        'failed': 'bg-red-100 text-red-700',
        'warning': 'bg-yellow-100 text-yellow-700'
    };
    return classes[status] || 'bg-gray-100 text-gray-700';
}

function formatLogTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;

    // 1분 미만
    if (diff < 60000) return '방금 전';
    // 1시간 미만
    if (diff < 3600000) return `${Math.floor(diff / 60000)}분 전`;
    // 오늘
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    }
    // 그 외
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// 확인 다이얼로그
let confirmCallback = null;

function showConfirmDialog(title, message, items, warning, callback) {
    const dialog = document.getElementById('confirmDialog');
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;

    const listEl = document.getElementById('confirmList');
    if (items && items.length > 0) {
        listEl.innerHTML = items.map(item => `
            <div class="text-sm text-gray-600 py-1">• ${item}</div>
        `).join('');
        listEl.style.display = 'block';
    } else {
        listEl.style.display = 'none';
    }

    const warningEl = document.getElementById('confirmWarning');
    if (warning) {
        warningEl.textContent = '⚠️ ' + warning;
        warningEl.style.display = 'block';
    } else {
        warningEl.style.display = 'none';
    }

    confirmCallback = callback;
    document.getElementById('confirmAction').onclick = async () => {
        closeConfirmDialog();
        if (confirmCallback) {
            await confirmCallback();
        }
    };

    dialog.classList.remove('hidden');
}

function closeConfirmDialog() {
    document.getElementById('confirmDialog').classList.add('hidden');
    confirmCallback = null;
}
