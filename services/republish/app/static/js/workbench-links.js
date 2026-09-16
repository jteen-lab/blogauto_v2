/**
 * 모듈 테스터 — 홍보 링크 칸.
 *
 * 글 끝에 붙일 버튼 하나를 고르고, 등록하고, 고친다. 등록과 수정은
 * **같은 칸**을 쓴다 — 칸이 둘이면 어느 쪽에 적어야 하는지 매번
 * 헷갈린다. 고치기를 누르면 그 링크의 값이 칸에 들어차고, 저장
 * 버튼의 이름이 바뀐다.
 *
 * 순서도: docs/flowcharts/promo_link_auto.md
 */

/** 고지문 기본값 — 서버 모델의 DEFAULT_NOTICE 와 같게 둔다. */
const PROMO_DEFAULT_NOTICE = '이 포스팅은 애드릭스 수익을 위해 작성되었습니다.';

/** 빈 등록 칸. */
function emptyLinkForm(notice, blogOnly) {
    return {
        name: '', url: '', button_text: '', keywords: '',
        notice: notice === undefined ? PROMO_DEFAULT_NOTICE : notice,
        blogOnly: !!blogOnly,
    };
}

/** 모듈 테스터에 섞어 넣는 홍보 링크 부분. */
function promoLinkPart() {
    return {
        // ── 상태 ─────────────────────────────────────────────
        links: [], pickedLink: null, linkSaving: false, linkMessage: '',
        linkForm: emptyLinkForm(),
        linkEditId: null,  // 고치는 중인 링크. null 이면 새로 등록
        linkAuto: false,   // 제목의 키워드로 링크를 고를지

        // ── 목록·선택 ────────────────────────────────────────
        async loadLinks() {
            try {
                const q = this.blogs[0] ? '?blog_id=' + this.blogs[0].id : '';
                const got = await this._json('/api/v1/promo-links' + q);
                this.links = got.items || [];
                if (!this.pickedLink) this.restoreLink();
            } catch (e) { console.error('링크 로드 실패:', e); }
        },
        pickLink(l) {
            this.pickedLink = l; this.linkAuto = false;
            this.rememberLink(); this.closeSheet();
            if (this.preview.raw) this.assemble();
        },
        /** 제목의 키워드로 고르게 한다. 글마다 다른 링크가 붙는다. */
        useAutoLink() {
            this.linkAuto = true; this.pickedLink = null;
            this.rememberLink(); this.closeSheet();
            if (this.preview.raw) this.assemble();
        },
        clearLink() {
            this.pickedLink = null; this.linkAuto = false;
            this.rememberLink(); this.closeSheet();
            if (this.preview.raw) this.assemble();
        },
        /** 고른 링크를 기억해 둔다. 테스트마다 다시 고르지 않아도 된다. */
        rememberLink() {
            try {
                const v = this.linkAuto ? 'auto'
                    : (this.pickedLink ? String(this.pickedLink.id) : '');
                if (v) localStorage.setItem('mt_link_id', v);
                else localStorage.removeItem('mt_link_id');
            } catch (e) { /* 저장이 막힌 브라우저 — 기억만 안 될 뿐 */ }
        },
        /** 지난번에 고른 링크를 되살린다. */
        restoreLink() {
            try {
                const raw = localStorage.getItem('mt_link_id') || '';
                if (raw === 'auto') { this.linkAuto = true; return; }
                const id = parseInt(raw, 10);
                if (id) this.pickedLink = this.links.find(l => l.id === id) || null;
            } catch (e) { /* 무시 */ }
        },

        // ── 등록·수정 ────────────────────────────────────────
        /** 목록의 링크를 등록 칸으로 불러온다. */
        editLink(l) {
            this.linkEditId = l.id;
            this.linkForm = {
                name: l.name || '', url: l.url || '',
                button_text: l.button_text || '', keywords: l.keywords || '',
                notice: l.notice || '', blogOnly: !!l.blog_id,
            };
            this.linkMessage = '';
        },
        /** 고치기를 그만둔다. 칸은 새 등록 상태로 돌아간다. */
        cancelEditLink() {
            this.linkEditId = null;
            this.linkForm = emptyLinkForm();
            this.linkMessage = '';
        },
        /** 칸에 적은 값. 고칠 때는 원래 값을 참고한다. */
        _linkBody(orig) {
            const f = this.linkForm;
            let blogId = null;
            if (f.blogOnly) {
                // 블로그를 담지 않고 고치는 중이면 원래 블로그를 지킨다
                blogId = this.blogs[0] ? this.blogs[0].id
                    : (orig ? orig.blog_id : null);
            }
            return {
                name: f.name.trim(), url: f.url.trim(),
                button_text: f.button_text.trim(),
                notice: (f.notice || '').trim(),
                keywords: (f.keywords || '').trim(),
                blog_id: blogId,
            };
        },
        /** 등록하거나 고친다. 어느 쪽인지는 linkEditId 가 가른다. */
        async saveLink() {
            const f = this.linkForm;
            if (!f.name.trim() || !f.url.trim() || !f.button_text.trim()) {
                this.linkMessage = '실패: 이름·주소·버튼 문구는 필요합니다'; return;
            }
            this.linkSaving = true; this.linkMessage = '';
            try {
                if (this.linkEditId) await this._patchLink();
                else await this._createLink();
            } catch (e) { this.linkMessage = '실패: ' + e.message; }
            finally { this.linkSaving = false; }
        },
        async _createLink() {
            const f = this.linkForm;
            const got = await this._json('/api/v1/promo-links', {
                method: 'POST', body: JSON.stringify(this._linkBody(null)),
            });
            this.links.unshift(got.link);
            this.pickedLink = got.link; this.linkAuto = false;
            this.rememberLink();
            this.linkForm = emptyLinkForm(f.notice, f.blogOnly);
            this.linkMessage = '등록했습니다. 이 링크가 선택되었습니다.';
        },
        async _patchLink() {
            const id = this.linkEditId;
            const orig = this.links.find(x => x.id === id) || null;
            const got = await this._json('/api/v1/promo-links/' + id, {
                method: 'PATCH', body: JSON.stringify(this._linkBody(orig)),
            });
            const at = this.links.findIndex(x => x.id === id);
            if (at >= 0) this.links[at] = got.link;
            // 고르고 있던 링크면 고른 값도 따라가야 미리보기가 맞는다
            if (this.pickedLink && this.pickedLink.id === id) {
                this.pickedLink = got.link;
                if (this.preview.raw) this.assemble();
            }
            this.cancelEditLink();
            this.linkMessage = '고쳤습니다.';
        },
        async deleteLink(l) {
            if (!confirm('"' + l.name + '" 링크를 목록에서 뺄까요?')) return;
            try {
                await this._json('/api/v1/promo-links/' + l.id, { method: 'DELETE' });
                this.links = this.links.filter(x => x.id !== l.id);
                if (this.pickedLink && this.pickedLink.id === l.id) this.pickedLink = null;
                if (this.linkEditId === l.id) this.cancelEditLink();
            } catch (e) { this.linkMessage = '실패: ' + e.message; }
        },
    };
}
