/**
 * 니치 도메인 화면 — 옛 'URL 수집' 탭의 대체.
 *
 * URL 개별 행은 소비되지 않았다(처리율 0.02%). 남길 가치가 있는 것은
 * "이 니치에서 누가 상위에 있는가" 라는 도메인 단위 정보다.
 * 여기서 끈 도메인은 제목 각도 조회에서 빠진다.
 *
 * 계획서: docs/plans/title_pipeline_redesign_plan.md §2-3
 */
function nicheDomainApp() {
    return {
        items: [],
        total: 0,
        page: 1,
        size: 20,
        pages: 1,
        loading: false,
        message: '',
        messageType: 'info',

        search: '',
        platform: '',
        activeFilter: '',
        selected: [],
        sortField: 'url_count',
        sortDir: 'desc',
        stats: { total: 0, active: 0, urls_summarized: 0 },

        async init() {
            await Promise.all([this.loadStats(), this.load()]);
        },

        async loadStats() {
            const d = await this.get('/api/v1/data/domains/stats');
            if (d) this.stats = d;
        },

        async load() {
            this.loading = true;
            const q = new URLSearchParams({
                page: this.page, size: this.size,
                sort_field: this.sortField, sort_dir: this.sortDir,
            });
            if (this.search) q.set('search', this.search);
            if (this.platform) q.set('platform', this.platform);
            if (this.activeFilter) q.set('is_active', this.activeFilter);

            const d = await this.get(`/api/v1/data/domains?${q}`);
            this.loading = false;
            if (!d) return;
            this.items = d.items || [];
            this.total = d.total || 0;
            this.pages = Math.max(1, Math.ceil(this.total / this.size));
            this.selected = [];
        },

        reload() {
            this.page = 1;
            this.load();
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
            this.reload();
        },

        toggleAll(event) {
            this.selected = event.target.checked
                ? this.items.map((row) => row.id) : [];
        },

        async toggle(row) {
            const d = await this.post(`/api/v1/data/domains/${row.id}/toggle`);
            if (!d) return;
            row.is_active = d.is_active;
            await this.loadStats();
        },

        async bulkToggle(active) {
            if (!this.selected.length) return;
            const d = await this.post(
                `/api/v1/data/domains/bulk-toggle?active=${active}`,
                { ids: this.selected });
            if (!d) return;
            this.show(`${d.updated}개 도메인을 ${active ? '참조' : '제외'}로 바꿨습니다`);
            await Promise.all([this.loadStats(), this.load()]);
        },

        async removeSelected() {
            if (!this.selected.length) return;
            if (!confirm(`${this.selected.length}개 도메인을 삭제할까요?\n`
                + '다시 관측되면 새로 쌓입니다.')) return;
            const d = await this.post('/api/v1/data/domains/bulk-delete',
                                      { ids: this.selected });
            if (!d) return;
            this.show(`${d.deleted}개 삭제했습니다`);
            await Promise.all([this.loadStats(), this.load()]);
        },

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
