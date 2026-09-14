/**
 * 작업대 — 모듈을 올려놓고 돌려본 뒤, 반영할지 버릴지 정한다.
 *
 * 실행은 리허설이다: 서버가 실제 발행 길을 그대로 돌리되 마지막에
 * 되돌린다. 반영 버튼을 눌러야만 실제 데이터에 들어간다.
 *
 * 단계 연결: 앞 단계에서 체크한 것이 다음 단계 실행의 입력이 된다.
 *   키워드 선택 → 제목 생성이 그 키워드를 채택된 것처럼 쓴다
 *   제목 선택   → 글 생성이 그 제목으로 만든다 (회차당 3편 상한)
 *   소스 질문   → 글 생성이 질문 제목으로 만든다
 *
 * 계획서: docs/plans/test_workbench_plan.md
 */
function workbench() {
    return {
        // ── 상태 ─────────────────────────────────────────────
        catalog: { modules: {}, blogs: [] },
        blogId: null,
        steps: [],           // {uid,type,moduleId,moduleName,outcome,filter,running,applying,applyMessage}
        typeOrder: ['keyword', 'title_gen', 'data', 'generate'],
        typeLabel: {
            keyword: '키워드', title_gen: '제목 생성/수집',
            data: '제목 이관', generate: '글 생성', prompt: '글 생성',
        },
        sourceQuery: '', sourceItems: [], sourceError: '', sourceLoading: false,
        preview: { title: '', html: '', imageUrl: null, fromStep: null },
        previewCss: '', editMode: false, postMessage: '',
        presets: [], presetPick: '',
        _uid: 0,

        async init() {
            await Promise.all([this.loadCatalog(), this.loadPresets()]);
        },

        async _json(url, opts) {
            const res = await fetch(url, Object.assign({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }, opts || {}));
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || ('HTTP ' + res.status));
            }
            return res.json();
        },

        async loadCatalog() {
            try { this.catalog = await this._json('/api/v1/workbench/catalog'); }
            catch (e) { console.error('카탈로그 로드 실패:', e); }
        },

        async loadPreviewCss() {
            this.previewCss = '';
            if (!this.blogId) return;
            try {
                const got = await this._json(
                    '/api/v1/workbench/preview-css?blog_id=' + this.blogId);
                this.previewCss = got.css || '';
            } catch (e) { console.error('미리보기 CSS 실패:', e); }
        },

        // ── 단계 구성 ────────────────────────────────────────
        addStep(type) {
            const sel = document.getElementById('pick-' + type);
            const moduleId = sel ? parseInt(sel.value, 10) : NaN;
            if (!Number.isInteger(moduleId)) {
                alert('담을 모듈이 없습니다. 먼저 ' + this.typeLabel[type]
                      + ' 모듈을 만들어 두세요.');
                return;
            }
            const name = (this.catalog.modules[type] || [])
                .find(m => m.id === moduleId)?.name || '';
            this.steps.push({
                uid: ++this._uid, type, moduleId, moduleName: name,
                outcome: null, filter: 'all',
                running: false, applying: false, applyMessage: '',
            });
        },

        // ── 실행 ─────────────────────────────────────────────
        async runStep(i) {
            const s = this.steps[i];
            if (s.running) return;
            const payload = {
                module_type: s.type === 'prompt' ? 'generate' : s.type,
                module_id: s.moduleId,
                blog_id: this.blogId,
            };
            // 앞 단계 선택 → 이번 실행의 입력
            const prev = i > 0 ? this.steps[i - 1] : null;
            const picked = prev ? this.selectedOf(i - 1) : [];
            if (picked.length && prev.type === 'keyword') {
                payload.chain_keywords = picked.map(p => p.text);
            } else if (picked.length) {
                payload.title_texts = picked.map(p => p.text);
            } else if (s.type === 'generate' || s.type === 'prompt') {
                const q = this.checkedQuestions();
                if (q.length) payload.title_texts = q.map(x => x.title);
            }

            s.running = true; s.applyMessage = '';
            try {
                const got = await this._json('/api/v1/workbench/run',
                    { method: 'POST', body: JSON.stringify(payload) });
                (got.captured.items || []).forEach(it => { it.checked = false; });
                s.outcome = got;
                s.filter = 'all';
            } catch (e) {
                s.outcome = {
                    success: false, message: '실행 실패: ' + e.message,
                    captured: { total: 0, items: [], clipped: 0 },
                    counts: { total: 0, kept: 0, excluded: 0 },
                };
            } finally { s.running = false; }
        },

        // ── 결과 목록 ────────────────────────────────────────
        itemsFor(s) {
            const items = s.outcome?.captured?.items || [];
            if (s.filter === 'kept') return items.filter(i => !i.excluded);
            if (s.filter === 'excluded') return items.filter(i => i.excluded);
            return items;
        },
        countOf(s, f) {
            const c = s.outcome?.counts || {};
            return f === 'all' ? (c.total || 0)
                 : f === 'kept' ? (c.kept || 0) : (c.excluded || 0);
        },
        filterLabel(f) {
            return f === 'all' ? '전체' : f === 'kept' ? '채택' : '제외';
        },
        selectedOf(i) {
            const s = this.steps[i];
            return (s?.outcome?.captured?.items || [])
                .filter(it => it.checked && !it.excluded);
        },

        // ── 반영 ─────────────────────────────────────────────
        applyLabel(s) {
            return {
                keyword: '반영 — 키워드 풀에 채택',
                title_gen: '반영 — 제목 재고에 투입',
                data: '반영 — 제목 재고에 투입',
                generate: '반영은 미리보기에서', prompt: '반영은 미리보기에서',
            }[s.type] || '반영';
        },
        async applyStep(i) {
            const s = this.steps[i];
            const picked = this.selectedOf(i);
            if (s.type === 'generate' || s.type === 'prompt') {
                s.applyMessage = '글은 미리보기에서 확인 후 반영하세요.';
                return;
            }
            if (!picked.length) {
                s.applyMessage = '반영할 항목을 먼저 체크하세요.'; return;
            }
            s.applying = true; s.applyMessage = '';
            try {
                let got;
                if (s.type === 'keyword') {
                    got = await this._json('/api/v1/workbench/apply/keywords', {
                        method: 'POST',
                        body: JSON.stringify({
                            keywords: picked.map(p => p.text),
                            blog_id: this.blogId,
                        }),
                    });
                } else {
                    got = await this._json('/api/v1/workbench/apply/titles', {
                        method: 'POST',
                        body: JSON.stringify({ titles: picked.map(p => p.text) }),
                    });
                }
                s.applyMessage = got.message || '반영됨';
            } catch (e) { s.applyMessage = '실패: ' + e.message; }
            finally { s.applying = false; }
        },

        // ── 미리보기·글 반영 ─────────────────────────────────
        showPreview(s, item) {
            this.preview = {
                title: item.text, html: item.html || '',
                imageUrl: item.image_url || null, fromStep: s.uid,
            };
            this.postMessage = ''; this.editMode = false;
        },
        previewDoc() {
            const base = 'body{margin:16px;font-family:system-ui,sans-serif;'
                + 'font-size:15px;line-height:1.7;color:#222}'
                + 'img{max-width:100%;height:auto}'
                + 'table{border-collapse:collapse;width:100%}'
                + 'th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px}';
            return '<style>' + base + (this.previewCss || '') + '</style>'
                + '<div class="wb-preview">' + (this.preview.html || '') + '</div>';
        },
        async applyPost(mode) {
            if (!this.blogId) { this.postMessage = '실패: 블로그를 먼저 고르세요'; return; }
            if (mode === 'now'
                && !confirm('즉시 발행합니다. 실제 블로그에 올라가며 되돌릴 수 없습니다.\n진행할까요?')) {
                return;
            }
            try {
                const got = await this._json('/api/v1/workbench/apply/post', {
                    method: 'POST',
                    body: JSON.stringify({
                        blog_id: this.blogId, title: this.preview.title,
                        html: this.preview.html, image_url: this.preview.imageUrl,
                        mode,
                    }),
                });
                this.postMessage = got.message || '반영됨';
            } catch (e) { this.postMessage = '실패: ' + e.message; }
        },
        async copyHtml() {
            try {
                await navigator.clipboard.writeText(this.preview.html || '');
                this.postMessage = 'HTML을 복사했습니다.';
            } catch (e) { this.postMessage = '실패: 복사 권한이 없습니다'; }
        },

        // ── 소스 패널 ────────────────────────────────────────
        async searchSources() {
            const q = (this.sourceQuery || '').trim();
            if (q.length < 2) { this.sourceError = '검색어가 너무 짧습니다'; return; }
            this.sourceLoading = true; this.sourceError = '';
            try {
                const got = await this._json(
                    '/api/v1/workbench/sources?query=' + encodeURIComponent(q));
                this.sourceItems = (got.items || []).map(i =>
                    Object.assign({ checked: false }, i));
                this.sourceError = got.error || '';
            } catch (e) { this.sourceError = e.message; }
            finally { this.sourceLoading = false; }
        },
        checkedQuestions() {
            return this.sourceItems.filter(i => i.checked);
        },

        // ── 프리셋 ───────────────────────────────────────────
        async loadPresets() {
            try {
                const got = await this._json('/api/v1/workbench/presets');
                this.presets = got.presets || [];
            } catch (e) { console.error('프리셋 로드 실패:', e); }
        },
        async savePreset() {
            const name = prompt('프리셋 이름 (구성만 저장됩니다 — 결과물은 저장되지 않습니다)');
            if (!name) return;
            const config = {
                blog_id: this.blogId,
                steps: this.steps.map(s => ({ type: s.type, module_id: s.moduleId })),
            };
            try {
                await this._json('/api/v1/workbench/presets', {
                    method: 'POST', body: JSON.stringify({ name, config }),
                });
                await this.loadPresets();
            } catch (e) { alert('저장 실패: ' + e.message); }
        },
        loadPreset() {
            const p = this.presets.find(x => x.name === this.presetPick);
            if (!p) return;
            const cfg = p.config || {};
            this.blogId = cfg.blog_id ?? null;
            this.loadPreviewCss();
            this.steps = (cfg.steps || []).map(st => ({
                uid: ++this._uid, type: st.type, moduleId: st.module_id,
                moduleName: (this.catalog.modules[st.type] || [])
                    .find(m => m.id === st.module_id)?.name || ('#' + st.module_id),
                outcome: null, filter: 'all',
                running: false, applying: false, applyMessage: '',
            }));
        },

        discardAll() {
            if (this.steps.length
                && !confirm('모든 단계와 결과를 버립니다. 반영하지 않은 것은 사라집니다.')) return;
            this.steps = [];
            this.preview = { title: '', html: '', imageUrl: null, fromStep: null };
            this.postMessage = '';
        },
    };
}
