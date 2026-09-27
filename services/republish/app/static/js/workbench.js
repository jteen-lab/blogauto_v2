/**
 * 모듈 테스터 — 모듈을 담아 한 번 돌려보고, 반영할지 버릴지 정한다.
 *
 * 실행은 리허설이다: 서버가 실제 발행 길을 그대로 돌리되 마지막에
 * 되돌린다. 반영 버튼을 눌러야만 실제 데이터에 들어간다.
 *
 * 화면 규칙(다른 페이지와 통일):
 *   - 폭은 max-w-7xl, 우측 상단 추가 버튼, 모바일 플로팅 버튼
 *   - 담긴 블로그·모듈은 상단 요약줄에 칩으로
 *   - 선택·미리보기는 전부 하단 시트로 확장
 *
 * 단계 연결: 앞 단계에서 체크한 것이 다음 단계 실행의 입력이 된다.
 *   키워드 선택 → 제목 생성이 그 키워드를 채택된 것처럼 쓴다
 *   제목 선택   → 글 생성이 그 제목으로 만든다
 *   소스 질문   → 글 생성이 질문 제목으로 만든다
 *
 * 계획서: docs/plans/test_workbench_plan.md
 */
function moduleTester() {
    return {
        // ── 상태 ─────────────────────────────────────────────
        catalog: { modules: {}, all_modules: [], blogs: [] },
        blogs: [],            // 담긴 블로그 [{id,name,platform}]
        steps: [],            // {uid,type,moduleId,moduleName,outcome,items,clipped,filter,...}
        moduleQuery: '', moduleTypeFilter: '',
        typeLabel: {
            keyword: '키워드', title_gen: '제목 생성/수집',
            data: '제목 이관', generate: '글 생성', prompt: '글 생성',
        },
        sheet: null,          // blog | module | source | link | preview
        // 글감 찾기(별도 파일 workbench-sources.js)
        ...sourcePart(),
        // 홍보 링크(상태·등록·수정)는 workbench-links.js 에 있다
        ...promoLinkPart(),
        // 담은 블로그의 키워드 칩(별도 파일)
        ...blogKeywordPart(),
        preview: { title: '', html: '', imageUrl: null, raw: '' },
        previewItem: null, previewStep: null,
        previewCss: '', editMode: false, postMessage: '',
        presets: [], presetPick: '',
        _uid: 0,

        // 글 생성 회차당 편수 상한 — AI 비용 통제
        MAX_POSTS: 3,

        async init() {
            await Promise.all([this.loadCatalog(), this.loadPresets(),
                               this.loadLinks()]);
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

        // ── 하단 시트 ────────────────────────────────────────
        openSheet(name) {
            this.sheet = name;
            document.body.style.overflow = 'hidden';
            // 질문 목록은 보던 자리에서 다시 열린다. 맨 위로 튕기면
            // 아래쪽에서 고르던 사람은 같은 곳을 다시 찾아 내려가야 한다.
            if (name === 'source') {
                this.$nextTick(() => {
                    const box = this.$refs.sourceScroll;
                    if (box) box.scrollTop = this.sourceScrollTop || 0;
                });
            }
        },
        closeSheet() {
            this._rememberSourceScroll();
            this.sheet = null;
            document.body.style.overflow = '';
        },
        /** 질문 목록에서 어디까지 내려갔는지 적어 둔다. */
        _rememberSourceScroll() {
            if (this.sheet !== 'source') return;
            const box = this.$refs.sourceScroll;
            if (box) this.sourceScrollTop = box.scrollTop;
        },
        sheetTitle() {
            // 소스 시트는 지금 찾는 곳의 이름을 쓴다 — 시트 안에서 곳을
            // 바꾸면 제목도 같이 바뀐다
            if (this.sheet === 'source') return this.sourceModeLabel();
            return { blog: '블로그 선택', module: '모듈 담기',
                     link: '홍보 링크', preview: '미리보기' }[this.sheet] || '';
        },

        // ── 모듈 표 ──────────────────────────────────────────
        /** 종류 필터에 쓸 목록. 실제로 있는 종류만 낸다. */
        moduleTypes() {
            const seen = {};
            for (const m of (this.catalog.all_modules || [])) {
                if (!seen[m.type]) {
                    seen[m.type] = { code: m.type, label: m.type_label, count: 0 };
                }
                seen[m.type].count += 1;
            }
            return Object.values(seen);
        },
        /** 이름 검색과 종류 필터를 적용한 목록. 담을 수 있는 것이 위로 온다. */
        filteredModules() {
            const q = (this.moduleQuery || '').trim().toLowerCase();
            const t = this.moduleTypeFilter;
            return (this.catalog.all_modules || [])
                .filter(m => (!t || m.type === t)
                    && (!q || m.name.toLowerCase().includes(q)))
                .sort((a, b) => (b.supported - a.supported)
                    || a.type_label.localeCompare(b.type_label)
                    || a.name.localeCompare(b.name));
        },

        // ── 블로그 ───────────────────────────────────────────
        hasBlog(id) { return this.blogs.some(b => b.id === id); },
        toggleBlog(b) {
            if (this.hasBlog(b.id)) this.removeBlog(b.id);
            else {
                this.blogs.push(b); this.loadPreviewCss(); this.loadLinks();
                this.loadBlogKeywords();
            }
        },
        removeBlog(id) {
            this.blogs = this.blogs.filter(b => b.id !== id);
            this.loadPreviewCss();
            this.loadBlogKeywords();
        },
        async loadPreviewCss() {
            this.previewCss = '';
            const first = this.blogs[0];
            if (!first) return;
            try {
                const got = await this._json(
                    '/api/v1/workbench/preview-css?blog_id=' + first.id);
                this.previewCss = got.css || '';
            } catch (e) { console.error('미리보기 CSS 실패:', e); }
        },

        // ── 단계 구성 ────────────────────────────────────────
        addStep(type, m) {
            this.steps.push({
                uid: ++this._uid, type, moduleId: m.id, moduleName: m.name,
                outcome: null, items: [], clipped: 0, filter: 'all',
                running: false, applying: false, applyMessage: '',
            });
        },

        // ── 실행 ─────────────────────────────────────────────
        async runStep(i) {
            const s = this.steps[i];
            if (s.running) return;
            const targets = this.blogs.length ? this.blogs : [null];

            const base = {
                module_type: s.type === 'prompt' ? 'generate' : s.type,
                module_id: s.moduleId,
            };
            const picked = i > 0 ? this.selectedOf(i - 1) : [];
            const prevType = i > 0 ? this.steps[i - 1].type : null;
            if (picked.length && prevType === 'keyword') {
                base.chain_keywords = picked.map(p => p.text);
            } else if (picked.length) {
                base.title_texts = picked.map(p => p.text).slice(0, this.MAX_POSTS);
            } else if (base.module_type === 'generate' && this.pickedQuestions.length) {
                const rows = this.pickedQuestions.slice(0, this.MAX_POSTS);
                base.title_texts = rows.map(q => q.title);
                // 제목과 짝을 맞춰 보낸다. **본문이 없어도 보낸다** —
                // 카페 비공개처럼 본문을 못 가져와도 질문 제목은 질문 제목이라,
                // 어디서 왔는지를 알아야 제목을 알맞게 다시 쓴다.
                base.questions = rows.map(q => Object.assign(
                    {}, q.body || {}, { source: q.source || '' }));
            }

            s.running = true; s.applyMessage = '';
            const items = [];
            const messages = [];
            let clipped = 0, ok = false;

            try {
                for (const blog of targets) {
                    const payload = Object.assign({}, base,
                        { blog_id: blog ? blog.id : null });
                    const got = await this._json('/api/v1/workbench/run',
                        { method: 'POST', body: JSON.stringify(payload) });
                    if (got.success) ok = true;
                    messages.push((blog ? blog.name + ': ' : '') + (got.message || ''));
                    clipped += (got.captured?.clipped || 0);
                    (got.captured?.items || []).forEach(it => {
                        it.checked = false;
                        it.blogName = blog ? blog.name : '';
                        items.push(it);
                    });
                }
                s.items = items;
                s.clipped = clipped;
                s.outcome = {
                    success: ok,
                    message: messages.filter(Boolean).join(' / ') || '완료',
                };
            } catch (e) {
                s.items = []; s.clipped = 0;
                s.outcome = { success: false, message: '실행 실패: ' + e.message };
            } finally {
                s.filter = 'all';
                s.running = false;
            }
        },

        // ── 결과 목록 ────────────────────────────────────────
        itemsFor(s) {
            const items = s.items || [];
            if (s.filter === 'kept') return items.filter(i => !i.excluded);
            if (s.filter === 'excluded') return items.filter(i => i.excluded);
            return items;
        },
        countOf(s, f) {
            const items = s.items || [];
            if (f === 'all') return items.length;
            if (f === 'kept') return items.filter(i => !i.excluded).length;
            return items.filter(i => i.excluded).length;
        },
        filterLabel(f) {
            return f === 'all' ? '전체' : f === 'kept' ? '채택' : '제외';
        },
        selectedOf(i) {
            return (this.steps[i]?.items || [])
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
            if (s.type === 'generate' || s.type === 'prompt') {
                s.applyMessage = '글은 미리보기를 열어 확인한 뒤 반영하세요.';
                return;
            }
            const picked = this.selectedOf(i);
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
                            blog_id: this.blogs[0]?.id ?? null,
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

        // 미리보기·복사·글 반영(별도 파일 workbench-preview.js)
        ...previewPart(),

        // ── 프리셋 ───────────────────────────────────────────
        async loadPresets() {
            try {
                const got = await this._json('/api/v1/workbench/presets');
                this.presets = got.presets || [];
            } catch (e) { console.error('프리셋 로드 실패:', e); }
        },
        async savePreset() {
            const name = prompt('프리셋 이름 (블로그·모듈·링크 구성만 저장됩니다 — 결과물은 저장되지 않습니다)');
            if (!name) return;
            const config = {
                blog_ids: this.blogs.map(b => b.id),
                steps: this.steps.map(s => ({ type: s.type, module_id: s.moduleId })),
                // 링크는 담지 않는다. 프리셋에 박힌 링크 하나가 되살아나
                // 제목과 상관없이 모든 글에 같은 버튼을 달았다
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
            const ids = cfg.blog_ids || (cfg.blog_id ? [cfg.blog_id] : []);
            this.blogs = this.catalog.blogs.filter(b => ids.includes(b.id));
            this.loadPreviewCss();
            // 옛 프리셋에 남은 link_id 는 읽지 않는다 — 링크는 제목이 고른다
            this.loadLinks();   // 담은 블로그 전용 링크까지 다시 받는다
            this.loadBlogKeywords();
            this.steps = (cfg.steps || []).map(st => ({
                uid: ++this._uid, type: st.type, moduleId: st.module_id,
                moduleName: (this.catalog.all_modules || [])
                    .find(m => m.id === st.module_id)?.name || ('#' + st.module_id),
                outcome: null, items: [], clipped: 0, filter: 'all',
                running: false, applying: false, applyMessage: '',
            }));
        },

        discardAll() {
            if ((this.steps.length || this.blogs.length)
                && !confirm('담긴 것과 결과를 모두 버립니다. 반영하지 않은 것은 사라집니다.')) return;
            this.steps = []; this.blogs = []; this.pickedQuestions = [];
            this.loadBlogKeywords();
            this.preview = { title: '', html: '', imageUrl: null };
            this.postMessage = ''; this.closeSheet();
        },
    };
}
