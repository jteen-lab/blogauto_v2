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

            // 활성 + 일시정지 + 비활성 플로우 모두 표시 (오토런에 추가된 모든 플로우)
            this.autorunFlows = [
                ...(data.active_flows || []),
                ...(data.paused_flows || []),
                ...(data.inactive_flows || [])
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

            // 네이티브 confirm() 사용 - this 컨텍스트 문제 해결
            if (!confirm(`'${flow.name}' 플로우를 오토런에서 제외하시겠습니까?\n\n제외 시 예약된 스케줄이 해제됩니다.`)) {
                return;
            }

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

        async bulkRemove() {
            if (this.selectedIds.length === 0) return;

            const names = this.selectedIds.map(id =>
                this.autorunFlows.find(f => f.id === id)?.name || ''
            ).filter(Boolean);

            // 네이티브 confirm() 사용 - this 컨텍스트 문제 해결
            const confirmMsg = `다음 ${names.length}개 플로우를 오토런에서 제외하시겠습니까?\n\n` +
                names.map(n => `• ${n}`).join('\n') +
                '\n\n제외 시 예약된 스케줄이 해제됩니다.';

            if (!confirm(confirmMsg)) {
                return;
            }

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
        },

        // 하단 시트 열기
        openAddSheet() {
            loadAvailableFlows();
            openBottomSheet('addSheet');
        }
    };
}

// autorunCardState() 함수 제거됨
// 카드에서 x-data="autorunCardState()" 제거 후 부모 autorunApp() 스코프 직접 사용

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
        'generate': '✨',
        'prompt': '📝',
        'publish': '📤',
        'collect': '🔍',
        'growth_profile': '📈'
    };
    return icons[code] || '📦';
}

// 모듈 타입별 표시할 정보 아이템 반환 (flows/list.js와 동일)
function getModuleInfoItems(module) {
    if (!module) return [];
    const items = [];
    const typeCode = module.module_type?.code || '';

    if (typeCode === 'republish') {
        items.push({ label: '범위', value: getPostRangeText(module) });
        items.push({ label: '간격', value: getIntervalText(module) });
        const schedule = getScheduleSummary(module);
        if (schedule !== '설정 없음') {
            items.push({ label: '스케줄', value: schedule });
        }
    } else if (typeCode === 'publish') {
        items.push({ label: '간격', value: getIntervalText(module) });
        const schedule = getScheduleSummary(module);
        if (schedule !== '설정 없음') {
            items.push({ label: '스케줄', value: schedule });
        }
    } else if (typeCode === 'generate') {
        if (module.ai_model) {
            items.push({ label: 'AI', value: module.ai_model });
        }
        if (module.prompt_template) {
            const promptPreview = module.prompt_template.substring(0, 30) + '...';
            items.push({ label: '프롬프트', value: promptPreview });
        }
    } else if (typeCode === 'prompt') {
        if (module.prompt_name) {
            items.push({ label: '이름', value: module.prompt_name });
        }
        if (module.category) {
            items.push({ label: '카테고리', value: module.category });
        }
    } else if (typeCode === 'collect') {
        // 수집 모듈 정보 표시 (flows/list.js와 동일)
        const settings = module.settings || {};

        // 수집 대상
        const sources = [];
        if (settings.source_naver_datalab) sources.push('데이터랩');
        if (settings.source_naver_ads) sources.push('네이버광고');
        if (settings.source_google_trends) sources.push('트렌드');
        if (settings.source_google_planner) sources.push('플래너');
        if (sources.length > 0) {
            items.push({ label: '수집', value: sources.join(', ') });
        }

        // 수집 타입
        const typeMap = { 'keyword': '키워드', 'title': '제목', 'both': '키워드+제목' };
        if (settings.collect_type) {
            items.push({ label: '타입', value: typeMap[settings.collect_type] || '전체' });
        }

        // 스케줄
        if (settings.schedule_mode === 'fixed_time' && settings.fixed_times?.length > 0) {
            items.push({ label: '시간', value: settings.fixed_times.join(', ') });
        } else if (settings.schedule_mode === 'interval' && settings.interval_hours) {
            items.push({ label: '간격', value: `${settings.interval_hours}시간` });
        }
    } else if (typeCode === 'growth_profile') {
        const settings = module.settings || {};
        const stages = settings.stages || [];
        if (stages.length > 0) {
            items.push({ label: '구간', value: `${stages.length}단계` });
        }
        const activeModules = [];
        const firstStage = stages[0] || {};
        if (firstStage.generate?.enabled) activeModules.push('생성');
        if (firstStage.publish?.enabled) activeModules.push('발행');
        if (firstStage.republish?.enabled) activeModules.push('재발행');
        if (activeModules.length > 0) {
            items.push({ label: '활성', value: activeModules.join('/') });
        }
        if (settings.warmup?.enabled) {
            items.push({ label: '워밍업', value: `${settings.warmup.warmup_days || 0}일` });
        }
    }

    // 기본 정보가 없으면 생성일 표시
    if (items.length === 0 && module.created_at) {
        const date = new Date(module.created_at).toLocaleDateString('ko-KR');
        items.push({ label: '생성일', value: date });
    }

    return items;
}

// 포스트 범위 텍스트 반환
function getPostRangeText(module) {
    const start = module.post_range_start || 1;
    const end = module.post_range_end;
    if (!end) {
        return `${start}~무제한 (누적 포스트)`;
    }
    return `${start}~${end} (누적 포스트)`;
}

// 간격 텍스트 반환
function getIntervalText(module) {
    const mode = module.interval_mode || 'manual';
    const activeMinutes = calculateActiveMinutes(module);

    if (mode === 'auto' && module.auto_daily_count) {
        const minInterval = Math.ceil(activeMinutes / module.auto_daily_count);
        return `${module.auto_daily_count}회/일 (최소 ${minInterval}분 간격)`;
    } else if (module.manual_interval_minutes) {
        const maxDaily = Math.floor(activeMinutes / module.manual_interval_minutes);
        return `${module.manual_interval_minutes}분마다 (최대 ${maxDaily}회/일)`;
    }
    return "설정 없음";
}

// 활성 시간 계산
function calculateActiveMinutes(module) {
    if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
        return 720;
    }
    let totalActiveMinutes = 0;
    for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
        const daySchedule = module.schedule_matrix[dayIdx];
        if (Array.isArray(daySchedule)) {
            const activeHours = daySchedule.filter(hour => hour === true).length;
            totalActiveMinutes += activeHours * 60;
        }
    }
    return Math.round(totalActiveMinutes / 7) || 720;
}

// 스케줄 요약 반환
function getScheduleSummary(module) {
    if (!module.schedule_matrix || !Array.isArray(module.schedule_matrix)) {
        return "설정 없음";
    }
    const schedule = module.schedule_matrix;
    const days = ['월', '화', '수', '목', '금', '토', '일'];
    const dayRanges = {};

    for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
        const daySchedule = schedule[dayIdx];
        if (Array.isArray(daySchedule) && daySchedule.some(hour => hour === true)) {
            const timeRange = extractTimeRange(daySchedule);
            if (timeRange) {
                dayRanges[dayIdx] = timeRange;
            }
        }
    }

    if (Object.keys(dayRanges).length === 0) {
        return "설정 없음";
    }

    const timeGroups = {};
    for (const [dayIdx, timeRange] of Object.entries(dayRanges)) {
        if (!timeGroups[timeRange]) {
            timeGroups[timeRange] = [];
        }
        timeGroups[timeRange].push(parseInt(dayIdx));
    }

    const groupTexts = [];
    for (const [timeRange, dayIndices] of Object.entries(timeGroups)) {
        const dayText = formatDayRange(dayIndices, days);
        groupTexts.push(`${dayText}(${timeRange})`);
    }
    return groupTexts.join('\n');
}

// 시간 범위 추출
function extractTimeRange(daySchedule) {
    let startHour = -1;
    let endHour = -1;
    for (let hour = 0; hour < 24; hour++) {
        if (daySchedule[hour]) {
            if (startHour === -1) startHour = hour;
            endHour = hour;
        }
    }
    if (startHour === -1) return null;
    return `${String(startHour).padStart(2, '0')}~${String(endHour + 1).padStart(2, '0')}`;
}

// 요일 범위 포맷
function formatDayRange(dayIndices, days) {
    if (dayIndices.length === 1) {
        return days[dayIndices[0]];
    }
    dayIndices.sort((a, b) => a - b);
    let ranges = [];
    let start = dayIndices[0];
    let end = start;

    for (let i = 1; i < dayIndices.length; i++) {
        if (dayIndices[i] === end + 1) {
            end = dayIndices[i];
        } else {
            ranges.push(start === end ? days[start] : `${days[start]}~${days[end]}`);
            start = dayIndices[i];
            end = start;
        }
    }
    ranges.push(start === end ? days[start] : `${days[start]}~${days[end]}`);
    return ranges.join(', ');
}

// 모듈 슬라이드 필요 여부 판단 (초기 힌트, DOM 체크로 최종 결정)
function needsModuleSlide(module) {
    return getModuleInfoItems(module).length >= 1;
}

// 모듈 정보 텍스트 길이에 따른 슬라이드 속도 계산 (초)
function getModuleSlideDuration(module) {
    const items = getModuleInfoItems(module);
    const totalLength = items.reduce((sum, item) => {
        return sum + (item.label?.length || 0) + (item.value?.length || 0);
    }, 0);
    const baseSpeed = 12;
    const perChar = 0.25;
    const minDuration = 12;
    const maxDuration = 40;
    return Math.max(minDuration, Math.min(maxDuration, baseSpeed + (totalLength * perChar)));
}

// 블로그 슬라이드 필요 여부 판단 (초기 힌트, DOM 체크로 최종 결정)
function needsBlogSlide(blogCount) {
    return blogCount >= 1;
}

// 블로그 개수에 따른 슬라이드 속도 계산 (초)
function getBlogSlideDuration(blogCount) {
    const baseSpeed = 5.4;
    const minDuration = 14;
    const maxDuration = 44;
    return Math.max(minDuration, Math.min(maxDuration, blogCount * baseSpeed));
}

function initSlideCheck(el) {
    const container = el.querySelector('.module-slide-container');
    const track = el.querySelector('.module-slide-track');
    if (!container || !track) return;

    setTimeout(() => {
        const containerWidth = container.clientWidth;
        if (containerWidth === 0) return;

        // 측정을 위해 no-slide 일시 제거 (복제 콘텐츠 display:none 해제)
        track.classList.remove('no-slide');
        const trackWidth = track.scrollWidth / 2;

        if (trackWidth > containerWidth) {
            // 슬라이드 필요 - no-slide 이미 제거됨
        } else {
            // 슬라이드 불필요 - no-slide 복원
            track.classList.add('no-slide');
        }
    }, 100);
}

function initBlogSlideCheck(el, count) {
    const container = el.querySelector('.blog-slide-container');
    const track = el.querySelector('.blog-slide-track');
    if (!container || !track) return;

    setTimeout(() => {
        const containerWidth = container.clientWidth;
        if (containerWidth === 0) return;

        track.classList.remove('no-slide');
        const trackWidth = track.scrollWidth / 2;

        if (trackWidth > containerWidth) {
            // 슬라이드 필요
        } else {
            track.classList.add('no-slide');
        }
    }, 100);
}

// 슬라이드 재초기화 (더보기 클릭 시 호출)
function reinitSlides(containerEl) {
    if (!containerEl) return;

    setTimeout(() => {
        // 모듈 슬라이드 재초기화
        containerEl.querySelectorAll('.module-slide-row').forEach(row => {
            const container = row.querySelector('.module-slide-container');
            const track = row.querySelector('.module-slide-track');
            if (!container || !track) return;

            const containerWidth = container.clientWidth;
            if (containerWidth === 0) return;

            track.classList.remove('no-slide');
            const trackWidth = track.scrollWidth / 2;

            if (trackWidth <= containerWidth) {
                track.classList.add('no-slide');
            }
        });

        // 블로그 슬라이드 재초기화
        containerEl.querySelectorAll('.blog-slide-section').forEach(section => {
            const container = section.querySelector('.blog-slide-container');
            const track = section.querySelector('.blog-slide-track');
            if (!container || !track) return;

            const containerWidth = container.clientWidth;
            if (containerWidth === 0) return;

            track.classList.remove('no-slide');
            const trackWidth = track.scrollWidth / 2;

            if (trackWidth <= containerWidth) {
                track.classList.add('no-slide');
            }
        });
    }, 50);
}

function toggleSlideTouch(event, el) {
    if (event.type !== 'touchstart') return;

    const track = el.querySelector('.module-slide-track') || el.querySelector('.blog-slide-track');
    if (!track) return;

    const isPaused = track.classList.contains('paused');
    if (isPaused) {
        track.classList.remove('paused');
    } else {
        track.classList.add('paused');
        setTimeout(() => {
            track.classList.remove('paused');
        }, 5000);
    }
}

// 스크롤 위치 저장용 변수 (autorun)
let autorunSavedScrollPosition = 0;

// 하단 시트 관련
function openBottomSheet(id) {
    const backdrop = document.getElementById(`${id}-backdrop`);
    const sheet = document.getElementById(id);

    if (backdrop && sheet) {
        // 모바일에서 body 스크롤 고정
        autorunSavedScrollPosition = window.pageYOffset;
        document.body.classList.add('sheet-open');
        document.body.style.top = `-${autorunSavedScrollPosition}px`;

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

            // body 스크롤 복원
            document.body.classList.remove('sheet-open');
            document.body.style.top = '';
            window.scrollTo(0, autorunSavedScrollPosition);
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
