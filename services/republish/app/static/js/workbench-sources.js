/**
 * 모듈 테스터 — 글감(소스) 찾기.
 *
 * 네 갈래로 찾는다. 지식iN 질문 · 카페 질문 · 키워드·제목(블로그·웹문서) ·
 * 임시제목(우리 DB). 고른 순간 본문을 가져오고, 고른 뒤 길은 모두 같다.
 *
 * **순서는 네이버가 준 대로 둔다** — 우리가 다시 정렬하지 않는다.
 *
 * 순서도: docs/flowcharts/workbench_source_modes.md
 */
function sourcePart() {
    return {
        // 글감을 어디서 찾을까. 고른 뒤 길은 모두 같다.
        //   kin  = 지식iN 질문      cafe = 카페 질문
        //   web  = 키워드·제목      temp = 담은 블로그의 임시제목
        sourceMode: 'kin',
        sourceQuery: '', sourceItems: [], sourceError: '', sourceLoading: false,
        sourceNextStart: null, sourceLastQuery: '',
        sourceScrollTop: 0,   // 질문 목록에서 보던 자리
        // 네이버 화면 기본이 정확도순이다. 최신순으로 바꿔 볼 수 있다.
        sourceSort: 'sim',
        bodyLoading: false,
        pickedQuestions: [],

        // 찾는 곳의 이름. 시트 제목과 버튼에 같이 쓴다.
        SOURCE_MODES: [
            { code: 'kin', label: '지식iN 질문' },
            { code: 'cafe', label: '카페 질문' },
            { code: 'web', label: '키워드·제목 검색' },
            { code: 'temp', label: '임시제목' },
        ],

        sourceModeLabel(mode) {
            const m = this.SOURCE_MODES.find(x => x.code === (mode || this.sourceMode));
            return m ? m.label : '글 소스';
        },

        /** 지금 모드가 부를 주소. 모드마다 길이 다르다. */
        _sourceUrl(q, start) {
            const base = '/api/v1/workbench/';
            const query = 'query=' + encodeURIComponent(q) + '&start=' + start;
            if (this.sourceMode === 'temp') {
                return base + 'temp-titles?' + query
                    + '&blog_ids=' + this.blogs.map(b => b.id).join(',');
            }
            if (this.sourceMode === 'web') {
                return base + 'web-sources?' + query + '&sort=' + this.sourceSort;
            }
            const src = this.sourceMode === 'cafe' ? 'naver_cafe' : 'naver_kin';
            return base + 'sources?' + query + '&sources=' + src
                + '&sort=' + this.sourceSort;
        },

        /** 정렬을 바꾸면 바로 다시 찾는다 — 순서를 보려고 누르는 것이다. */
        setSourceSort(sort) {
            if (this.sourceSort === sort) return;
            this.sourceSort = sort;
            if (this.sourceLastQuery) this.searchSources();
        },

        // ── 소스 ─────────────────────────────────────────────
        async searchSources(more = false) {
            const q = (this.sourceQuery || '').trim();
            if (q.length < 2) { this.sourceError = '검색어가 너무 짧습니다'; return; }
            if (this.sourceMode === 'temp' && !this.blogs.length) {
                this.sourceError = '블로그를 먼저 담으세요 — 그 블로그의 '
                    + '하위 주제 안에서만 찾습니다';
                return;
            }
            // 검색어가 바뀌면 처음부터. 더 보기면 이어서.
            const start = (more && q === this.sourceLastQuery)
                ? (this.sourceNextStart || 1) : 1;
            this.sourceLoading = true; this.sourceError = '';
            try {
                const got = await this._json(this._sourceUrl(q, start));
                const rows = (got.items || []).map(i =>
                    Object.assign({ checked: false }, i));
                if (start === 1) {
                    this.sourceItems = rows;
                    // 새 검색은 처음부터 본다
                    this.sourceScrollTop = 0;
                    this.$nextTick(() => {
                        const box = this.$refs.sourceScroll;
                        if (box) box.scrollTop = 0;
                    });
                } else {
                    // 같은 글이 겹쳐 오면 한 번만 남긴다
                    const seen = new Set(this.sourceItems.map(i => i.link));
                    this.sourceItems.push(...rows.filter(i => !seen.has(i.link)));
                }
                this.sourceNextStart = got.next_start || null;
                this.sourceLastQuery = q;
                this.sourceError = got.error || '';
            } catch (e) { this.sourceError = e.message; }
            finally { this.sourceLoading = false; }
        },
        checkedQuestions() { return this.sourceItems.filter(i => i.checked); },

        /** 이 글감의 본문을 어느 길로 가져올지.
         *
         *  질문 페이지와 아무 웹페이지는 본문이 있는 자리가 다르다.
         *  글감에 적힌 출처를 따르고, 없으면 지금 모드를 따른다.
         */
        _bodyPath(item) {
            const src = String((item && item.source) || '').trim();
            const isQ = !src || src === 'naver_kin' || src === 'naver_cafe';
            return '/api/v1/workbench/'
                + (isQ ? 'question-body' : 'page-body');
        },

        /** 이 글감을 열어 볼 수 있나. 임시제목은 원문 주소가 비어 있을 수
         *  있다 — 그때는 제목만으로 글을 만든다. */
        hasSourceLink(item) { return !!(item && item.link); },

        /** 찾을 곳을 바꾸며 시트를 연다. 곳이 바뀌면 목록을 비운다 —
         *  섞이면 어디서 온 글인지 알 수 없다. */
        openSourceSheet(mode) {
            if (mode && this.sourceMode !== mode) {
                this.sourceMode = mode;
                this.sourceItems = [];
                this.sourceQuery = '';
                this.sourceError = '';
                this.sourceNextStart = null;
                this.sourceLastQuery = '';
            }
            this.openSheet('source');
        },
        /** 체크한 순간 본문을 가져온다. 버튼을 한 번 더 누르게 하면
         *  잊고 그냥 생성해 제목만으로 글이 나간다. */
        async onQuestionCheck(q) {
            if (!q.checked) return;
            if (q.body) { q.bodyOpen = true; return; }
            if (!q.link || q.bodyLoading) return;
            q.bodyLoading = true; q.bodyError = '';
            try {
                const got = await this._json(this._bodyPath(q), {
                    method: 'POST', body: JSON.stringify({ links: [q.link] }),
                });
                const row = (got.items || [])[0];
                if (row && (row.question || row.answer)) {
                    q.body = { question: row.question, answer: row.answer };
                    q.bodyOpen = true;
                } else {
                    q.bodyError = (row && row.error) || '본문을 못 가져왔습니다';
                }
            } catch (e) { q.bodyError = '실패: ' + e.message; }
            finally { q.bodyLoading = false; }
        },
        /** 체크한 질문의 본문을 가져온다.
         *  고른 것만 부른다 — 목록을 통째로 긁으면 한 번에 수 MB 다. */
        async fetchQuestionBodies() {
            const picked = this.checkedQuestions();
            if (!picked.length) {
                this.sourceError = '내용을 가져올 질문을 먼저 체크하세요';
                return;
            }
            this.bodyLoading = true; this.sourceError = '';
            try {
                const got = await this._json(this._bodyPath(picked[0]), {
                    method: 'POST',
                    body: JSON.stringify({ links: picked.map(q => q.link) }),
                });
                const byLink = {};
                for (const row of (got.items || [])) byLink[row.link] = row;
                let ok = 0;
                for (const q of picked) {
                    const row = byLink[q.link];
                    if (row && (row.question || row.answer)) {
                        q.body = { question: row.question, answer: row.answer };
                        q.bodyOpen = true;
                        ok += 1;
                    } else {
                        q.bodyError = (row && row.error) || '본문을 못 가져왔습니다';
                    }
                }
                this.sourceError = ok ? ''
                    : '본문을 가져오지 못했습니다 — 제목만으로 진행됩니다';
            } catch (e) { this.sourceError = '실패: ' + e.message; }
            finally { this.bodyLoading = false; }
        },
        /** 고른 질문을 놓는다. 가져온 본문은 접어 두되 버리지 않는다 —
         *  다시 쓰려고 펼치면 부르지 않고 바로 보인다. */
        releaseSources() {
            (this.sourceItems || []).forEach(q => {
                q.checked = false;
                if (q.body) q.bodyOpen = false;
            });
            this.pickedQuestions = [];
        },
        applyPickedQuestions() {
            this.pickedQuestions = this.checkedQuestions().slice();
            this.closeSheet();
        },
    };
}
