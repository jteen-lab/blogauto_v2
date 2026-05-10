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
            total_modules: 0, prompt_modules: 0, generate_modules: 0, publish_modules: 0, republish_modules: 0, growth_profile_modules: 0,
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
            // 모듈 (5개)
            { key: 'total_modules', label: '전체 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'prompt_modules', label: '프롬프트 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'generate_modules', label: '생성 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'publish_modules', label: '발행 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'republish_modules', label: '재발행 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'growth_profile_modules', label: 'GP 모듈', group: 'module', bgClass: 'bg-emerald-50', textClass: 'text-emerald-600' },
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

            // 페이지 이탈 시 정리
            window.addEventListener('beforeunload', () => {
                this.stopAutoRefresh();
                this.stopLogAutoRefresh();
                this.stopWorkerPoll();
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

        // 표시할 로그 로드 (노출 수만큼, 현재 필터 적용)
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
                    // unified-logs는 title 필드, 로그 바는 message 필드 사용 - 정규화
                    this.displayLogs = (data.logs || []).map(log => ({
                        ...log,
                        message: log.message || log.title || '',
                    }));
                    // 호환성을 위해 latestLog도 업데이트
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

        // 워커 상태 조회
        async loadWorkerStatus() {
            try {
                const apiBase = typeof API_BASE !== 'undefined' ? API_BASE : '/api/v1';
                const resp = await fetch(`${apiBase}/dashboard/celery/workers`, {
                    credentials: 'include'
                });
                if (resp.ok) {
                    const data = await resp.json();
                    // 워커 offline 전환 감지 (Phase 3)
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
                }
            } catch (e) {
                console.warn('[GlobalSummary] 워커 상태 조회 실패:', e);
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

        // 워커 점유율 (0~100) — 진행률 바 채움 비율
        getWorkerProgress(key) {
            const w = this.workerStatus?.workers?.[key];
            if (!w || w.status !== 'online') return 0;
            const active = Math.max(0, w.active_tasks || 0);
            const max = Math.max(1, w.concurrency || 1);
            return Math.min(100, Math.round((active / max) * 100));
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

        // 워커 카드 인라인 스타일 (CSS 변수로 그라데이션 진행률 전달)
        getWorkerCardStyle(key) {
            const state = this.getWorkerState(key);
            const progress = this.getWorkerProgress(key);
            // 상태별 채움 색상 / 배경 색상
            const palette = {
                idle:      { fill: 'transparent', bg: '#f0fdf4' },  // green-50
                busy:      { fill: 'rgba(59,130,246,0.35)', bg: 'rgba(59,130,246,0.08)' },   // blue
                saturated: { fill: 'rgba(245,158,11,0.45)', bg: 'rgba(245,158,11,0.12)' },   // amber
                offline:   { fill: 'transparent', bg: '#fef2f2' },  // red-50
                unknown:   { fill: 'transparent', bg: '#f3f4f6' },  // gray-100
            };
            const c = palette[state] || palette.unknown;
            // saturated일 때는 100%로 가득 채움
            const pct = state === 'saturated' ? 100 : progress;
            return {
                background: `linear-gradient(to right, ${c.fill} ${pct}%, ${c.bg} ${pct}%)`,
                transition: 'background 0.4s ease-out',
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
