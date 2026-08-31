/**
 * 키워드 관리(실험실).
 *
 * 수집(①)과 측정(②)을 나눈 이유: 검색광고 API 는 시드 5개씩 한 번에
 * 처리되지만 문서수는 키워드마다 한 번씩 호출해야 한다. 한 요청에 묶으면
 * 타임아웃이 나고, 중간에 끊기면 무엇까지 쟀는지 알 수 없다.
 *
 * 순서도: docs/flowcharts/keyword_lab.md
 */
function keywordLabApp() {
    return {
        // 목록 선택(탭별 독립) — components/list_selection.js
        ...listSelectionMixin(),

        blogs: [],
        blogId: '',
        modules: [],
        moduleId: '',
        seeds: [],
        seedText: '',
        candidates: [],
        counts: {},
        apiStatus: { naver_ads: false, naver_search: false },

        verdictTab: 'adopt',
        search: '',
        listSortKey: 'search_volume',
        listSortDir: 'desc',

        minVolume: 100,
        minSaturation: 0.2,

        busy: '',
        message: '',
        messageType: 'success',
        // 실패 사유는 토스트가 아니라 화면에 남긴다 — 토스트는 5초 뒤
        // 사라져서 무엇을 고쳐야 하는지 다시 볼 수 없다.
        failure: '',
        connTest: null,

        async init() {
            await Promise.all([
                this.loadBlogs(), this.loadStatus(), this.loadCandidates(),
                this.loadModules(),
            ]);
        },

        // ── 로드 ──────────────────────────────────────────
        async loadBlogs() {
            try {
                const r = await fetch('/api/v1/blogs?limit=100',
                    { credentials: 'include' });
                const d = await r.json();
                this.blogs = d.blogs || d || [];
            } catch (e) { this.blogs = []; }
        },

        async loadModules() {
            try {
                const r = await fetch('/api/v1/keyword-lab/modules',
                    { credentials: 'include' });
                if (r.ok) this.modules = (await r.json()).modules || [];
            } catch (e) { this.modules = []; }
        },

        /** 자동 실행과 **같은 실행기**를 부른다 — 수집·측정·제목을 한 번에. */
        async runModule() {
            this.busy = 'run';
            this.failure = '';
            try {
                const body = {
                    module_id: this.moduleId ? Number(this.moduleId) : null,
                    blog_id: this.blogId ? Number(this.blogId) : null,
                    force: true,
                };
                // 모듈을 안 고르면 화면 값으로 임시 설정을 만들어 돌린다.
                if (!this.moduleId) {
                    body.settings_override = {
                        keyword: {
                            enabled: true,
                            seeds: this.normalizeSeeds(this.seedText),
                            use_blog_categories: !!this.blogId,
                            min_volume: this.minVolume,
                            min_saturation: this.minSaturation,
                        },
                    };
                }
                const r = await fetch('/api/v1/keyword-lab/run', {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const d = await r.json();
                if (!r.ok) {
                    this.failure = d.detail || '실행 실패';
                    this.show('실행하지 못했습니다', 'error');
                    return;
                }
                if (d.skipped) { this.show(d.message || '건너뜀'); return; }
                const c = d.collect || {}, m = d.measure || {}, t = d.titles || {};
                this.show(
                    `수집 ${c.saved || 0} · 측정 ${m.measured || 0} · 제목 ${t.made || 0}편`);
                await this.loadCandidates();
                this.verdictTab = 'adopt';
            } catch (e) {
                this.failure = '실행 중 오류가 발생했습니다';
            } finally { this.busy = ''; }
        },

        async loadStatus() {
            try {
                const r = await fetch('/api/v1/keyword-lab/status',
                    { credentials: 'include' });
                if (r.ok) this.apiStatus = await r.json();
            } catch (e) { /* 화면 경고만 못 띄운다 */ }
        },

        async loadSeeds() {
            this.seeds = [];
            if (!this.blogId) return;
            try {
                const r = await fetch(
                    `/api/v1/keyword-lab/seeds/${this.blogId}`,
                    { credentials: 'include' });
                if (r.ok) this.seeds = (await r.json()).seeds || [];
            } catch (e) { /* 미리보기일 뿐이라 조용히 넘긴다 */ }
        },

        async loadCandidates() {
            try {
                const r = await fetch('/api/v1/keyword-lab/candidates?limit=1000',
                    { credentials: 'include' });
                const d = await r.json();
                this.candidates = d.candidates || [];
                this.counts = d.counts || {};
            } catch (e) { this.candidates = []; }
        },

        // ── 실행 ──────────────────────────────────────────
        async collect() {
            // 네이버는 공백·가운뎃점이 든 키워드를 거부한다(400, 11001).
            // 서버에서도 다듬지만, 입력 단계에서 정리해 두면 사용자가
            // 무엇이 실제로 나가는지 보고 고칠 수 있다.
            const manual = this.normalizeSeeds(this.seedText);
            if (manual.length) this.seedText = manual.join(', ');
            if (!this.blogId && !manual.length) {
                this.show('블로그를 고르거나 시드를 입력하세요', 'error');
                return;
            }
            this.busy = 'collect';
            try {
                const r = await fetch('/api/v1/keyword-lab/collect', {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        blog_id: this.blogId ? Number(this.blogId) : null,
                        seeds: manual, limit: 200,
                    }),
                });
                const d = await r.json();
                if (!r.ok) {
                    this.failure = d.detail || '수집 실패';
                    this.show('수집하지 못했습니다', 'error');
                    return;
                }
                this.failure = '';
                this.show(
                    `${d.saved}개 수집 (중복 ${d.skipped} 제외, API ${d.api_calls}회)`);
                await this.loadCandidates();
                this.verdictTab = 'pending';
            } catch (e) {
                this.show('수집 중 오류가 발생했습니다', 'error');
            } finally { this.busy = ''; }
        },

        async measure() {
            this.busy = 'measure';
            try {
                const r = await fetch('/api/v1/keyword-lab/measure', {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        blog_id: this.blogId ? Number(this.blogId) : null,
                        limit: 50,
                        min_volume: this.minVolume,
                        min_saturation: this.minSaturation,
                    }),
                });
                const d = await r.json();
                if (!r.ok) { this.show(d.detail || '측정 실패', 'error'); return; }
                this.show(
                    `${d.measured}건 측정`
                    + (d.failed ? ` / 실패 ${d.failed}` : '')
                    + (d.remaining ? ` — 남은 ${d.remaining}건은 다시 누르세요` : ''));
                await this.loadCandidates();
                if (!d.remaining) this.verdictTab = 'adopt';
            } catch (e) {
                this.show('측정 중 오류가 발생했습니다', 'error');
            } finally { this.busy = ''; }
        },

        async rejudge() {
            this.busy = 'rejudge';
            try {
                const r = await fetch('/api/v1/keyword-lab/rejudge', {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        min_volume: this.minVolume,
                        min_saturation: this.minSaturation,
                    }),
                });
                const d = await r.json();
                this.show(`${d.total}건 재판정 — 채택 ${d.adopted}건`);
                await this.loadCandidates();
            } catch (e) {
                this.show('재판정 실패', 'error');
            } finally { this.busy = ''; }
        },

        async deleteSelected(scope, rows) {
            const targets = this.listSelectedRows(scope, rows);
            if (!targets.length) return;
            if (!confirm(`키워드 후보 ${targets.length}개를 삭제합니다.`)) return;
            try {
                const r = await fetch('/api/v1/keyword-lab/candidates', {
                    method: 'DELETE', credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: targets.map(t => t.id) }),
                });
                const d = await r.json();
                this.listClearSelection(scope);
                this.show(`${d.deleted}개 삭제`);
                await this.loadCandidates();
            } catch (e) { this.show('삭제 실패', 'error'); }
        },

        /** 서버와 같은 규칙으로 시드를 다듬는다(naver_ads_service.normalize_hints). */
        normalizeSeeds(text) {
            const out = [], seen = new Set();
            for (const raw of (text || '').split(',')) {
                for (const part of raw.split(/[·/|~\-]+/)) {
                    const kw = part.replace(/[^0-9A-Za-z가-힣]/g, '');
                    if (kw && !seen.has(kw)) { seen.add(kw); out.push(kw); }
                }
            }
            return out;
        },

        async testConnection() {
            this.busy = 'conn';
            this.connTest = null;
            try {
                const r = await fetch('/api/v1/keyword-lab/test-connection', {
                    method: 'POST', credentials: 'include',
                });
                const d = await r.json();
                if (!r.ok) { this.failure = d.detail || '연결 테스트 실패'; return; }
                this.connTest = d;
                this.failure = '';
            } catch (e) {
                this.failure = '연결 테스트 중 오류가 발생했습니다';
            } finally { this.busy = ''; }
        },

        connRows() {
            if (!this.connTest) return [];
            const t = this.connTest;
            return [
                { name: '검색광고 (연관키워드·검색량)',
                  ok: t.naver_ads?.ok,
                  message: t.naver_ads?.ok ? '정상' : (t.naver_ads?.error || '') },
                { name: '검색 API (문서수)',
                  ok: t.naver_search?.ok,
                  message: t.naver_search?.ok ? '정상' : (t.naver_search?.error || '') },
            ];
        },

        // ── 표 ────────────────────────────────────────────
        byVerdict(v) {
            return this.candidates.filter(c => c.verdict === v);
        },

        visibleCandidates(v) {
            const q = (this.search || '').trim().toLowerCase();
            const rows = this.byVerdict(v).filter(c => !q
                || (c.keyword || '').toLowerCase().includes(q)
                || (c.niche || '').toLowerCase().includes(q));
            const dir = this.listSortDir === 'asc' ? 1 : -1;
            return [...rows].sort((a, b) => {
                const va = this.sortValue(a), vb = this.sortValue(b);
                if (va === vb) return 0;
                return va > vb ? dir : -dir;
            });
        },

        sortValue(row) {
            const k = this.listSortKey;
            // 문자 열은 문자로, 수치 열은 수치로 비교한다. 섞으면
            // '10' 이 '9' 보다 앞에 온다.
            if (k === 'keyword' || k === 'niche' || k === 'competition') {
                return (this.listCell(row, k) || '').toLowerCase();
            }
            const v = row[k];
            return v === null || v === undefined ? -1 : v;
        },

        listColumns() {
            return [
                { key: 'keyword',       label: '키워드', width: '24%', strong: true, sortable: true },
                { key: 'search_volume', label: '검색량', width: '11%', align: 'right', sortable: true },
                { key: 'doc_count',     label: '문서수', width: '11%', align: 'right', sortable: true },
                { key: 'saturation',    label: '포화도', width: '10%', align: 'right', sortable: true },
                { key: 'competition',   label: '경쟁',   width: '8%',  sortable: true },
                { key: '_badges',       label: '판정',   width: '18%' },
                // 입력한 시드가 아니라 이 키워드가 분류된 카테고리다.
                { key: 'niche',         label: '니치',   width: '18%', sortable: true },
            ];
        },

        listCell(row, key) {
            switch (key) {
                case 'keyword': return row.keyword || '';
                case 'search_volume':
                    return row.search_volume === null || row.search_volume === undefined
                        ? '-' : row.search_volume.toLocaleString();
                case 'doc_count':
                    return row.doc_count === null || row.doc_count === undefined
                        ? '미측정' : row.doc_count.toLocaleString();
                case 'saturation':
                    return row.saturation === null || row.saturation === undefined
                        ? '-' : row.saturation.toFixed(2);
                case 'competition': return row.competition || '-';
                case 'niche': return row.niche || '미분류';
                default: return '';
            }
        },

        listBadges(row) {
            const out = [];
            const map = {
                adopt:   ['채택', 'bg-green-50 text-green-700 border border-green-200'],
                hold:    ['보류', 'bg-amber-50 text-amber-700 border border-amber-200'],
                pending: ['미측정', 'bg-gray-100 text-gray-600 border border-gray-200'],
                reject:  ['제외', 'bg-red-50 text-red-700 border border-red-200'],
            };
            const m = map[row.verdict];
            if (m) out.push({ label: m[0], cls: m[1], tip: row.verdict_reason || '' });
            if (row.risk_label) {
                out.push({
                    label: row.risk_label,
                    cls: 'bg-orange-50 text-orange-700 border border-orange-200',
                    tip: '확인 불가한 정보가 핵심인 유형 — 사람이 판단해야 한다',
                });
            }
            return out;
        },

        listTitle(row) { return row.keyword || ''; },

        listSub(row) {
            const parts = [];
            parts.push(`검색 ${row.search_volume ?? '-'}`);
            parts.push(`문서 ${row.doc_count === null || row.doc_count === undefined
                ? '미측정' : row.doc_count.toLocaleString()}`);
            if (row.niche) parts.push(row.niche);
            if (row.verdict_reason) parts.push(row.verdict_reason);
            return parts.join(' · ');
        },

        listSort(key) {
            if (this.listSortKey === key) {
                this.listSortDir = this.listSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.listSortKey = key;
                // 수치는 큰 것부터 보는 편이 쓸모 있다.
                const textual = ['keyword', 'niche', 'competition'];
                this.listSortDir = textual.includes(key) ? 'asc' : 'desc';
            }
        },

        listSortIcon(key) {
            if (this.listSortKey !== key) return '↕';
            return this.listSortDir === 'asc' ? '▲' : '▼';
        },

        show(text, type = 'success') {
            this.message = text;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 5000);
        },
    };
}
