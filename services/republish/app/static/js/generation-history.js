/**
 * 생성 이력 페이지 Alpine.js 컴포넌트
 *
 * 설계 문서: generation_content_storage_plan.md - Phase 3
 */
function generationHistory() {
    return {
        // 목록 상태
        loading: false,
        items: [],
        total: 0,
        currentPage: 1,
        pageSize: 20,
        totalPages: 0,

        // 필터
        filter: {
            blogId: '',
        },

        // 콘텐츠 보기 모달
        modal: {
            open: false,
            loading: false,
            title: '',
            blogName: '',
            html: '',
            rawHtml: '',
            copied: false,
        },

        // 삭제 확인 모달
        deleteConfirm: {
            open: false,
            loading: false,
            id: null,
            title: '',
        },

        // 초기화
        init() {
            this.loadContent(1);
        },

        /**
         * 콘텐츠 목록 로드
         */
        async loadContent(page) {
            if (page < 1 || (this.totalPages > 0 && page > this.totalPages)) return;
            this.loading = true;
            this.currentPage = page;

            try {
                const params = new URLSearchParams({
                    page: String(page),
                    page_size: String(this.pageSize),
                });
                if (this.filter.blogId) {
                    params.set('blog_id', this.filter.blogId);
                }

                const resp = await fetch(
                    `/api/v1/generation/content/list?${params}`
                );
                if (!resp.ok) throw new Error('목록 조회 실패');

                const data = await resp.json();
                this.items = data.items || [];
                this.total = data.total || 0;
                this.totalPages = Math.ceil(this.total / this.pageSize);
            } catch (e) {
                console.error('[GenerationHistory] loadContent:', e);
                this.items = [];
            } finally {
                this.loading = false;
            }
        },

        /**
         * 콘텐츠 보기 모달 열기
         */
        async viewContent(crawledPostId) {
            this.modal.open = true;
            this.modal.loading = true;
            this.modal.html = '';
            this.modal.rawHtml = '';
            this.modal.copied = false;

            try {
                const resp = await fetch(
                    `/api/v1/generation/content/${crawledPostId}`
                );
                if (!resp.ok) throw new Error('콘텐츠 조회 실패');

                const data = await resp.json();
                this.modal.title = data.title || '';
                this.modal.blogName = data.blog_name || '';
                this.modal.html = data.content_html || '<p class="text-gray-400">콘텐츠가 없습니다</p>';
                this.modal.rawHtml = data.content_html || '';
            } catch (e) {
                console.error('[GenerationHistory] viewContent:', e);
                this.modal.html = '<p class="text-red-500">콘텐츠 로딩 실패</p>';
            } finally {
                this.modal.loading = false;
            }
        },

        /**
         * HTML 클립보드 복사 (목록에서)
         */
        async copyHtml(crawledPostId) {
            try {
                const resp = await fetch(
                    `/api/v1/generation/content/${crawledPostId}/html`
                );
                if (!resp.ok) throw new Error('HTML 조회 실패');

                const data = await resp.json();
                await navigator.clipboard.writeText(data.html || '');
                this._showToast('HTML이 클립보드에 복사되었습니다');
            } catch (e) {
                console.error('[GenerationHistory] copyHtml:', e);
                this._showToast('복사 실패', true);
            }
        },

        /**
         * 모달 내 HTML 복사
         */
        async copyModalHtml() {
            try {
                await navigator.clipboard.writeText(this.modal.rawHtml);
                this.modal.copied = true;
                setTimeout(() => { this.modal.copied = false; }, 2000);
            } catch (e) {
                console.error('[GenerationHistory] copyModalHtml:', e);
            }
        },

        /**
         * 삭제 확인 모달 열기
         */
        confirmDelete(item) {
            this.deleteConfirm.open = true;
            this.deleteConfirm.loading = false;
            this.deleteConfirm.id = item.crawled_post_id;
            this.deleteConfirm.title = item.title;
        },

        /**
         * 삭제 실행
         */
        async executeDelete() {
            if (!this.deleteConfirm.id) return;
            this.deleteConfirm.loading = true;

            try {
                const resp = await fetch(
                    `/api/v1/generation/content/${this.deleteConfirm.id}`,
                    { method: 'DELETE' }
                );
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || '삭제 실패');
                }

                this.deleteConfirm.open = false;
                this._showToast('콘텐츠가 삭제되었습니다');
                await this.loadContent(this.currentPage);
            } catch (e) {
                console.error('[GenerationHistory] executeDelete:', e);
                this._showToast(e.message, true);
            } finally {
                this.deleteConfirm.loading = false;
            }
        },

        /**
         * 날짜 포맷
         */
        formatDate(isoStr) {
            if (!isoStr) return '-';
            const d = new Date(isoStr);
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const h = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            return `${m}-${day} ${h}:${min}`;
        },

        /**
         * 토스트 메시지
         */
        _showToast(msg, isError = false) {
            const el = document.createElement('div');
            el.className = `fixed bottom-4 right-4 z-[100] px-4 py-2 rounded-lg shadow-lg text-sm text-white ${
                isError ? 'bg-red-500' : 'bg-green-500'
            }`;
            el.textContent = msg;
            document.body.appendChild(el);
            setTimeout(() => el.remove(), 3000);
        },
    };
}
