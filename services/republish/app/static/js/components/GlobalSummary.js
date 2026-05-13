/** GlobalSummary - 글로벌 요약탭 + 워커 상태 모니터링 컴포넌트 */
function globalSummary() {
    return {
        logPanelOpen: false,
        logFilter: localStorage.getItem('dashboard_log_filter') || 'all',
        logSearch: '',
        logBlogFilter: '',         // 블로그 드롭다운 선택값 (빈 문자열=전체)
        logActionFilter: '',       // 액션 라디오 선택값 (publish/republish/generate/queue_publish 등, 빈 문자열=전체)
        logBlogList: [],           // 검색 드롭다운용 블로그 목록
        logPageSize: parseInt(localStorage.getItem('dashboard_log_page_size') || '50', 10),
        unifiedLogs: [],
        unifiedLogsTotal: 0,
        hasMoreUnifiedLogs: false,
        refreshInterval: null,
        logRefreshInterval: null,
        stats: {
            // 초기값 설정 (API 로드 전 0 표시)
            total_blogs: 0, wordpress: 0, blogger: 0, active_blogs: 0, inactive_blogs: 0,
            topics: 0, subtopics: 0, keywords: 0,
            total_modules: 0, prompt_modules: 0, growth_profile_modules: 0, collect_modules: 0, data_modules: 0,
            total_flows: 0, active_flows: 0, inactive_flows: 0,
            week_generate: 0, week_publish: 0, week_republish: 0,
            today_generate: 0, today_publish: 0, today_republish: 0
        },
        logs: [],
        latestLog: '',
        latestLogTime: '',
        pinnedTabKeys: [],
        displayLogCount: 1,  // 고정 요약탭에 표시할 로그 수 (1~3)
        displayLogs: [],     // 고정 요약탭에 표시할 로그 배열
        // 워커 상태 (Phase 1: Worker Status UI)
        workerStatus: {
            workers: {
                generation: { status: 'unknown', active_tasks: 0 },
                publish: { status: 'unknown', active_tasks: 0 },
                utility: { status: 'unknown', active_tasks: 0 },
            },
            queues: {},
            total_queued: 0,
        },
        workerPollInterval: null,
        previousWorkerOnline: { generation: null, publish: null, utility: null },
        // 워커별 task 단위 추적 (대량 작업 환경 + 충돌 방지).
        // 구조: workerTaskTracker[workerKey][taskId] = {
        //   startedAt: number,           // 작업 시작 시각 (백엔드 time_start * 1000 또는 클라이언트 now)
        //   completedAt: number | null,  // 작업 완료 감지 시각 (null이면 진행 중)
        //   lastProgress: number,        // 완료 감지 시점의 진행률 (가속 시작점)
        //   taskName: string,            // tasks.generate_content 등
        // }
        workerTaskTracker: {},
        // 워커별 평균 작업 시간(ms) - 진행률 추정 기준
        workerAvgDurationMs: {
            generation: 60000,  // 글 생성 평균 60초 (AI 호출 + 이미지)
            publish: 15000,     // 발행 15초
            utility: 8000,      // 수집/이동 8초
            image: 30000,       // 이미지 생성 30초 (현재 UI는 generation에 통합)
        },
        // Alpine 반응성 트리거용 카운터
        progressTick: 0,
        progressTickerInterval: null,
        // Phase 5: 로그 매칭 큐 - 가속 중인 task와 새 SUCCESS/ERROR 로그를 동기화
        // 구조: [{ log, addedAt, lockedToKey }]
        // 가속 중인 task가 있을 때 SUCCESS/ERROR 로그를 잠시 보류했다가
        // task가 100%에 도달하면 displayLogs로 release. 5초 안전망.
        pendingLogQueue: [],
        // (시스템 탭은 대시보드 페이지로 이동됨)

        // 22개 전체 탭 정의
        allTabs: [
            // 블로그 (5개)
            { key: 'total_blogs', label: '전체 블로그', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'wordpress', label: '워드프레스', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'blogger', label: '구글 블로거', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'active_blogs', label: '활성 블로그', group: 'blog', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'inactive_blogs', label: '비활성 블로그', group: 'blog', bgClass: 'bg-gray-100', textClass: 'text-gray-600' },
            // 카테고리 (3개)
            { key: 'topics', label: '주제', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'subtopics', label: '하위주제', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'keywords', label: '키워드', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            // 모듈 (4개) — 생성/발행/재발행은 GP에 통합되어 별도 모듈 없음.
            // 수집(collect)/데이터(data) 모듈은 별도 운영.
            { key: 'total_modules', label: '전체 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'prompt_modules', label: '프롬프트 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'growth_profile_modules', label: 'GP 모듈', group: 'module', bgClass: 'bg-emerald-50', textClass: 'text-emerald-600' },
            { key: 'collect_modules', label: '수집 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'data_modules', label: '데이터 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            // 플로우 (3개)
            { key: 'total_flows', label: '전체 플로우', group: 'flow', bgClass: 'bg-cyan-50', textClass: 'text-cyan-600' },
            { key: 'active_flows', label: '활성 플로우', group: 'flow', bgClass: 'bg-cyan-50', textClass: 'text-cyan-600' },
            { key: 'inactive_flows', label: '비활성 플로우', group: 'flow', bgClass: 'bg-gray-100', textClass: 'text-gray-600' },
            // 이번 주 (3개)
            { key: 'week_generate', label: '이번 주 생성', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            { key: 'week_publish', label: '이번 주 발행', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            { key: 'week_republish', label: '이번 주 재발행', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            // 오늘 (3개)
            { key: 'today_generate', label: '오늘 생성', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
            { key: 'today_publish', label: '오늘 발행', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
            { key: 'today_republish', label: '오늘 재발행', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
        ],

        // 선택된 탭 객체 배열 (computed)
        get pinnedTabs() {
            return this.pinnedTabKeys
                .map(key => this.allTabs.find(t => t.key === key))
                .filter(Boolean);
        },

        async init() {
            // localStorage에서 고정 탭 설정 로드
            this.loadPinnedTabs();
            // 노출 로그 수 설정 로드
            this.loadDisplayLogCount();
            // 통계 데이터 로드
            await this.loadStats();
            // 최신 로그 로드 (노출 수만큼)
            await this.loadDisplayLogs();
            // 동작 로그 검색용 블로그 목록 미리 로드 (드롭다운 즉시 사용 가능)
            this.loadLogBlogList();
            // 실시간 갱신 시작 (30초마다)
            this.startAutoRefresh();
            // 로그 실시간 갱신 (10초마다)
            this.startLogAutoRefresh();
            // 워커 상태 폴링 시작 (3초마다 - 큐는 워커가 빠르게 가져가므로 짧은 주기 필요)
            this.loadWorkerStatus();
            this.workerPollInterval = setInterval(() => this.loadWorkerStatus(), 3000);

            // 진행률 시간 갱신 타이머 (250ms - 가속 채움 단계도 부드럽게 표시).
            // Phase 5: 같은 주기로 pendingLogQueue 처리 → 100% 도달 시 로그 release.
            this.progressTickerInterval = setInterval(() => {
                this.progressTick++;
                this._processLogQueue();
            }, 250);

            // 페이지 이탈 시 정리
            window.addEventListener('beforeunload', () => {
                this.stopAutoRefresh();
                this.stopLogAutoRefresh();
                this.stopWorkerPoll();
                if (this.progressTickerInterval) {
                    clearInterval(this.progressTickerInterval);
                    this.progressTickerInterval = null;
                }
            });
        },

        startAutoRefresh() {
            // 30초마다 통계 갱신
            this.refreshInterval = setInterval(() => {
                this.loadStats();
            }, 30000);
        },

        stopAutoRefresh() {
            if (this.refreshInterval) { clearInterval(this.refreshInterval); this.refreshInterval = null; }
        },
        startLogAutoRefresh() {
            // 10초마다 로그 바 + 확장 패널 갱신
            this.logRefreshInterval = setInterval(() => {
                this.loadDisplayLogs();
                if (this.logPanelOpen) this.loadUnifiedLogs();
            }, 10000);
        },

        stopLogAutoRefresh() {
            if (this.logRefreshInterval) { clearInterval(this.logRefreshInterval); this.logRefreshInterval = null; }
        },
        // 워커 폴링 정리
        stopWorkerPoll() {
            if (this.workerPollInterval) { clearInterval(this.workerPollInterval); this.workerPollInterval = null; }
        },
        loadPinnedTabs() {
            try {
                const saved = localStorage.getItem('dashboard_pinned_tabs');
                if (saved) {
                    this.pinnedTabKeys = JSON.parse(saved);
                } else {
                    // 기본값: 활성 플로우, 활성 블로그, 오늘 생성, 오늘 발행
                    this.pinnedTabKeys = ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
                }
            } catch (e) {
                this.pinnedTabKeys = ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
            }
        },

        savePinnedTabs() {
            localStorage.setItem('dashboard_pinned_tabs', JSON.stringify(this.pinnedTabKeys));
        },

        isTabPinned(key) {
            return this.pinnedTabKeys.includes(key);
        },

        togglePinTab(key) {
            if (this.isTabPinned(key)) {
                this.pinnedTabKeys = this.pinnedTabKeys.filter(k => k !== key);
            } else {
                this.pinnedTabKeys.push(key);
            }
        },

        async loadStats() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const res = await fetch(`${apiBase}/dashboard/stats`, { credentials: 'include' });
                if (res.ok) {
                    const data = await res.json();
                    // Alpine.js 반응형 업데이트를 위해 객체를 새로 할당
                    Object.keys(data).forEach(key => {
                        this.stats[key] = data[key];
                    });
                }
            } catch (error) {
                console.error('[GlobalSummary] 통계 로드 실패:', error);
            }
        },

        // 로그 패널 토글
        toggleLogPanel() {
            this.logPanelOpen = !this.logPanelOpen;
            if (this.logPanelOpen) {
                if (this.unifiedLogs.length === 0) {
                    this.loadUnifiedLogs();
                }
                if (this.logBlogList.length === 0) {
                    this.loadLogBlogList();
                }
            }
        },

        // 동작 로그 검색용 블로그 목록 로드
        async loadLogBlogList() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const resp = await fetch(`${apiBase}/dashboard/unified-logs/blog-list`, {
                    credentials: 'include'
                });
                if (resp.ok) {
                    const data = await resp.json();
                    this.logBlogList = data.blogs || [];
                }
            } catch (e) {
                console.warn('[GlobalSummary] 블로그 목록 로드 실패:', e);
            }
        },

        // 검색 조건 초기화
        resetLogFilters() {
            this.logSearch = '';
            this.logBlogFilter = '';
            this.logActionFilter = '';
            this.loadUnifiedLogs();
        },

        // 대시보드 페이지로 이동 (이미 대시보드면 무시)
        navigateToDashboard() {
            if (window.location.pathname !== '/dashboard') { window.location.href = '/dashboard'; }
        },

        formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;

            if (diff < 3600000) {
                const mins = Math.floor(diff / 60000);
                return mins <= 0 ? '방금' : `${mins}분 전`;
            }
            if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                return `${hours}시간 전`;
            }
            const days = Math.floor(diff / 86400000);
            return `${days}일 전`;
        },

        // 날짜+시간 표시 (MM/DD HH:MM:SS 형식)
        formatLogTime(timestamp) {
            if (!timestamp) return '';
            const d = new Date(timestamp);
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const hours = String(d.getHours()).padStart(2, '0');
            const minutes = String(d.getMinutes()).padStart(2, '0');
            const seconds = String(d.getSeconds()).padStart(2, '0');
            return `${month}/${day} ${hours}:${minutes}:${seconds}`;
        },

        async loadLatestLog() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const res = await fetch(`${apiBase}/dashboard/logs?limit=1`, { credentials: 'include' });
                if (res.ok) {
                    const data = await res.json();
                    if (data.logs && data.logs.length > 0) {
                        const log = data.logs[0];
                        this.latestLog = `[${log.level}] ${log.message}`;
                        this.latestLogTime = this.formatLogTime(log.timestamp);
                    }
                }
            } catch (error) {
                console.error('[GlobalSummary] 최신 로그 로드 실패:', error);
            }
        },

        // 노출 로그 수 설정 로드
        loadDisplayLogCount() {
            try {
                const saved = localStorage.getItem('dashboard_display_log_count');
                if (saved) {
                    const count = parseInt(saved);
                    if (count >= 1 && count <= 3) {
                        this.displayLogCount = count;
                    }
                }
            } catch (e) {
                this.displayLogCount = 1;
            }
        },

        // 노출 로그 수 설정 저장
        setDisplayLogCount(count) {
            this.displayLogCount = count;
            localStorage.setItem('dashboard_display_log_count', count.toString());
            this.loadDisplayLogs();
        },

        // 표시할 로그 로드 (노출 수만큼, 현재 필터 적용).
        // Phase 5: 가속 중인 task와 일치하는 SUCCESS/ERROR 로그는 pendingLogQueue로 보류.
        async loadDisplayLogs() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const params = new URLSearchParams({ limit: String(this.displayLogCount) });
                if (this.logFilter && this.logFilter !== 'all') {
                    params.set('log_type', this.logFilter);
                }
                const res = await fetch(`${apiBase}/dashboard/unified-logs?${params}`, { credentials: 'include' });
                if (res.ok) {
                    const data = await res.json();
                    const fetched = (data.logs || []).map(log => ({
                        ...log,
                        message: log.message || log.title || '',
                    }));

                    // Phase 5: 큐 중인 로그는 finalLogs에서 제외, 표시 중인 로그는 유지.
                    const queuedIds = new Set(this.pendingLogQueue.map(q => q.log && q.log.id));
                    const displayedIds = new Set((this.displayLogs || []).map(l => l && l.id));
                    const finalLogs = [];

                    for (const log of fetched) {
                        if (log.id != null && queuedIds.has(log.id)) {
                            continue;  // 이미 큐 → release 대기
                        }
                        if (log.id != null && displayedIds.has(log.id)) {
                            finalLogs.push(log);  // 이미 표시 중 → 유지
                            continue;
                        }
                        // 신규 로그 → 가속 중 task와 매칭 시도
                        const matchKey = this._matchLogToActiveAccel(log);
                        if (matchKey) {
                            this.pendingLogQueue.push({
                                log,
                                addedAt: Date.now(),
                                lockedToKey: matchKey,
                            });
                        } else {
                            finalLogs.push(log);
                        }
                    }
                    this.displayLogs = finalLogs;

                    if (this.displayLogs.length > 0) {
                        const log = this.displayLogs[0];
                        this.latestLog = `[${log.level}] ${log.message}`;
                        this.latestLogTime = this.formatLogTime(log.timestamp);
                    }
                }
            } catch (error) {
                console.error('[GlobalSummary] 로그 로드 실패:', error);
            }
        },

        // Phase 5: 로그를 가속/HOLD 중인 워커에 매칭.
        // action_type → worker key 매핑 후 해당 워커에 가속 중인 task가 있는지 확인.
        // 매칭되면 그 워커 key 반환, 아니면 null.
        // INFO/WARN/시스템 로그는 매칭하지 않음 (즉시 표시).
        _matchLogToActiveAccel(log) {
            if (!log || (log.level !== 'SUCCESS' && log.level !== 'ERROR')) return null;
            const actionToKey = {
                generate: 'generation',
                publish: 'publish',
                republish: 'publish',
                collect: 'utility',
                data: 'utility',
            };
            const key = actionToKey[log.action_type];
            if (!key) return null;
            const tracker = this.workerTaskTracker[key] || {};
            const now = Date.now();
            // 가속(_getAccelMs) + 최대 HOLD(800ms) 윈도 내에 완료된 task가 있는지
            for (const t of Object.values(tracker)) {
                if (!t.completedAt) continue;
                const accelMs = this._getAccelMs(t.lastProgress);
                if (now - t.completedAt < accelMs + 800) {
                    return key;
                }
            }
            return null;
        },

        // Phase 5: pendingLogQueue 처리 (250ms 주기로 progressTickerInterval에서 호출).
        // Release 조건:
        //   1) 매칭된 워커의 progress가 100% 도달 → 즉시 release (가속 완료)
        //   2) 매칭된 워커의 tracker에 완료 task 없음 → 비정상 케이스 release
        //   3) 5초 안전망: 추가 후 5초 경과 → 강제 release
        _processLogQueue() {
            if (!this.pendingLogQueue || this.pendingLogQueue.length === 0) return;
            const now = Date.now();
            const released = [];
            const remaining = [];
            const SAFETY_MS = 5000;

            for (const entry of this.pendingLogQueue) {
                const waitTime = now - entry.addedAt;
                if (waitTime >= SAFETY_MS) {
                    released.push(entry.log);
                    continue;
                }
                const progress = this.getWorkerProgress(entry.lockedToKey);
                if (progress >= 100) {
                    released.push(entry.log);
                    continue;
                }
                const tracker = this.workerTaskTracker[entry.lockedToKey] || {};
                const stillHasCompleted = Object.values(tracker).some(t => t.completedAt);
                if (!stillHasCompleted) {
                    released.push(entry.log);
                    continue;
                }
                remaining.push(entry);
            }

            this.pendingLogQueue = remaining;
            if (released.length === 0) return;

            // displayLogs 앞에 추가 + displayLogCount로 제한
            const merged = [...released, ...(this.displayLogs || [])];
            this.displayLogs = merged.slice(0, this.displayLogCount);
            const top = this.displayLogs[0];
            if (top) {
                this.latestLog = `[${top.level}] ${top.message || top.title || ''}`;
                this.latestLogTime = this.formatLogTime(top.timestamp);
            }
        },

        // 플랫폼 뱃지 문자 추출 (예: "[워]블로그명..." → "워")
        getPlatformBadge(message) {
            if (!message) return null;
            const match = message.match(/^\[(.)\]/);
            return match ? match[1] : null;
        },

        // 플랫폼 뱃지 배경색 클래스 반환
        getPlatformBadgeClass(badge) {
            const colorMap = { '워': 'bg-blue-500', '구': 'bg-orange-500' };
            return colorMap[badge] || 'bg-gray-500';
        },

        // 플랫폼 뱃지 제거 후 메시지 반환
        getMessageText(message) {
            if (!message) return '';
            return message.replace(/^\[.\]/, '').trim();
        },

        // 메시지 슬라이드 지속 시간 계산 (메시지 길이에 따라 조정)
        getMessageSlideDuration(message) {
            if (!message) return 20;
            // 메시지 길이에 비례 (최소 15초, 최대 40초)
            const baseTime = 15;
            const charTime = 0.3;  // 글자당 0.3초
            const duration = baseTime + (message.length * charTime);
            return Math.min(Math.max(duration, 15), 40);
        },

        // 워커 상태 조회 + task 등장/사라짐 감지
        async loadWorkerStatus() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const resp = await fetch(`${apiBase}/dashboard/celery/workers`, {
                    credentials: 'include'
                });
                if (resp.ok) {
                    const data = await resp.json();
                    // 워커 offline 전환 감지
                    const labels = { generation: '생성', publish: '발행', utility: '유틸리티' };
                    for (const key of ['generation', 'publish', 'utility']) {
                        const curr = data.workers?.[key]?.status;
                        const prev = this.previousWorkerOnline[key];
                        if (prev === 'online' && curr === 'offline') {
                            showErrorMessage(`${labels[key]} 워커가 오프라인으로 전환되었습니다`);
                        }
                        this.previousWorkerOnline[key] = curr || 'unknown';
                    }
                    this.workerStatus = data;
                    // task 등장/사라짐 감지 → tracker 갱신
                    this._syncTaskTracker();
                }
            } catch (e) {
                console.warn('[GlobalSummary] 워커 상태 조회 실패:', e);
            }
        },

        // task_id 기반 등장/사라짐 감지 + tracker 갱신
        _syncTaskTracker() {
            const now = Date.now();
            const workers = this.workerStatus?.workers || {};
            // UI 워커 키만 처리 (image는 generation에 통합되어 별도 카드 없음)
            for (const key of ['generation', 'publish', 'utility']) {
                const w = workers[key];
                if (!w) continue;
                const taskList = Array.isArray(w.active_task_list) ? w.active_task_list : [];
                const tracker = this.workerTaskTracker[key] || {};
                const currentIds = new Set(taskList.map(t => t.id).filter(Boolean));

                // 새 task 등장 → startedAt 등록 (백엔드 time_start 우선, 없으면 now)
                for (const t of taskList) {
                    if (!t.id) continue;
                    if (!tracker[t.id]) {
                        const startedAt = (typeof t.time_start === 'number' && t.time_start > 0)
                            ? t.time_start * 1000  // Celery time_start는 unix epoch seconds
                            : now;
                        tracker[t.id] = {
                            startedAt,
                            completedAt: null,
                            lastProgress: 0,
                            taskName: t.name || '',
                        };
                    }
                }
                // 사라진 task → completedAt 등록 (이미 완료된 것은 그대로)
                for (const taskId of Object.keys(tracker)) {
                    if (!currentIds.has(taskId) && !tracker[taskId].completedAt) {
                        // 작업 완료 시점 도달 → lastProgress 보존
                        const elapsed = now - tracker[taskId].startedAt;
                        const duration = this.workerAvgDurationMs[key] || 30000;
                        // 진행률 계산은 Phase 3에서 비선형 곡선으로 변경 예정
                        // 지금은 임시로 선형 계산 (다음 Phase에서 _calcProgressFromRatio 사용)
                        const ratio = elapsed / duration;
                        tracker[taskId].lastProgress = Math.min(99, Math.max(1, Math.round(ratio * 95)));
                        tracker[taskId].completedAt = now;
                    }
                }
                this.workerTaskTracker[key] = tracker;
            }
        },

        // 워커 상태 인디케이터 dot 클래스
        getWorkerDotClass(key) {
            const w = this.workerStatus?.workers?.[key];
            if (!w || w.status === 'unknown') return 'bg-gray-500';
            if (w.status === 'offline') return 'bg-red-400';
            // saturated: active > concurrency → amber 강조
            if (this._isWorkerSaturated(key)) return 'bg-amber-500 animate-pulse';
            if (w.active_tasks > 0) return 'bg-blue-400 animate-pulse';
            return 'bg-green-400';
        },

        // 구간별 비선형 진행률 곡선:
        //   ratio 0.0~0.8 → 0~80%  (선형 빠른 진행 - 평균 80% 시점에 80% 도달)
        //   ratio 0.8~1.0 → 80~95% (선형 중간 - 평균 시점에 95%)
        //   ratio 1.0~1.5 → 95~99% (선형 매우 느림 - 평균 +50%까지 99%)
        //   ratio 1.5+    → 99%    (soft cap, 완료 대기)
        _calcProgressFromRatio(ratio) {
            if (ratio < 0) return 0;
            if (ratio < 0.8) return Math.round((ratio / 0.8) * 80);
            if (ratio < 1.0) return Math.round(80 + (ratio - 0.8) * 75);
            if (ratio < 1.5) return Math.round(95 + (ratio - 1.0) * 8);
            return 99;
        },

        // 현재 진행률에 따른 동적 가속 채움 시간 (ms).
        // 큰 점프(낮은 progress)는 길게, 작은 점프(높은 progress)는 짧게.
        _getAccelMs(lastProgress) {
            if (lastProgress >= 99) return 300;   // soft cap → 1% 채움만
            if (lastProgress >= 80) return 400;
            if (lastProgress >= 50) return 800;
            return 1500;
        },

        // 워커 진행률 (0~100) — UI에 표시할 메인 task 1개 기준.
        // 우선순위 1: 가속 채움 중인 task (가장 최근 완료) → 100% 점프 표시
        // 우선순위 2: 활성 task 중 가장 오래된 것 → 시간 기반 진행률
        // 우선순위 3: 0% (모든 task 종료)
        //
        // Phase 4 핵심: 100% 유지 시간 동적 조정 + 자연 전환.
        // - 다음 활성 task 대기 중: HOLD 300ms (빠르게 다음 task로 전환)
        // - 단독 완료: HOLD 800ms (잠시 머무른 후 0%로)
        // - 0% 리셋 폐기: 완료 task 제거 후 활성 task의 현재 진행률로 자연 전환
        //   (활성 task 있으면 0%가 아닌 그 task의 진행률 반환)
        getWorkerProgress(key) {
            const w = this.workerStatus?.workers?.[key];
            if (!w || w.status !== 'online') return 0;
            // Alpine 반응성 트리거 (250ms tick으로 UI 갱신)
            void this.progressTick;
            const tracker = this.workerTaskTracker[key] || {};
            const now = Date.now();
            const duration = this.workerAvgDurationMs[key] || 30000;

            // 활성 task 목록 - 자연 전환 우선순위 판정에 먼저 사용
            const activeTasks = Object.entries(tracker)
                .filter(([_, t]) => !t.completedAt)
                .sort((a, b) => a[1].startedAt - b[1].startedAt);
            const hasActiveTasks = activeTasks.length > 0;

            // 우선순위 1: 가속 채움 중인 task (가장 최근 완료 1개만)
            const completedTasks = Object.entries(tracker)
                .filter(([_, t]) => t.completedAt)
                .sort((a, b) => b[1].completedAt - a[1].completedAt);

            if (completedTasks.length > 0) {
                const [completedId, t] = completedTasks[0];
                const sinceCompleted = now - t.completedAt;
                const accelMs = this._getAccelMs(t.lastProgress);
                // 동적 HOLD: 다음 활성 task 대기 시 짧게(300ms), 단독 완료 시 길게(800ms)
                const holdMs = hasActiveTasks ? 300 : 800;
                const startP = t.lastProgress || 0;

                if (sinceCompleted < accelMs) {
                    // 가속 채움 단계 (lastProgress → 100% 부드러운 점프)
                    const ratio = sinceCompleted / accelMs;
                    return Math.min(100, Math.round(startP + (100 - startP) * ratio));
                }
                if (sinceCompleted < accelMs + holdMs) {
                    // 100% 유지 (다음 task 대기 시 빠르게 자연 전환)
                    return 100;
                }
                // 가속 + 유지 종료 → tracker에서 제거.
                // 활성 task 있으면 다음 줄에서 그 task의 진행률 반환 (0% 리셋 폐기).
                delete tracker[completedId];
                this.workerTaskTracker[key] = tracker;
            }

            // 우선순위 2: 활성 task 중 가장 오래된 것의 시간 기반 진행률
            if (!hasActiveTasks) return 0;
            const [, t] = activeTasks[0];
            const elapsed = now - t.startedAt;
            const ratio = elapsed / duration;
            return this._calcProgressFromRatio(ratio);
        },

        // soft cap(99%) 도달 상태 여부 — "마무리 중..." UI 표시용
        isWorkerSoftCapped(key) {
            const progress = this.getWorkerProgress(key);
            if (progress !== 99) return false;
            // 가속 채움 중인 task가 있으면 일반 가속 진행이므로 soft cap 아님
            const tracker = this.workerTaskTracker[key] || {};
            const hasCompleted = Object.values(tracker).some(t => t.completedAt);
            return !hasCompleted;
        },

        // 워커 상태 분류: offline / idle / busy / saturated / unknown
        getWorkerState(key) {
            const w = this.workerStatus?.workers?.[key];
            if (!w || w.status === 'unknown') return 'unknown';
            if (w.status === 'offline') return 'offline';
            const active = w.active_tasks || 0;
            const max = w.concurrency || 1;
            if (active === 0) return 'idle';
            if (active > max) return 'saturated';
            return 'busy';
        },

        _isWorkerSaturated(key) {
            return this.getWorkerState(key) === 'saturated';
        },

        // 워커 카드 인라인 스타일 - 시간 기반 진행률을 background-size로 표시.
        // active>0이면 progress(0~95%)에 비례해 좌→우로 점진 채움,
        // 완료 직후 100%로 잠시 유지 후 0%로 리셋(별도 무한 반복 없음).
        getWorkerCardStyle(key) {
            const state = this.getWorkerState(key);
            const progress = this.getWorkerProgress(key);
            const palette = {
                idle:      { fill: 'rgba(34,197,94,0)',    bg: '#f0fdf4' },
                busy:      { fill: 'rgba(59,130,246,0.45)', bg: 'rgba(59,130,246,0.10)' },
                saturated: { fill: 'rgba(245,158,11,0.55)', bg: 'rgba(245,158,11,0.12)' },
                offline:   { fill: 'transparent',           bg: '#fef2f2' },
                unknown:   { fill: 'transparent',           bg: '#f3f4f6' },
            };
            const c = palette[state] || palette.unknown;

            if (state === 'busy' || state === 'saturated') {
                return {
                    backgroundColor: c.bg,
                    backgroundImage: `linear-gradient(to right, ${c.fill}, ${c.fill})`,
                    backgroundRepeat: 'no-repeat',
                    backgroundSize: `${progress}% 100%`,
                    // 250ms tick과 맞춰 부드러운 채움 (가속 단계 600ms와도 자연 동기화)
                    transition: 'background-size 0.3s linear',
                };
            }
            return {
                backgroundColor: c.bg,
                backgroundImage: 'none',
                transition: 'background-color 0.4s ease-out',
            };
        },

        // 워커 카드 외곽 border 클래스 (상태별)
        getWorkerCardBorder(key) {
            const state = this.getWorkerState(key);
            const map = {
                idle:      'border border-green-200',
                busy:      'border border-blue-300',
                saturated: 'border border-amber-300',
                offline:   'border border-red-200',
                unknown:   'border border-gray-200',
            };
            return map[state] || map.unknown;
        },

        // 워커 상태 툴팁 텍스트 (확장: processed/concurrency/uptime)
        getWorkerTooltip(key) {
            const labels = {
                generation: '생성', publish: '발행',
                utility: '유틸리티', image: '이미지',
            };
            const label = labels[key] || key;
            const w = this.workerStatus?.workers?.[key];
            if (!w || w.status === 'unknown') return `${label} 워커: 확인 중`;
            if (w.status === 'offline') return `${label} 워커: 오프라인`;
            const progress = this.getWorkerProgress(key);
            const state = this.getWorkerState(key);
            const stateLabel = (
                state === 'saturated' ? '과부하' :
                state === 'busy' ? '실행 중' :
                state === 'idle' ? '대기' : ''
            );
            return (
                `${label} 워커: 온라인 (${stateLabel})\n` +
                `점유율: ${w.active_tasks || 0}/${w.concurrency || '?'}` +
                ` (${progress}%)\n` +
                `처리량: ${w.processed ?? 0}건` +
                (w.uptime ? `\n가동시간: ${w.uptime}` : '')
            );
        },

        // 검색용 쿼리 파라미터 빌드 (loadUnifiedLogs/loadMore에서 공용 사용)
        _buildLogQueryParams(offset) {
            const params = new URLSearchParams({
                limit: String(this.logPageSize),
                offset: String(offset),
                log_type: this.logFilter,
                level: 'all',
            });
            if (this.logSearch) params.set('search', this.logSearch);
            if (this.logBlogFilter) params.set('blog_name', this.logBlogFilter);
            if (this.logActionFilter) params.set('action_type', this.logActionFilter);
            return params;
        },

        // 통합 로그 로드 (검색/필터 변경 시 처음부터 다시 로드)
        async loadUnifiedLogs() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const params = this._buildLogQueryParams(0);
                const resp = await fetch(`${apiBase}/dashboard/unified-logs?${params}`, { credentials: 'include' });
                if (resp.ok) {
                    const data = await resp.json();
                    this.unifiedLogs = data.logs || [];
                    this.unifiedLogsTotal = data.total || 0;
                    this.hasMoreUnifiedLogs = data.has_more || false;
                }
            } catch (e) {
                console.warn('[GlobalSummary] 통합 로그 로드 실패:', e);
            }
        },

        // 통합 로그 더 보기 (현재까지 로드된 다음부터 추가 조회)
        async loadMoreUnifiedLogs() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const params = this._buildLogQueryParams(this.unifiedLogs.length);
                const resp = await fetch(`${apiBase}/dashboard/unified-logs?${params}`, { credentials: 'include' });
                if (resp.ok) {
                    const data = await resp.json();
                    this.unifiedLogs = [...this.unifiedLogs, ...(data.logs || [])];
                    this.hasMoreUnifiedLogs = data.has_more || false;
                }
            } catch (e) {
                console.warn('[GlobalSummary] 추가 통합 로그 로드 실패:', e);
            }
        },

        // 페이지 사이즈 변경
        setLogPageSize(size) {
            this.logPageSize = size;
            localStorage.setItem('dashboard_log_page_size', String(size));
            this.loadUnifiedLogs();
        },

        // 로그 레벨 CSS 클래스
        getLevelClass(level) {
            const map = {
                'INFO': 'bg-blue-900 text-blue-300',
                'SUCCESS': 'bg-green-900 text-green-300',
                'WARN': 'bg-yellow-900 text-yellow-300',
                'ERROR': 'bg-red-900 text-red-300',
            };
            return map[level] || 'bg-gray-800 text-gray-400';
        },

        // 액션 타입별 배지 클래스
        getActionBadgeClass(actionType) {
            const map = {
                generate: 'bg-emerald-800/60 text-emerald-300',
                publish: 'bg-blue-800/60 text-blue-300',
                republish: 'bg-violet-800/60 text-violet-300',
                collect: 'bg-cyan-800/60 text-cyan-300',
                data: 'bg-amber-800/60 text-amber-300',
                queue_register: 'bg-indigo-800/60 text-indigo-300',
            };
            return map[actionType] || 'bg-gray-700/60 text-gray-400';
        },
        getActionLabel(actionType) {
            const map = { generate: '생성', publish: '발행', republish: '재발행', collect: '수집', data: '데이터', queue_register: '워커 등록' };
            return map[actionType] || '시스템';
        },
        getLogRowBorderClass(actionType) {
            // 작업 로그(generate/publish/republish/collect/data)는 별도 강조 없음.
            // 활동 로그(queue_register/system)는 행 전체 배경 하이라이트로 표시.
            return '';
        },
        getLogRowBgClass(level, actionType) {
            if (level === 'ERROR') return 'bg-red-900/40';
            if (level === 'WARN') return 'bg-amber-900/20';
            // 활동 로그 전체 하이라이트
            if (actionType === 'queue_register') return 'bg-indigo-900/40';
            if (actionType === 'system') return 'bg-slate-700/40';
            return '';
        },

        // 외부에서 로그 추가 (전역 함수로 사용 가능)
        addLog(level, message) {
            const logEntry = {
                level: level,
                message: message,
                timestamp: new Date().toISOString()
            };
            this.logs.unshift(logEntry);
            this.latestLog = `[${level}] ${message}`;
            this.latestLogTime = this.formatLogTime(logEntry.timestamp);

            // 서버에도 저장 시도
            this.saveLogToServer(logEntry);
        },

        async saveLogToServer(logEntry) {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                await fetch(`${apiBase}/dashboard/logs`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(logEntry)
                });
            } catch (error) {
                // 실패해도 무시 (클라이언트에는 이미 표시됨)
            }
        }
    };
}

// 전역 로그 함수 (다른 컴포넌트에서 사용)
window.addGlobalLog = function(level, message) {
    const component = document.querySelector('[x-data*="globalSummary"]');
    if (component && component.__x) {
        component.__x.$data.addLog(level, message);
    }
};
