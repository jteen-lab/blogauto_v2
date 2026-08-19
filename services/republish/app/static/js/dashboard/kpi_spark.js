/**
 * compactDashboard - 대시보드 V2 통합 Alpine.js 컴포넌트
 * 모든 대시보드 상태를 관리하며, KPI 스파크라인을 렌더링한다.
 * main_charts.js 등에서 renderTrendChart/renderHourlyChart 를 오버라이드한다.
 */
function compactDashboard() {
    return {
        /* ── 상태 ── */
        kpiList: [
            { key: 'active_blogs',   label: '활성 블로그', value: 0,    delta: null, spark: [] },
            { key: 'today_generate', label: '오늘 생성',   value: 0,    delta: null, spark: [] },
            { key: 'today_publish',  label: '오늘 발행',   value: 0,    delta: null, spark: [] },
            { key: 'success_rate',   label: '성공률',      value: '0%', delta: null, spark: [] },
            { key: 'queue_depth',    label: '대기 큐',     value: 0,    delta: null, spark: [] },
        ],
        trends: { dates: [], generated: [], published: [], republished: [] },
        blogStats: [], hourly: { hours: [], counts: [] },
        statusPct: { generated: 0, published: 0, failed: 0 },
        statusCount: { generated: 0, published: 0, failed: 0 },
        logs: [], contents: [], workers: {}, workerStatus: {}, flowerUrl: '',
        period: '7d', lastUpdated: '',
        _refreshTimer: null, _sparkCharts: {},

        /* ── KPI 확장 + 요약탭 선택 상태 ── */
        kpiExpanded: false,
        allTabs: [
            { key: 'total_blogs', label: '전체 블로그', group: 'blog' },
            { key: 'wordpress', label: '워드프레스', group: 'blog' },
            { key: 'blogger', label: '구글 블로거', group: 'blog' },
            { key: 'active_blogs', label: '활성 블로그', group: 'blog' },
            { key: 'inactive_blogs', label: '비활성 블로그', group: 'blog' },
            { key: 'topics', label: '주제', group: 'category' },
            { key: 'subtopics', label: '하위주제', group: 'category' },
            { key: 'keywords', label: '키워드', group: 'category' },
            // 현재 시스템: 생성/발행/재발행은 GP에 통합 → 별도 모듈 없음.
            // 수집/데이터 모듈은 별도 운영.
            { key: 'total_modules', label: '전체 모듈', group: 'module' },
            { key: 'prompt_modules', label: '프롬프트', group: 'module' },
            { key: 'growth_profile_modules', label: 'GP', group: 'module' },
            { key: 'collect_modules', label: '수집', group: 'module' },
            { key: 'data_modules', label: '데이터', group: 'module' },
            { key: 'total_flows', label: '전체 플로우', group: 'flow' },
            { key: 'active_flows', label: '활성 플로우', group: 'flow' },
            { key: 'inactive_flows', label: '비활성 플로우', group: 'flow' },
            { key: 'week_generate', label: '이번 주 생성', group: 'week' },
            { key: 'week_publish', label: '이번 주 발행', group: 'week' },
            { key: 'week_republish', label: '이번 주 재발행', group: 'week' },
            { key: 'today_generate', label: '오늘 생성', group: 'today' },
            { key: 'today_publish', label: '오늘 발행', group: 'today' },
            { key: 'today_republish', label: '오늘 재발행', group: 'today' },
        ],
        pinnedTabKeys: [],
        stats: {},

        /* ── 문의 수신함 (F10) ── */
        inboxExpanded: false, inboxItems: [], inboxUnreadOnly: false,
        inboxSyncing: false, inboxMsg: '',
        async loadInbox() {
            try {
                const r = await fetch('/api/v1/contact-submissions?unread_only=' + this.inboxUnreadOnly, { credentials: 'include' });
                if (r.ok) { const d = await r.json(); this.inboxItems = d.items || []; this.stats.unread_contacts = d.unread_count ?? this.stats.unread_contacts; }
            } catch (e) { console.error('[inbox]', e); }
        },
        async syncInbox() {
            this.inboxSyncing = true; this.inboxMsg = '';
            try {
                const r = await fetch('/api/v1/contact-submissions/sync', { method: 'POST', credentials: 'include' });
                const d = await r.json();
                this.inboxMsg = d.success ? ('동기화 완료 · 새 문의 ' + (d.new || 0) + '건') : ('동기화 실패: ' + (d.message || ''));
                await this.loadInbox();
            } catch (e) { this.inboxMsg = '동기화 오류'; } finally { this.inboxSyncing = false; }
        },
        async toggleInboxRead(s) {
            try {
                const r = await fetch('/api/v1/contact-submissions/' + s.id + '/read?is_read=' + (!s.is_read), { method: 'POST', credentials: 'include' });
                if (r.ok) { s.is_read = !s.is_read; this.stats.unread_contacts = Math.max(0, (this.stats.unread_contacts || 0) + (s.is_read ? -1 : 1)); }
            } catch (e) { console.error('[inbox]', e); }
        },
        fmtInboxDate(v) { if (!v) return ''; try { return new Date(v).toLocaleString('ko-KR'); } catch (e) { return v; } },

        /* ── 초기화 ── */
        async init() {
            this.loadPinnedTabs();

            // SSR 초기 데이터 즉시 적용 (API 호출 전 KPI 표시)
            if (window.__DASHBOARD_INITIAL__) {
                const initial = window.__DASHBOARD_INITIAL__;
                if (initial.summary) {
                    this.stats = initial.summary;
                    this._updateKPI(initial.summary, this.trends, { total_queued: 0 });
                    this._updateStatus(initial.summary);
                }
                delete window.__DASHBOARD_INITIAL__;
            }

            await this.loadAll();
            this.$nextTick(() => this._renderSparklines());
            this._refreshTimer = setInterval(() => this.loadAll(), 60_000);
            window.addEventListener('beforeunload', () => {
                if (this._refreshTimer) clearInterval(this._refreshTimer);
                Object.values(this._sparkCharts).forEach(c => c?.destroy());
            });
        },

        /* ── 전체 데이터 로드 ── */
        async loadAll() {
            const A = '/api/v1';
            try {
                const [summary, trends, blogStats, hourly, workers, logs, contents, flower] =
                    await Promise.all([
                        this._get(`${A}/dashboard/stats`),
                        this._get(`${A}/dashboard/trends?days=${this._periodDays()}`),
                        this._get(`${A}/dashboard/blog_stats`),
                        this._get(`${A}/dashboard/hourly`),
                        this._get(`${A}/dashboard/celery/workers`),
                        this._get(`${A}/dashboard/logs?limit=8`),
                        this._get(`${A}/generation/content/list?page_size=20`),
                        this._get(`${A}/dashboard/celery/flower-url`),
                    ]);
                this.trends = trends || { dates: [], generated: [], published: [], republished: [] };
                this.blogStats = this._calcBlogPct(blogStats);
                this.hourly = hourly || { hours: [], counts: [] };
                this.workerStatus = workers || {};
                this.workers = (workers && workers.workers) || {};
                this.flowerUrl = (flower && flower.url) || '';
                this.stats = summary || {};
                this.logs = Array.isArray(logs) ? logs : [];
                this.contents = (contents && contents.items) || [];
                this.lastUpdated = new Date().toLocaleTimeString('ko-KR');
                this._updateKPI(summary, this.trends, workers);
                this._updateStatus(summary);
                this.renderTrendChart();
                this.renderHourlyChart();
            } catch (e) {
                console.warn('[Dashboard] loadAll 실패:', e);
            }
        },

        /* ── 기간 전환 ── */
        async switchPeriod(p) {
            this.period = p;
            try {
                const data = await this._get(`/api/v1/dashboard/trends?days=${this._periodDays()}`);
                if (data) { this.trends = data; this.renderTrendChart(); }
            } catch (e) { console.warn(e); }
        },

        /* ── KPI 값 갱신 ── */
        _updateKPI(summary, trends, workers) {
            const s = summary || {};
            const gen = (trends && trends.generated) || [];
            const pub = (trends && trends.published) || [];
            this.kpiList[0].value = s.active_blogs || 0;
            this.kpiList[1].value = s.today_generate || 0;
            this.kpiList[1].delta = gen.length >= 2 ? (gen[gen.length-1]||0) - (gen[gen.length-2]||0) : null;
            this.kpiList[1].spark = gen;
            this.kpiList[2].value = s.today_publish || 0;
            this.kpiList[2].delta = pub.length >= 2 ? (pub[pub.length-1]||0) - (pub[pub.length-2]||0) : null;
            this.kpiList[2].spark = pub;
            const total = (s.today_generate||0) + (s.today_publish||0);
            const failed = s.today_failed || 0;
            this.kpiList[3].value = total > 0 ? ((total-failed)/total*100).toFixed(1)+'%' : '\u2014';
            this.kpiList[4].value = (workers && workers.total_queued) || 0;
        },

        /* ── 콘텐츠 상태 비율 ── */
        _updateStatus(summary) {
            const s = summary || {};
            const gen = s.week_generate||0, pub = s.week_publish||0, fail = s.week_failed||0;
            const total = gen + pub + fail || 1;
            this.statusPct = {
                generated: Math.round(gen/total*100),
                published: Math.round(pub/total*100),
                failed: Math.round(fail/total*100),
            };
            this.statusCount = { generated: gen, published: pub, failed: fail };
        },

        /* ── 블로그 퍼센트 계산 ── */
        _calcBlogPct(stats) {
            if (!stats || !stats.length) return [];
            const max = Math.max(...stats.map(s => s.count||0), 1);
            return stats.map(s => ({ ...s, pct: Math.round((s.count||0)/max*100) }));
        },

        /* ── 스파크라인 렌더링 (ApexCharts) ── */
        _renderSparklines() {
            this.kpiList.forEach(kpi => {
                if (!kpi.spark || kpi.spark.length < 2) return;
                const el = document.getElementById(`spark-${kpi.key}`);
                if (!el) return;
                if (this._sparkCharts[kpi.key]) this._sparkCharts[kpi.key].destroy();
                // CSS 변수 기반 테마 색상 (success_rate는 경고색 유지)
                const _cs = getComputedStyle(document.documentElement);
                const color = kpi.key === 'success_rate' ? '#993C1D' : (_cs.getPropertyValue('--color-primary').trim() || '#0F6E56');
                this._sparkCharts[kpi.key] = new ApexCharts(el, {
                    chart: { type: 'line', sparkline: { enabled: true }, height: 30 },
                    series: [{ data: kpi.spark }],
                    stroke: { width: 1.5, curve: 'smooth' },
                    colors: [color],
                    tooltip: { enabled: false },
                });
                this._sparkCharts[kpi.key].render();
            });
        },

        /* ── fetch 래퍼 ── */
        async _get(url) {
            const r = await fetch(url, { credentials: 'include' });
            return r.ok ? r.json() : null;
        },

        /* ── 기간 일수 변환 ── */
        _periodDays() {
            return this.period === '90d' ? 90 : this.period === '30d' ? 30 : 7;
        },

        /* ── 요약탭 핀 관리 ── */
        loadPinnedTabs() {
            try {
                const saved = localStorage.getItem('dashboard_pinned_tabs');
                this.pinnedTabKeys = saved
                    ? JSON.parse(saved)
                    : ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
            } catch {
                this.pinnedTabKeys = ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
            }
        },
        isTabPinned(key) { return this.pinnedTabKeys.includes(key); },
        togglePinTab(key) {
            if (this.isTabPinned(key)) {
                this.pinnedTabKeys = this.pinnedTabKeys.filter(k => k !== key);
            } else {
                this.pinnedTabKeys.push(key);
            }
            localStorage.setItem('dashboard_pinned_tabs', JSON.stringify(this.pinnedTabKeys));
        },

        /* ── 워커/큐 표시 헬퍼 ── */
        getWorkerLabel(key) {
            return { generation: 'Generation', publish: 'Publish', utility: 'Utility' }[key] || key;
        },
        getWorkerDotClass(key) {
            const w = this.workers?.[key];
            if (!w || w.status === 'unknown') return 'bg-gray-400';
            if (w.status === 'offline') return 'bg-red-400';
            if (w.active_tasks > 0) return 'bg-blue-400 animate-pulse';
            return 'bg-green-400';
        },
        getDisplayQueues() {
            const exclude = ['callback_queue', 'image_queue'];
            const queues = this.workerStatus?.queues || {};
            return Object.entries(queues)
                .filter(([name]) => !exclude.includes(name))
                .map(([name, count]) => ({ name, count: Math.max(count || 0, 0) }));
        },

        /* ── 시간 포매터 ── */
        formatTime(ts) {
            if (!ts) return '';
            const d = new Date(ts);
            return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        },

        /* 플레이스홀더: main_charts.js 에서 오버라이드 */
        renderTrendChart() {},
        renderHourlyChart() {},
    };
}
