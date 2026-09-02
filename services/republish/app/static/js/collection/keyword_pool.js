/**
 * 수집 키워드 풀(정본) 화면.
 *
 * 자동 모듈이 하는 일을 사람이 같은 API 로 직접 돌린다.
 * 측정은 오래 걸려 프록시가 끊으므로 토큰을 받아 폴링한다.
 *
 * 계획서: docs/plans/keyword_pipeline_restructure_review.md §5-1
 */
function keywordPoolApp() {
    return {
        items: [],
        total: 0,
        page: 1,
        size: 50,
        pages: 1,
        loading: false,
        busy: '',
        elapsed: 0,
        message: '',
        messageType: 'info',
        search: '',
        selected: [],
        sortField: 'created_at',
        sortDir: 'desc',
        filters: { verdict: '', classified: '', measured: '' },
        stats: { total: 0, unmeasured: 0, unclassified: 0, no_volume: 0,
                 by_verdict: {} },
        th: { min_volume: 100, max_volume: 100000, min_saturation: 0.2 },
        measureLimit: 50,

        // 수동 수집 — 자동 모듈과 같은 실행기를 손으로 돌린다
        collectForm: {
            seeds: '', modifiers: '방법, 추천, 후기, 비교, 초보',
            src_google_trending: false, src_naver_suggest: false,
            src_google_suggest: false, niche_filter: true, limit: 100,
        },
        collectResult: null,

        // 노출 설정 — /keyword-lab 화면에서 이관
        blogs: [],
        blogId: '',
        engines: ['google'],
        engineWarnings: [],
        readiness: null,

        async init() {
            await Promise.all([this.loadStats(), this.load(), this.loadBlogs()]);
        },

        engineLabel(code) {
            return { google: '구글', naver: '네이버', bing: '빙' }[code] || code;
        },

        stateIcon(state) {
            return { ok: '✅', warn: '⚠️', fail: '❌' }[state] || '❔';
        },

        async loadBlogs() {
            const d = await this.get('/api/v1/blogs?size=100');
            this.blogs = (d && (d.items || d.blogs || d)) || [];
        },

        async loadEngines() {
            this.readiness = null;
            if (!this.blogId) return;
            const d = await this.get(
                `/api/v1/keyword-lab/engines/${this.blogId}`);
            if (!d) return;
            this.engines = d.engines || ['google'];
            this.engineWarnings = d.warnings || [];
        },

        async saveEngines() {
            if (!this.blogId) return;
            try {
                const r = await fetch(
                    `/api/v1/keyword-lab/engines/${this.blogId}`, {
                        method: 'PUT', credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ engines: this.engines }),
                    });
                const text = await r.text();
                if (!r.ok) throw new Error(this.detail(text, r.status));
                const d = JSON.parse(text);
                this.engines = d.engines || [];
                this.engineWarnings = d.warnings || [];
                this.show('노출 목표를 저장했습니다');
            } catch (e) {
                this.show(e.message, 'error');
            }
        },

        async loadReadiness() {
            if (!this.blogId) return;
            this.busy = 'readiness';
            this.readiness = await this.get(
                `/api/v1/keyword-lab/readiness/${this.blogId}`);
            this.busy = '';
        },

        async collectFeedback() {
            if (!this.blogId) return;
            this.busy = 'feedback';
            const d = await this.post('/api/v1/keyword-lab/feedback',
                { blog_id: Number(this.blogId) });
            this.busy = '';
            if (!d) return;
            this.show(d.message
                || `실측 ${d.rows}행 · 매칭 ${d.matched} · 노출없음 ${d.zeroed}`);
            await this.load();
        },

        num(v) {
            return (v === null || v === undefined) ? '-' : v.toLocaleString();
        },

        verdictLabel(v) {
            return { adopt: '채택', hold: '보류', pending: '미측정',
                     reject: '제외' }[v] || v;
        },

        verdictTone(v) {
            return {
                adopt: 'bg-green-100 text-green-700',
                hold: 'bg-amber-100 text-amber-700',
                pending: 'bg-gray-100 text-gray-600',
                reject: 'bg-red-100 text-red-700',
            }[v] || 'bg-gray-100 text-gray-600';
        },

        // 카드가 곧 필터다. 같은 조건을 카드와 드롭다운 두 군데서 고르면
        // 어느 쪽이 지금 걸려 있는지 알 수 없고, 판정의 '미측정'(pending)과
        // 측정 여부의 '미측정'이 같은 말로 보여 더 헷갈렸다.
        statCards() {
            const s = this.stats;
            const v = s.by_verdict || {};
            return [
                { key: 'all', label: '전체', value: s.total || 0, patch: null,
                  tone: 'border-gray-200 hover:bg-gray-50',
                  activeTone: 'border-gray-400 bg-gray-50' },
                { key: 'unclassified', label: '미분류',
                  value: s.unclassified || 0, patch: ['classified', 'false'],
                  tone: 'border-amber-200 hover:bg-amber-50',
                  activeTone: 'border-amber-500 bg-amber-50' },
                { key: 'unmeasured', label: '미측정',
                  value: s.unmeasured || 0, patch: ['measured', 'false'],
                  tone: 'border-sky-200 hover:bg-sky-50',
                  activeTone: 'border-sky-500 bg-sky-50' },
                { key: 'adopt', label: '채택', value: v.adopt || 0,
                  patch: ['verdict', 'adopt'],
                  tone: 'border-green-200 hover:bg-green-50',
                  activeTone: 'border-green-500 bg-green-50' },
                { key: 'hold', label: '보류', value: v.hold || 0,
                  patch: ['verdict', 'hold'],
                  tone: 'border-orange-200 hover:bg-orange-50',
                  activeTone: 'border-orange-500 bg-orange-50' },
                { key: 'reject', label: '제외', value: v.reject || 0,
                  patch: ['verdict', 'reject'],
                  tone: 'border-red-200 hover:bg-red-50',
                  activeTone: 'border-red-500 bg-red-50' },
            ];
        },

        isCardActive(card) {
            if (!card.patch) {
                return !this.filters.verdict && !this.filters.classified
                    && !this.filters.measured;
            }
            const [key, value] = card.patch;
            return this.filters[key] === value;
        },

        toggleCard(card) {
            if (!card.patch) {
                this.filters = { verdict: '', classified: '', measured: '' };
            } else {
                const [key, value] = card.patch;
                // 같은 걸 다시 누르면 해제. 판정은 서로 배타적이라 교체된다.
                this.filters[key] = this.filters[key] === value ? '' : value;
            }
            this.page = 1;
            this.load();
        },

        activeChips() {
            return this.statCards().filter(c => c.patch && this.isCardActive(c));
        },

        async loadStats() {
            const d = await this.get('/api/v1/data/keyword-pool/stats');
            if (d) this.stats = d;
        },

        async load() {
            this.loading = true;
            const q = new URLSearchParams({
                page: this.page, size: this.size,
                sort_field: this.sortField, sort_dir: this.sortDir,
            });
            if (this.search) q.set('search', this.search);
            if (this.filters.verdict) q.set('verdict', this.filters.verdict);
            if (this.filters.classified) q.set('classified', this.filters.classified);
            if (this.filters.measured) q.set('measured', this.filters.measured);

            const d = await this.get(`/api/v1/data/keyword-pool?${q}`);
            this.loading = false;
            if (!d) return;
            this.items = d.items || [];
            this.total = d.total || 0;
            this.pages = d.pages || 1;
            this.selected = [];
        },

        go(page) {
            if (page < 1 || page > this.pages) return;
            this.page = page;
            this.load();
        },

        sort(field) {
            if (this.sortField === field) {
                this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortDir = 'desc';
            }
            this.load();
        },

        toggleAll(event) {
            this.selected = event.target.checked
                ? this.items.map(r => r.id) : [];
        },

        // ── 수집 ─────────────────────────────────────────
        async runCollect() {
            const f = this.collectForm;
            const split = (t) => (t || '').split(',')
                .map(x => x.trim()).filter(Boolean);
            const sources = ['naver_ads'];
            if (f.src_google_trending) sources.push('google_trending');
            if (f.src_naver_suggest) sources.push('naver_suggest');
            if (f.src_google_suggest) sources.push('google_suggest');

            this.busy = 'collect';
            this.elapsed = 0;
            this.collectResult = null;
            try {
                // 모듈과 같은 실행기·같은 설정 모양을 쓴다
                const started = await this.post('/api/v1/keyword-lab/run', {
                    settings_override: {
                        keyword: {
                            enabled: true,
                            seeds: split(f.seeds),
                            modifiers: split(f.modifiers),
                            use_blog_categories: false,
                            sources: sources,
                            discovery_niche_filter: !!f.niche_filter,
                            collect_limit: f.limit,
                            make_titles: false,
                        },
                    },
                    steps: ['collect'],
                    force: true,
                    background: true,
                });
                if (!started) return;
                this.collectResult = await this.pollRun(started.task_id);
                const blocked = this.collectResult?.blocked || 0;
                if (blocked) {
                    this.show(`금지어 필터로 ${blocked}건을 걸렀습니다`);
                }
                await Promise.all([this.loadStats(), this.load()]);
            } catch (e) {
                this.show(e.message, 'error');
            } finally {
                this.busy = '';
            }
        },

        async pollRun(taskId, maxSeconds = 900) {
            const step = 2000;
            for (let waited = 0; waited < maxSeconds * 1000; waited += step) {
                await new Promise(res => setTimeout(res, step));
                this.elapsed = Math.round(waited / 1000);
                let row;
                try {
                    const res = await fetch(
                        `/api/v1/keyword-lab/run/${taskId}`,
                        { credentials: 'include' });
                    const text = await res.text();
                    row = text ? JSON.parse(text) : { status: 'running' };
                } catch (e) { continue; }
                if (row.status === 'done') return row.result;
                if (row.status === 'failed') throw new Error(row.error || '수집 실패');
            }
            throw new Error('시간이 너무 오래 걸립니다');
        },

        // ── 작업 ─────────────────────────────────────────
        async runClassify(retryAll = false) {
            this.busy = 'classify';
            const d = await this.post('/api/v1/data/keyword-pool/classify',
                { limit: 2000, retry_all: !!retryAll });
            this.busy = '';
            if (!d) return;
            if (d.message) {
                // 더 훑을 게 없다 — 왜 안 줄어드는지 말해 준다
                this.show(d.message);
            } else {
                this.show(`분류: 훑음 ${d.scanned.toLocaleString()}건 · `
                    + `카테고리 붙음 ${d.matched.toLocaleString()}건 · `
                    + `못 붙음 ${d.unmatched.toLocaleString()}건 · `
                    + `아직 안 훑은 ${d.remaining.toLocaleString()}건`);
            }
            await Promise.all([this.loadStats(), this.load()]);
        },

        async runRejudge() {
            this.busy = 'rejudge';
            const d = await this.post('/api/v1/data/keyword-pool/rejudge', this.th);
            this.busy = '';
            if (!d) return;
            const v = d.by_verdict || {};
            this.show(`재판정 ${d.total}건 → 채택 ${v.adopt || 0} · `
                + `보류 ${v.hold || 0} · 미측정 ${v.pending || 0} · 제외 ${v.reject || 0}`);
            await Promise.all([this.loadStats(), this.load()]);
        },

        async runMeasure() {
            this.busy = 'measure';
            this.elapsed = 0;
            const started = await this.post('/api/v1/data/keyword-pool/measure',
                { limit: this.measureLimit, ...this.th });
            if (!started) { this.busy = ''; return; }
            try {
                const r = await this.poll(started.task_id);
                this.show(`측정: 검색량 보강 ${r.enriched}건 · 공급(발행량) 측정 ${r.measured}건`
                    + (r.error ? ` · ⚠ ${r.error}` : '')
                    + ` · 남은 ${r.remaining.toLocaleString()}건`);
                await Promise.all([this.loadStats(), this.load()]);
            } catch (e) {
                this.show(e.message, 'error');
            } finally {
                this.busy = '';
            }
        },

        async poll(taskId, maxSeconds = 900) {
            const step = 2000;
            for (let waited = 0; waited < maxSeconds * 1000; waited += step) {
                await new Promise(res => setTimeout(res, step));
                this.elapsed = Math.round(waited / 1000);
                let row;
                try {
                    const res = await fetch(
                        `/api/v1/data/keyword-pool/task/${taskId}`,
                        { credentials: 'include' });
                    const text = await res.text();
                    row = text ? JSON.parse(text) : { status: 'running' };
                } catch (e) { continue; }
                if (row.status === 'done') return row.result;
                if (row.status === 'failed') throw new Error(row.error || '측정 실패');
            }
            throw new Error('시간이 너무 오래 걸립니다');
        },

        async removeSelected() {
            if (!this.selected.length) return;
            if (!confirm(`${this.selected.length}개를 삭제할까요?`)) return;
            const d = await this.post('/api/v1/data/keyword-pool/delete',
                { ids: this.selected });
            if (!d) return;
            this.show(`${d.deleted}개 삭제`);
            await Promise.all([this.loadStats(), this.load()]);
        },

        // ── 통신 ─────────────────────────────────────────
        show(text, type = 'info') {
            this.message = text;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 8000);
        },

        async get(url) {
            try {
                const r = await fetch(url, { credentials: 'include' });
                const text = await r.text();
                if (!r.ok) throw new Error(this.detail(text, r.status));
                return text ? JSON.parse(text) : null;
            } catch (e) {
                this.show(e.message, 'error');
                return null;
            }
        },

        async post(url, body) {
            try {
                const r = await fetch(url, {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body || {}),
                });
                const text = await r.text();
                if (!r.ok) throw new Error(this.detail(text, r.status));
                // 빈 본문이면 JSON.parse 가 원인 모를 오류를 던진다
                if (!text) throw new Error('서버가 빈 응답을 돌려줬습니다');
                return JSON.parse(text);
            } catch (e) {
                this.show(e.message, 'error');
                return null;
            }
        },

        detail(text, status) {
            try { return JSON.parse(text).detail || `요청 실패 (${status})`; }
            catch (e) { return `요청 실패 (${status})`; }
        },
    };
}
