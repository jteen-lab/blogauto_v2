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

        async init() {
            await Promise.all([this.loadStats(), this.load()]);
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

        statCards() {
            const s = this.stats;
            return [
                { label: '전체', value: s.total || 0, filter: {},
                  tone: 'border-gray-200 hover:bg-gray-50' },
                { label: '미분류', value: s.unclassified || 0,
                  filter: { classified: 'false' },
                  tone: 'border-amber-200 hover:bg-amber-50' },
                { label: '미측정', value: s.unmeasured || 0,
                  filter: { measured: 'false' },
                  tone: 'border-sky-200 hover:bg-sky-50' },
                { label: '채택', value: (s.by_verdict || {}).adopt || 0,
                  filter: { verdict: 'adopt' },
                  tone: 'border-green-200 hover:bg-green-50' },
                { label: '제외', value: (s.by_verdict || {}).reject || 0,
                  filter: { verdict: 'reject' },
                  tone: 'border-red-200 hover:bg-red-50' },
            ];
        },

        applyQuickFilter(filter) {
            this.filters = { verdict: '', classified: '', measured: '',
                             ...filter };
            this.page = 1;
            this.load();
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

        // ── 작업 ─────────────────────────────────────────
        async runClassify() {
            this.busy = 'classify';
            const d = await this.post('/api/v1/data/keyword-pool/classify',
                { limit: 2000 });
            this.busy = '';
            if (!d) return;
            this.show(`분류: 훑음 ${d.scanned}건 · 매칭 ${d.matched}건 · `
                + `여전히 미분류 ${d.unmatched ?? 0}건`);
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
                this.show(`측정: 검색량 보강 ${r.enriched}건 · 공급 측정 ${r.measured}건`
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
