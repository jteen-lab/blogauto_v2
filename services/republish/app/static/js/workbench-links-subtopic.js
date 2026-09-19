/**
 * 모듈 테스터 홍보 링크 — 하위 주제 고르개.
 *
 * 키워드를 손으로 적는 대신 카테고리의 하위 주제를 고른다. 고른 주제의
 * 키워드가 제목에 있으면 그 링크가 붙는다. 서버가 저장할 때 키워드를
 * 펼쳐 넣으므로 글을 만들 때는 지금과 같은 길로 간다.
 *
 * 순서도: docs/flowcharts/subtopic_link.md
 */
function promoSubtopicPart() {
    return {
        topics: [],            // 카테고리 트리
        subtopicOpen: false,   // 고르개 창
        linkSubtopics: [],     // 지금 고른 하위 주제

        /** 카테고리를 한 번만 받아 둔다. */
        async loadTopics() {
            if (this.topics.length) return;
            try {
                const got = await this._json('/api/v1/categories');
                this.topics = got.categories || [];
            } catch (e) { console.error('카테고리 로드 실패:', e); }
        },

        async openSubtopics() {
            await this.loadTopics();
            this.subtopicOpen = true;
        },

        closeSubtopics() { this.subtopicOpen = false; },

        toggleLinkSubtopic(id) {
            const at = this.linkSubtopics.indexOf(id);
            if (at === -1) this.linkSubtopics.push(id);
            else this.linkSubtopics.splice(at, 1);
        },

        linkSubtopicPicked(id) { return this.linkSubtopics.includes(id); },

        /** 단추에 적을 말. */
        linkSubtopicSummary() {
            if (!this.linkSubtopics.length) return '하위 주제로 고르기';
            const names = [];
            (this.topics || []).forEach(t => (t.subtopics || []).forEach(st => {
                if (this.linkSubtopics.includes(st.id)) names.push(st.name);
            }));
            const head = names.slice(0, 2).join('·') || (this.linkSubtopics.length + '개');
            return head + (names.length > 2 ? ` 외 ${names.length - 2}` : '');
        },

        /** 고치기로 불러올 때 링크에 저장된 주제를 되살린다. */
        restoreLinkSubtopics(link) {
            this.linkSubtopics = Array.isArray(link && link.subtopic_ids)
                ? [...link.subtopic_ids] : [];
        },
    };
}
