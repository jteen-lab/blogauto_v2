/**
 * 모듈 테스터 소스 검색 — 담은 블로그의 키워드 칩.
 *
 * 블로그마다 정해 둔 하위 주제·키워드를 검색창 아래에 펼쳐 두고,
 * 누르면 검색창에 들어간다. 검색은 하지 않는다 — 키워드를 이어 붙이거나
 * 뒤에 말을 덧붙여 찾는 일이 잦다.
 *
 * 순서도: docs/flowcharts/workbench_blog_keywords.md
 */
function blogKeywordPart() {
    return {
        blogKeywords: [],        // [{blog_id, blog_name, subtopics:[{subtopic_id, subtopic_name, topic_name, keywords:[]}]}]
        blogKeywordsOpen: true,  // 칩 영역 펼침/접힘 — 시트를 닫아도 유지
        blogKeywordsLoading: false,
        blogKeywordsError: '',   // 받다 실패하면 '없다' 대신 이걸 보인다
        _blogKeywordsFor: '',    // 어느 블로그 조합으로 받았는지 — 같으면 다시 안 받는다

        /** 담은 블로그가 바뀌었을 때 부른다. 조합이 같으면 건너뛴다. */
        async loadBlogKeywords() {
            const key = this.blogs.map(b => b.id).join(',');
            if (key === this._blogKeywordsFor) return;
            this._blogKeywordsFor = key;
            if (!key) { this.blogKeywords = []; return; }
            this.blogKeywordsLoading = true; this.blogKeywordsError = '';
            try {
                const got = await this._json(
                    '/api/v1/workbench/blog-keywords?blog_ids=' + key);
                // 받는 사이 블로그가 또 바뀌었으면 이 응답은 버린다
                if (key !== this._blogKeywordsFor) return;
                this.blogKeywords = got.blogs || [];
            } catch (e) {
                console.error('블로그 키워드 로드 실패:', e);
                this.blogKeywords = [];
                this.blogKeywordsError = '키워드를 불러오지 못했습니다: ' + e.message;
            } finally { this.blogKeywordsLoading = false; }
        },

        /** 칩 수 — 없으면 영역 자체를 숨긴다. */
        blogKeywordCount() {
            return this.blogKeywords.reduce((n, b) =>
                n + b.subtopics.reduce((m, s) => m + s.keywords.length, 0), 0);
        },

        /** 검색창에 넣는다. 비어 있으면 그대로, 있으면 한 칸 띄워 뒤에.
         *  이미 들어 있는 키워드는 또 붙이지 않는다. */
        pickBlogKeyword(kw) {
            const text = this._kwText(kw);
            const cur = (this.sourceQuery || '').trim();
            const has = cur.split(/\s+/).join(' ').includes(text);
            if (!cur) this.sourceQuery = text;
            else if (!has) this.sourceQuery = cur + ' ' + text;
            this.$nextTick(() => {
                const el = this.$refs.sourceInput;
                if (el) el.focus();
            });
        },

        /** 이 키워드가 지금 검색창에 들어 있는지 — 칩 색을 바꾼다. */
        blogKeywordPicked(kw) {
            return (this.sourceQuery || '').includes(this._kwText(kw));
        },

        /** 키워드 풀은 '포장+이사'처럼 + 로 묶어 둔다. 검색창에는 띄어 넣는다. */
        _kwText(kw) {
            return String(kw || '').replace(/\+/g, ' ').replace(/\s+/g, ' ').trim();
        },
    };
}
